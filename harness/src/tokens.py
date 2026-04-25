"""
Token counting + budget resolution.

We rely on Anthropic's `messages.count_tokens` API for authoritative counts.
Rough character-based estimates in assembly.py are only for diagnostics.

Budget resolution flow for a single run (called by runner.py):
    1. Start with noise_budget = target_input_tokens - system - target_report
       - questions - safety_margin.
    2. Split into (noise_a_budget, noise_b_budget) per cell position.
    3. Assemble prompt.
    4. count_tokens() on assembled prompt.
    5. If |actual - target| > tolerance, adjust the noise budget and repeat
       (bounded by max_budget_adjustment_iterations).
    6. If we cannot converge, raise BudgetError — the run will be marked
       excluded per DESIGN §7.5.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic

from .assembly import AssembledPrompt, assemble, compute_noise_split
from .cells import RunSpec
from .config import ExperimentConfig
from .materials import Materials


class BudgetError(RuntimeError):
    """Raised when token count cannot be made to match target within tolerance."""


@dataclass(frozen=True)
class BudgetResolution:
    prompt: AssembledPrompt
    target_input_tokens: int
    realized_input_tokens: int
    iterations: int
    pool_exhausted: bool = False   # noise pool too small to hit target
    is_baseline: bool = False      # baseline cell (fill_pct=0, no noise pool)


async def count_tokens(
    client: AsyncAnthropic,
    model: str,
    prompt: AssembledPrompt,
) -> int:
    """
    Return the authoritative input_token count Anthropic would charge.
    """
    resp = await client.messages.count_tokens(
        model=model,
        system=prompt.system,
        messages=prompt.messages,
    )
    return int(resp.input_tokens)


async def resolve_budget(
    client: AsyncAnthropic,
    run: RunSpec,
    materials: Materials,
    cfg: ExperimentConfig,
) -> BudgetResolution:
    """
    Iteratively size the noise blocks so realized input tokens match the cell's
    target fill within tolerance.

    Handles three outcomes:
      - Converged within tolerance → pool_exhausted=False.
      - Under-target but the sampled noise equals pool max → pool_exhausted=True
        (honest shortfall; return, don't iterate further, don't raise).
      - Could not converge for any other reason → BudgetError.
    """
    target_input_tokens = _target_input_tokens(cfg, run, materials)
    tolerance = cfg.tokens.fill_tolerance_tokens
    pool_max_tokens = _pool_max_tokens(materials, run.cell)

    initial_overhead = _rough_overhead(cfg, materials, run)
    total_noise_budget = max(0, target_input_tokens - initial_overhead)

    def _pool_exhausted(prompt: AssembledPrompt) -> bool:
        """True if the assembled noise used (approximately) the entire available pool."""
        if pool_max_tokens == 0:
            return False
        est = prompt.estimated_tokens
        used = est.get("noise_a_actual", 0) + est.get("noise_b_actual", 0)
        # allow a small slack for pack inefficiency (largest doc that wouldn't fit)
        return used >= pool_max_tokens - 500

    iterations = 0
    prompt = None
    realized = 0
    # Track best-seen pack across iterations so a stall returns the closest
    # achievable fit (discrete doc sizes can prevent ±tolerance convergence
    # for any continuous target — observed for MSFT at 25% and 50% fill).
    best: tuple[int, AssembledPrompt, int, int] | None = None  # (|delta|, prompt, realized, iter)
    last_realized: int | None = None

    for _ in range(cfg.tokens.max_budget_adjustment_iterations):
        iterations += 1
        noise_a, noise_b = compute_noise_split(run.cell.position, total_noise_budget)
        prompt = assemble(run, materials, noise_a, noise_b)
        realized = await count_tokens(client, cfg.models.analyst.snapshot, prompt)
        delta = target_input_tokens - realized

        if best is None or abs(delta) < best[0]:
            best = (abs(delta), prompt, realized, iterations)

        # Converged: done.
        if abs(delta) <= tolerance:
            return BudgetResolution(
                prompt=prompt,
                target_input_tokens=target_input_tokens,
                realized_input_tokens=realized,
                iterations=iterations,
                pool_exhausted=False,
                is_baseline=run.cell.is_baseline,
            )

        # Under-target but pool is already maxed: honest shortfall.
        if delta > tolerance and _pool_exhausted(prompt):
            return BudgetResolution(
                prompt=prompt,
                target_input_tokens=target_input_tokens,
                realized_input_tokens=realized,
                iterations=iterations,
                pool_exhausted=True,
                is_baseline=run.cell.is_baseline,
            )

        # Baseline has no noise to adjust — accept whatever comes out.
        if run.cell.is_baseline:
            return BudgetResolution(
                prompt=prompt,
                target_input_tokens=target_input_tokens,
                realized_input_tokens=realized,
                iterations=iterations,
                pool_exhausted=False,
                is_baseline=True,
            )

        # Stall: the budget adjustment did not change which docs got packed
        # (greedy FFD over a discrete pool can oscillate between two stable
        # packs neither of which lands within tolerance). Return the closest
        # pack seen so far — flagged pool_exhausted so validation accepts it.
        if last_realized is not None and realized == last_realized:
            return BudgetResolution(
                prompt=best[1],
                target_input_tokens=target_input_tokens,
                realized_input_tokens=best[2],
                iterations=iterations,
                pool_exhausted=True,
                is_baseline=run.cell.is_baseline,
            )
        last_realized = realized

        # Otherwise, adjust noise budget and retry.
        total_noise_budget = max(0, total_noise_budget + delta)

    # Out of iterations: return the closest pack seen as pool_exhausted.
    # (Greedy FFD over a finite discrete pool may not reach arbitrary targets;
    # the realized_fill_pct is logged and downstream analysis can re-bin.)
    if best is not None:
        return BudgetResolution(
            prompt=best[1],
            target_input_tokens=target_input_tokens,
            realized_input_tokens=best[2],
            iterations=iterations,
            pool_exhausted=True,
            is_baseline=run.cell.is_baseline,
        )
    raise BudgetError(
        f"run {run.run_id}: no iteration completed (target {target_input_tokens})"
    )


def _pool_max_tokens(materials: Materials, cell) -> int:
    """Total tokens available in the noise pool usable for this cell."""
    if cell.noise_type is None:
        return 0
    pool = materials.noise.get(cell.noise_type, [])
    if cell.noise_type == "peer_materials":
        pool = [d for d in pool if d.pair_target in (cell.report_id, None)]
    return sum(d.token_count for d in pool)


# ---- helpers -------------------------------------------------------------

def _target_input_tokens(cfg: ExperimentConfig, run: RunSpec, materials: Materials) -> int:
    fill_pct = run.cell.fill_pct
    if fill_pct == 0.0:
        # Baseline: target = realized prompt size with no noise (bundle + system
        # + questions). Uses the same overhead estimate as the noise sizer so
        # the two sides of the tolerance check are computed from the same model.
        return _rough_overhead(cfg, materials, run)
    total = cfg.tokens.total_context_target
    raw = int(total * fill_pct)
    margin = int(raw * cfg.tokens.safety_margin_pct)
    return raw - margin


def _rough_overhead(cfg: ExperimentConfig, materials: Materials, run: RunSpec) -> int:
    """Estimate of non-noise tokens in the prompt (for initial noise sizing)."""
    # System prompt is short; question block is ~1K tokens for 8 questions.
    # Target materials bundle (10-K + earnings call) is the dominant contribution.
    bundle = materials.target_bundles.get(run.cell.report_id)
    bundle_tokens = bundle.combined_token_count if bundle else cfg.tokens.report_token_cap
    return bundle_tokens + 1500  # system ~500 + questions ~1000

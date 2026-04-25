"""
Cost tracker. Converts API usage into dollars and enforces the budget hard-stop.

Pricing is looked up by model-family key in `cfg.cost.pricing`. The analyst
and secondary judge share the `opus_4_7` family; the primary judge is
`sonnet_4_6`; the extractor is `haiku_4_5`.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .api import Usage
from .config import ExperimentConfig, ModelPricing
from .manifest import Manifest, Stage


class BudgetExceeded(RuntimeError):
    """Raised when cumulative cost exceeds the configured hard stop."""


@dataclass(frozen=True)
class RunCost:
    input_usd: float
    cache_read_usd: float
    cache_write_usd: float
    output_usd: float

    @property
    def total_usd(self) -> float:
        return self.input_usd + self.cache_read_usd + self.cache_write_usd + self.output_usd


def compute_cost(usage: Usage, pricing: ModelPricing) -> RunCost:
    # `input_tokens` from the Anthropic API represents uncached input for
    # a given request — cache reads and creations are reported separately.
    return RunCost(
        input_usd=usage.uncached_input_tokens * pricing.input / 1_000_000,
        cache_read_usd=usage.cache_read_input_tokens * pricing.cache_read / 1_000_000,
        cache_write_usd=usage.cache_creation_input_tokens * pricing.cache_write / 1_000_000,
        output_usd=usage.output_tokens * pricing.output / 1_000_000,
    )


class CostTracker:
    """Thread-safe cumulative cost tracker with budget guard."""

    def __init__(self, cfg: ExperimentConfig, manifest: Manifest) -> None:
        self._cfg = cfg
        self._manifest = manifest
        self._lock = threading.Lock()
        self._running_total = manifest.cumulative_cost()

    def record(
        self,
        usage: Usage,
        *,
        component: str,
        model: str,
        run_id: str | None,
        stage: Stage | None,
    ) -> RunCost:
        family = self._cfg.model_family(model)
        pricing = self._cfg.cost.pricing[family]
        cost = compute_cost(usage, pricing)
        self._manifest.log_cost(
            ts=time.time(),
            component=component,
            run_id=run_id,
            stage=stage,
            model=model,
            input_usd=cost.input_usd,
            cache_read_usd=cost.cache_read_usd,
            cache_write_usd=cost.cache_write_usd,
            output_usd=cost.output_usd,
        )
        with self._lock:
            self._running_total += cost.total_usd
        return cost

    def total(self) -> float:
        with self._lock:
            return self._running_total

    def check_budget(self) -> None:
        """Raise BudgetExceeded if the hard stop has been crossed."""
        if self.total() >= self._cfg.cost.hard_stop_usd:
            raise BudgetExceeded(
                f"cumulative cost ${self.total():.2f} >= hard_stop "
                f"${self._cfg.cost.hard_stop_usd:.2f}"
            )

    def budget_remaining(self) -> float:
        return self._cfg.cost.budget_usd - self.total()

    def hard_stop_remaining(self) -> float:
        return self._cfg.cost.hard_stop_usd - self.total()

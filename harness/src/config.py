"""
Experiment config loader.

Loads config/experiment.yaml into strongly-typed dataclasses. Validates only
the invariants that the harness itself depends on — design-level assumptions
(e.g., 15 questions per report) are validated downstream in materials.py.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# --- model configs ---------------------------------------------------------

@dataclass(frozen=True)
class AnalystModelConfig:
    snapshot: str
    context_window: int
    # Opus 4.7 adaptive thinking: effort ∈ {low, medium, high, xhigh, max}.
    # None ⇒ no extended thinking (for models/calls that don't need it).
    thinking_effort: str | None
    max_output_tokens: int
    temperature: float


@dataclass(frozen=True)
class AuxModelConfig:
    """Extractor and judges."""
    snapshot: str
    max_output_tokens: int
    temperature: float
    # Same effort enum as AnalystModelConfig. Judge primary uses "max";
    # Sonnet secondary uses "high"; extractor is None (mechanical task).
    thinking_effort: str | None = None


@dataclass(frozen=True)
class ModelsConfig:
    analyst: AnalystModelConfig
    extractor: AuxModelConfig
    judge_primary: AuxModelConfig
    judge_secondary: AuxModelConfig


# --- design -------------------------------------------------------------

@dataclass(frozen=True)
class DesignConfig:
    fill_levels: tuple[float, ...]
    positions: tuple[str, ...]
    noise_types: tuple[str, ...]
    reports: tuple[str, ...]
    reps_per_cell: int


@dataclass(frozen=True)
class PilotCellOverride:
    report: str
    fill: float
    position: str | None
    noise: str | None


@dataclass(frozen=True)
class PilotConfig:
    cells: tuple[PilotCellOverride, ...]


# --- tokens / execution / cost -------------------------------------------

@dataclass(frozen=True)
class TokensConfig:
    total_context_target: int
    safety_margin_pct: float
    fill_tolerance_tokens: int
    report_token_cap: int
    max_budget_adjustment_iterations: int


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float


@dataclass(frozen=True)
class ExecutionConfig:
    max_concurrent_cells: int
    max_concurrent_extract: int
    max_concurrent_judge: int
    retry: RetryConfig
    cache_ttl_seconds: int
    per_run_timeout_seconds: int


@dataclass(frozen=True)
class PathsConfig:
    materials_dir: Path
    materials_lock: Path
    data_dir: Path
    manifest_db: Path
    raw_dir: Path
    extracted_dir: Path
    graded_dir: Path
    logs_dir: Path


@dataclass(frozen=True)
class ModelPricing:
    input: float
    output: float
    cache_read: float
    cache_write: float


@dataclass(frozen=True)
class CostConfig:
    budget_usd: float
    hard_stop_usd: float
    # Keyed by a model-family label: "opus_4_7" | "sonnet_4_6" | "haiku_4_5"
    pricing: dict[str, ModelPricing]


@dataclass(frozen=True)
class ObservabilityConfig:
    log_level: str
    persist_raw_prompts: bool
    persist_thinking_blocks: bool


# --- root -----------------------------------------------------------------

@dataclass(frozen=True)
class ExperimentConfig:
    name: str
    version: str
    pre_registration_hash: str
    config_path: Path
    config_sha256: str
    models: ModelsConfig
    design: DesignConfig
    pilot: PilotConfig
    tokens: TokensConfig
    execution: ExecutionConfig
    paths: PathsConfig
    cost: CostConfig
    observability: ObservabilityConfig

    def model_family(self, snapshot: str) -> str:
        """Map a snapshot id to a pricing family key."""
        s = snapshot.lower()
        if "opus" in s:
            return "opus_4_7"
        if "sonnet" in s:
            return "sonnet_4_6"
        if "haiku" in s:
            return "haiku_4_5"
        raise ValueError(f"Unknown model family for snapshot {snapshot!r}")


# --- loader ---------------------------------------------------------------

_VALID_EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def _opt_int(v: Any) -> int | None:
    return None if v is None else int(v)


def _opt_effort(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v)
    if s not in _VALID_EFFORTS:
        raise ValueError(f"thinking_effort must be one of {sorted(_VALID_EFFORTS)}, got {s!r}")
    return s


def load_config(path: str | Path) -> ExperimentConfig:
    path = Path(path).resolve()
    text = path.read_text(encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    raw: dict[str, Any] = yaml.safe_load(text)

    # Paths in the YAML are documented as "relative to harness/" (one level up from config/).
    base = path.parent.parent

    def resolve(p: str) -> Path:
        return (base / p).resolve()

    models = ModelsConfig(
        analyst=AnalystModelConfig(
            snapshot=raw["models"]["analyst"]["snapshot"],
            context_window=int(raw["models"]["analyst"]["context_window"]),
            thinking_effort=_opt_effort(raw["models"]["analyst"].get("thinking_effort")),
            max_output_tokens=int(raw["models"]["analyst"]["max_output_tokens"]),
            temperature=float(raw["models"]["analyst"]["temperature"]),
        ),
        extractor=AuxModelConfig(
            snapshot=raw["models"]["extractor"]["snapshot"],
            max_output_tokens=int(raw["models"]["extractor"]["max_output_tokens"]),
            temperature=float(raw["models"]["extractor"]["temperature"]),
            thinking_effort=_opt_effort(raw["models"]["extractor"].get("thinking_effort")),
        ),
        judge_primary=AuxModelConfig(
            snapshot=raw["models"]["judge_primary"]["snapshot"],
            max_output_tokens=int(raw["models"]["judge_primary"]["max_output_tokens"]),
            temperature=float(raw["models"]["judge_primary"]["temperature"]),
            thinking_effort=_opt_effort(raw["models"]["judge_primary"].get("thinking_effort")),
        ),
        judge_secondary=AuxModelConfig(
            snapshot=raw["models"]["judge_secondary"]["snapshot"],
            max_output_tokens=int(raw["models"]["judge_secondary"]["max_output_tokens"]),
            temperature=float(raw["models"]["judge_secondary"]["temperature"]),
            thinking_effort=_opt_effort(raw["models"]["judge_secondary"].get("thinking_effort")),
        ),
    )

    design = DesignConfig(
        fill_levels=tuple(float(f) for f in raw["design"]["fill_levels"]),
        positions=tuple(raw["design"]["positions"]),
        noise_types=tuple(raw["design"]["noise_types"]),
        reports=tuple(raw["design"]["reports"]),
        reps_per_cell=int(raw["design"]["reps_per_cell"]),
    )

    pilot = PilotConfig(
        cells=tuple(
            PilotCellOverride(
                report=c["report"],
                fill=float(c["fill"]),
                position=c.get("position"),
                noise=c.get("noise"),
            )
            for c in raw["pilot"]["cells"]
        ),
    )

    tokens = TokensConfig(
        total_context_target=int(raw["tokens"]["total_context_target"]),
        safety_margin_pct=float(raw["tokens"]["safety_margin_pct"]),
        fill_tolerance_tokens=int(raw["tokens"]["fill_tolerance_tokens"]),
        report_token_cap=int(raw["tokens"]["report_token_cap"]),
        max_budget_adjustment_iterations=int(raw["tokens"]["max_budget_adjustment_iterations"]),
    )

    execution = ExecutionConfig(
        max_concurrent_cells=int(raw["execution"]["max_concurrent_cells"]),
        max_concurrent_extract=int(raw["execution"]["max_concurrent_extract"]),
        max_concurrent_judge=int(raw["execution"]["max_concurrent_judge"]),
        retry=RetryConfig(
            max_attempts=int(raw["execution"]["retry"]["max_attempts"]),
            base_delay_seconds=float(raw["execution"]["retry"]["base_delay_seconds"]),
            max_delay_seconds=float(raw["execution"]["retry"]["max_delay_seconds"]),
        ),
        cache_ttl_seconds=int(raw["execution"]["cache_ttl_seconds"]),
        per_run_timeout_seconds=int(raw["execution"]["per_run_timeout_seconds"]),
    )

    paths = PathsConfig(
        materials_dir=resolve(raw["paths"]["materials_dir"]),
        materials_lock=resolve(raw["paths"]["materials_lock"]),
        data_dir=resolve(raw["paths"]["data_dir"]),
        manifest_db=resolve(raw["paths"]["manifest_db"]),
        raw_dir=resolve(raw["paths"]["raw_dir"]),
        extracted_dir=resolve(raw["paths"]["extracted_dir"]),
        graded_dir=resolve(raw["paths"]["graded_dir"]),
        logs_dir=resolve(raw["paths"]["logs_dir"]),
    )

    cost = CostConfig(
        budget_usd=float(raw["cost"]["budget_usd"]),
        hard_stop_usd=float(raw["cost"]["hard_stop_usd"]),
        pricing={
            family: ModelPricing(
                input=float(p["input"]),
                output=float(p["output"]),
                cache_read=float(p["cache_read"]),
                cache_write=float(p["cache_write"]),
            )
            for family, p in raw["cost"]["pricing"].items()
        },
    )

    obs = ObservabilityConfig(
        log_level=raw["observability"]["log_level"],
        persist_raw_prompts=bool(raw["observability"]["persist_raw_prompts"]),
        persist_thinking_blocks=bool(raw["observability"]["persist_thinking_blocks"]),
    )

    cfg = ExperimentConfig(
        name=raw["experiment"]["name"],
        version=raw["experiment"]["version"],
        pre_registration_hash=raw["experiment"]["pre_registration_hash"],
        config_path=path,
        config_sha256=sha,
        models=models,
        design=design,
        pilot=pilot,
        tokens=tokens,
        execution=execution,
        paths=paths,
        cost=cost,
        observability=obs,
    )
    _validate(cfg)
    return cfg


def _validate(cfg: ExperimentConfig) -> None:
    if cfg.tokens.fill_tolerance_tokens <= 0:
        raise ValueError("fill_tolerance_tokens must be positive")
    if cfg.design.reps_per_cell < 2:
        raise ValueError("reps_per_cell must be >= 2 to measure within-cell variance")
    if 0.0 not in cfg.design.fill_levels:
        raise ValueError("design.fill_levels must include 0.0 (baseline)")
    if cfg.cost.hard_stop_usd <= cfg.cost.budget_usd:
        raise ValueError("hard_stop_usd must exceed budget_usd")
    known_families = {"opus_4_7", "sonnet_4_6", "haiku_4_5"}
    for fam in cfg.cost.pricing:
        if fam not in known_families:
            raise ValueError(f"unknown pricing family {fam!r}")

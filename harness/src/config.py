"""
Experiment config loader.

Primary entry point: load_arm_config(arm_name). Loads config/base.yaml and
config/arms/<arm_name>.yaml, deep-merges them, substitutes the arm name into
path templates, and returns a strongly-typed ExperimentConfig.

Legacy entry: load_config(path) loads a single fully-formed YAML file. Used
by tests and ad-hoc tooling.

Validates only the invariants the harness itself depends on — design-level
assumptions (e.g., 15 questions per report) are validated downstream in
materials.py.
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
    # Anthropic adaptive-thinking knob, effort ∈ {low, medium, high, xhigh, max}.
    # None ⇒ no extended thinking (for models/calls that don't need it). For
    # non-Anthropic vendors this stays None and `thinking_config` carries the
    # vendor-native shape instead.
    thinking_effort: str | None
    max_output_tokens: int
    temperature: float
    # v2 multi-vendor additions — defaulted so v1 Anthropic arm configs continue
    # to load unchanged. See MULTI_VENDOR_ADDENDUM.md §7.
    vendor: str = "anthropic"
    snapshot_note: str = ""
    # Vendor-native thinking config — opaque dict passed through to the adapter.
    # Examples: {"reasoning": {"effort": "xhigh"}} for OpenAI,
    # {"thinking_level": "high"} for Gemini, {"reasoning_effort": "max"} for
    # DeepSeek if accepted. Anthropic ignores this and uses thinking_effort.
    thinking_config: dict[str, Any] | None = None


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
    arm_name: str                    # which analyst arm — drives output paths
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
        if "gpt-5.5" in s or "gpt5.5" in s:
            return "gpt_5_5"
        if "gemini-3" in s:
            return "gemini_3_1_pro"
        if "deepseek" in s:
            return "deepseek_v4_pro"
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


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge `overlay` into a copy of `base`. Leaf values from
    overlay replace base. Lists are replaced (not concatenated)."""
    out = dict(base)
    for key, val in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _substitute_arm_in_paths(paths: dict[str, Any], arm_name: str) -> dict[str, Any]:
    """Replace `{arm}` placeholder in path strings with the arm name."""
    return {k: (v.replace("{arm}", arm_name) if isinstance(v, str) else v)
            for k, v in paths.items()}


def load_arm_config(arm_name: str, config_root: Path | str | None = None) -> ExperimentConfig:
    """Load harness/config/base.yaml + harness/config/arms/{arm_name}.yaml,
    deep-merge them, substitute {arm} in path strings, and return the
    resulting ExperimentConfig.

    The merged config's SHA-256 hash is computed over the concatenation
    `<base.yaml bytes>\\n---\\n<arm.yaml bytes>` so reproducing the same hash
    requires both files unchanged.
    """
    if config_root is None:
        config_root = Path(__file__).resolve().parents[1] / "config"
    config_root = Path(config_root).resolve()
    base_path = config_root / "base.yaml"
    arm_path = config_root / "arms" / f"{arm_name}.yaml"

    if not base_path.exists():
        raise FileNotFoundError(f"missing base config: {base_path}")
    if not arm_path.exists():
        raise FileNotFoundError(f"missing arm config: {arm_path}")

    base_text = base_path.read_text(encoding="utf-8")
    arm_text = arm_path.read_text(encoding="utf-8")
    base_raw = yaml.safe_load(base_text)
    arm_raw = yaml.safe_load(arm_text)

    if not arm_raw or "arm" not in arm_raw or "name" not in arm_raw["arm"]:
        raise ValueError(f"{arm_path}: must declare arm.name at top level")
    declared_name = arm_raw["arm"]["name"]
    if declared_name != arm_name:
        raise ValueError(
            f"{arm_path}: arm.name={declared_name!r} does not match requested arm {arm_name!r} — "
            f"file path and declared name must agree"
        )

    merged = _deep_merge(base_raw, arm_raw)
    if "paths" in merged:
        merged["paths"] = _substitute_arm_in_paths(merged["paths"], arm_name)

    combined_text = base_text + "\n---\n# arm overlay:\n" + arm_text
    sha = hashlib.sha256(combined_text.encode("utf-8")).hexdigest()

    # Resolve paths relative to harness/ (one level up from config/).
    base_dir = config_root.parent
    return _build_config(merged, sha, arm_path, arm_name, base_dir)


def load_config(path: str | Path) -> ExperimentConfig:
    """Load a single-file experiment config (legacy / direct-loading mode).

    Intended for tests and ad-hoc scripts that want to pass a fully-formed
    YAML file without going through arm-overlay merging. Production scripts
    should use load_arm_config(arm_name) instead.

    The arm name is read from the yaml's `arm.name` field; if absent, defaults
    to "default" and a warning is logged.
    """
    path = Path(path).resolve()
    text = path.read_text(encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    raw: dict[str, Any] = yaml.safe_load(text)

    arm_name = raw.get("arm", {}).get("name", "default") if isinstance(raw.get("arm"), dict) else "default"
    if "paths" in raw:
        raw["paths"] = _substitute_arm_in_paths(raw["paths"], arm_name)

    base_dir = path.parent.parent
    return _build_config(raw, sha, path, arm_name, base_dir)


def _build_config(
    raw: dict[str, Any],
    sha: str,
    config_path: Path,
    arm_name: str,
    base_dir: Path,
) -> ExperimentConfig:
    def resolve(p: str) -> Path:
        return (base_dir / p).resolve()

    analyst_raw = raw["models"]["analyst"]
    models = ModelsConfig(
        analyst=AnalystModelConfig(
            snapshot=analyst_raw["snapshot"],
            context_window=int(analyst_raw["context_window"]),
            thinking_effort=_opt_effort(analyst_raw.get("thinking_effort")),
            max_output_tokens=int(analyst_raw["max_output_tokens"]),
            temperature=float(analyst_raw["temperature"]),
            vendor=str(analyst_raw.get("vendor", "anthropic")).lower(),
            snapshot_note=str(analyst_raw.get("snapshot_note", "")),
            thinking_config=analyst_raw.get("thinking_config"),
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
        arm_name=arm_name,
        config_path=config_path,
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


_KNOWN_VENDORS = {"anthropic", "openai", "google", "deepseek"}
_KNOWN_PRICING_FAMILIES = {
    "opus_4_7", "sonnet_4_6", "haiku_4_5",
    "gpt_5_5", "gemini_3_1_pro", "deepseek_v4_pro",
}


def _validate(cfg: ExperimentConfig) -> None:
    if not cfg.arm_name or "/" in cfg.arm_name or cfg.arm_name.startswith("."):
        raise ValueError(f"invalid arm_name {cfg.arm_name!r} — must be filename-safe")
    if cfg.tokens.fill_tolerance_tokens <= 0:
        raise ValueError("fill_tolerance_tokens must be positive")
    if cfg.design.reps_per_cell < 2:
        raise ValueError("reps_per_cell must be >= 2 to measure within-cell variance")
    if 0.0 not in cfg.design.fill_levels:
        raise ValueError("design.fill_levels must include 0.0 (baseline)")
    if cfg.cost.hard_stop_usd <= cfg.cost.budget_usd:
        raise ValueError("hard_stop_usd must exceed budget_usd")
    if cfg.models.analyst.vendor not in _KNOWN_VENDORS:
        raise ValueError(
            f"unknown analyst vendor {cfg.models.analyst.vendor!r} — must be one of "
            f"{sorted(_KNOWN_VENDORS)}"
        )
    # Anthropic vendor: thinking_effort is the canonical knob; thinking_config
    # should be None (the YAML may set it but the adapter ignores it).
    # Non-Anthropic vendor: thinking_effort must be None and thinking_config
    # carries the vendor-native shape.
    if cfg.models.analyst.vendor != "anthropic":
        if cfg.models.analyst.thinking_effort is not None:
            raise ValueError(
                f"vendor={cfg.models.analyst.vendor!r} must use thinking_config, "
                f"not thinking_effort (got {cfg.models.analyst.thinking_effort!r})"
            )
    for fam in cfg.cost.pricing:
        if fam not in _KNOWN_PRICING_FAMILIES:
            raise ValueError(
                f"unknown pricing family {fam!r} — must be one of "
                f"{sorted(_KNOWN_PRICING_FAMILIES)}"
            )

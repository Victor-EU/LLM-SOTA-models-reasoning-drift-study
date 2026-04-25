"""
One-shot API schema probe. Answers:
  1. Do the model IDs (opus 4.7 / sonnet 4.6 / haiku 4.5) resolve?
  2. Is thinking schema `budget_tokens` or `adaptive`? Is `effort` a param?
  3. How does the Usage object surface thinking tokens?
  4. Is a `context-1m` beta header needed for 1M context or is it GA?

Total cost: < $0.01. Non-cost count_tokens calls + 2-3 tiny messages.create
calls with max_tokens=512.

Usage:
    python -m scripts.probe_api
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

HARNESS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS_ROOT))

load_dotenv()

from anthropic import Anthropic  # noqa: E402


def _box(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def _safe(label: str, fn) -> None:
    try:
        result = fn()
        print(f"  [OK] {label}")
        if result:
            for k, v in result.items():
                print(f"       {k}: {v}")
    except Exception as e:
        print(f"  [FAIL] {label}: {type(e).__name__}: {e}")


def main() -> int:
    c = Anthropic()
    print(f"anthropic SDK: {__import__('anthropic').__version__}")

    # ---- 1. model IDs ----
    _box("1. Model ID resolution (count_tokens is free)")

    def _check(model: str):
        r = c.messages.count_tokens(model=model, messages=[{"role": "user", "content": "hi"}])
        return {"input_tokens": r.input_tokens}

    _safe("claude-opus-4-7", lambda: _check("claude-opus-4-7"))
    _safe("claude-sonnet-4-6", lambda: _check("claude-sonnet-4-6"))
    _safe("claude-haiku-4-5-20251001", lambda: _check("claude-haiku-4-5-20251001"))
    _safe("claude-haiku-4-5 (alias)", lambda: _check("claude-haiku-4-5"))

    # ---- 2. thinking schema: budget_tokens ----
    _box("2a. Thinking schema: {type: enabled, budget_tokens: 1024}")

    def _call_budget():
        r = c.messages.create(
            model="claude-opus-4-7",
            max_tokens=2048,
            temperature=1.0,
            thinking={"type": "enabled", "budget_tokens": 1024},
            messages=[{"role": "user", "content": "What is 2+2? Think briefly."}],
        )
        thinking_blocks = [b for b in r.content if getattr(b, "type", None) == "thinking"]
        text_blocks = [b for b in r.content if getattr(b, "type", None) == "text"]
        return {
            "stop_reason": r.stop_reason,
            "output_tokens": r.usage.output_tokens,
            "usage.thinking_tokens attr": getattr(r.usage, "thinking_tokens", "<no attribute>"),
            "content block types": [getattr(b, "type", "?") for b in r.content],
            "n thinking blocks": len(thinking_blocks),
            "n text blocks": len(text_blocks),
            "first thinking chars": (getattr(thinking_blocks[0], "thinking", "")[:80]
                                     if thinking_blocks else "<none>"),
        }

    _safe("budget_tokens schema", _call_budget)

    # ---- 2b. thinking schema: adaptive ----
    _box("2b. Thinking schema: {type: adaptive}")

    def _call_adaptive():
        r = c.messages.create(
            model="claude-opus-4-7",
            max_tokens=2048,
            temperature=1.0,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": "What is 2+2?"}],
        )
        return {
            "stop_reason": r.stop_reason,
            "output_tokens": r.usage.output_tokens,
            "content block types": [getattr(b, "type", "?") for b in r.content],
        }

    _safe("adaptive schema", _call_adaptive)

    # ---- 2c. thinking schema: adaptive + effort ----
    _box("2c. Thinking schema: {type: adaptive, effort: high}")

    def _call_adaptive_effort():
        r = c.messages.create(
            model="claude-opus-4-7",
            max_tokens=2048,
            temperature=1.0,
            thinking={"type": "adaptive", "effort": "high"},
            messages=[{"role": "user", "content": "What is 2+2?"}],
        )
        return {
            "stop_reason": r.stop_reason,
            "output_tokens": r.usage.output_tokens,
            "content block types": [getattr(b, "type", "?") for b in r.content],
        }

    _safe("adaptive+effort schema", _call_adaptive_effort)

    # ---- 3. High budget on Opus 4.7 (xhigh ~ 32k) ----
    _box("3. High-budget thinking (32K) on Opus 4.7")

    def _call_high():
        r = c.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            temperature=1.0,
            thinking={"type": "enabled", "budget_tokens": 32768},
            messages=[{"role": "user", "content": "Explain why 7 is a prime in one paragraph."}],
        )
        return {
            "stop_reason": r.stop_reason,
            "output_tokens": r.usage.output_tokens,
            "usage.thinking_tokens attr": getattr(r.usage, "thinking_tokens", "<no attribute>"),
        }

    _safe("32K budget_tokens on opus-4.7", _call_high)

    # ---- 4. 1M context beta header ----
    _box("4. 1M context: beta header required?")

    def _no_beta():
        # Just attempting to count tokens on a request nominally 1M-scale
        # context isn't conclusive without creating a giant request. The
        # real test is whether messages.create rejects oversized context
        # without the beta. We'll check count_tokens with a fake large
        # input and inspect for any "context too large" error patterns.
        big = "x " * 100_000  # 200k-char user msg; ~50k tokens
        r = c.messages.count_tokens(model="claude-opus-4-7",
                                     messages=[{"role": "user", "content": big}])
        return {"input_tokens": r.input_tokens, "note": "count_tokens accepts large inputs regardless"}

    _safe("count_tokens with 50K user msg", _no_beta)

    print()
    print("=" * 70)
    print("Probe complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

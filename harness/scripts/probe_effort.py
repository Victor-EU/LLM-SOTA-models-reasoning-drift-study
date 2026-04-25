"""
Follow-up probe: discover valid `output_config.effort` values for a given
Claude snapshot's adaptive thinking, and confirm how thinking telemetry
surfaces in responses.

Tests a prompt that invites real reasoning, across candidate effort levels.
For each, reports: stop_reason, total output_tokens, thinking block count,
per-block chars (proxy for thinking depth), any thinking_tokens attr.

Total cost: < $0.10 per model (5-9 short messages.create calls).

Usage:
    python -m scripts.probe_effort                                # default opus
    python -m scripts.probe_effort --model claude-sonnet-4-6      # probe Sonnet
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

HARNESS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS_ROOT))

load_dotenv()

from anthropic import Anthropic  # noqa: E402


REASONING_PROMPT = (
    "I have two sequences:\n"
    "  A: 2, 6, 12, 20, 30, ...\n"
    "  B: 1, 4, 9, 16, 25, ...\n"
    "For what smallest n > 100 does A[n] - B[n] = n? Show your reasoning."
)


def _try_effort(c, model: str, effort: str | None) -> dict:
    kwargs = dict(
        model=model,
        max_tokens=2048,
        temperature=1.0,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": REASONING_PROMPT}],
    )
    if effort is not None:
        kwargs["extra_body"] = {"output_config": {"effort": effort}}
    r = c.messages.create(**kwargs)
    thinking_blocks = [b for b in r.content if getattr(b, "type", None) == "thinking"]
    text_blocks = [b for b in r.content if getattr(b, "type", None) == "text"]
    return {
        "stop_reason": r.stop_reason,
        "output_tokens": r.usage.output_tokens,
        "input_tokens": r.usage.input_tokens,
        "usage.thinking_tokens": getattr(r.usage, "thinking_tokens", "<no attr>"),
        "n_thinking_blocks": len(thinking_blocks),
        "n_text_blocks": len(text_blocks),
        "total_thinking_chars": sum(len(getattr(b, "thinking", "")) for b in thinking_blocks),
        "first_text_chars": (text_blocks[0].text[:120] if text_blocks else "<none>"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="claude-opus-4-7", help="snapshot to probe")
    parser.add_argument("--efforts", default="low,medium,high,xhigh,max",
                        help="comma-separated effort values to probe (use 'none' for unset baseline)")
    args = parser.parse_args()

    c = Anthropic()
    print(f"Probing model: {args.model}")
    print(f"Effort candidates: {args.efforts}")

    candidates: list[str | None] = []
    for tok in args.efforts.split(","):
        tok = tok.strip()
        candidates.append(None if tok in ("", "none") else tok)
    if None not in candidates:
        candidates.insert(0, None)   # always include unset baseline

    results: dict[str, dict | str] = {}
    for eff in candidates:
        label = f"effort={eff!r}" if eff is not None else "no effort set (default)"
        print()
        print("=" * 70)
        print(label)
        print("=" * 70)
        try:
            result = _try_effort(c, args.model, eff)
            results[label] = result
            for k, v in result.items():
                print(f"  {k}: {v}")
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            results[label] = msg
            print(f"  FAILED: {msg}")

    # Summary table
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for label, r in results.items():
        if isinstance(r, dict):
            print(f"  {label:<40} OK  tokens_out={r['output_tokens']:>5}  "
                  f"think_blocks={r['n_thinking_blocks']}  "
                  f"think_chars={r['total_thinking_chars']}")
        else:
            # Surface only the message, not full repr
            err_msg = r.split(" - ", 1)[-1][:120] if " - " in r else r[:120]
            print(f"  {label:<40} FAIL  {err_msg}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Anthropic API wrapper with retry/backoff, thinking configuration, and
uniform usage extraction.

All analyst, extractor, and judge calls route through `call_messages`.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

from anthropic import (
    APIConnectionError,
    APIStatusError,
    AsyncAnthropic,
    RateLimitError,
)

from .assembly import AssembledPrompt
from .config import ExperimentConfig, RetryConfig

log = logging.getLogger(__name__)


# ---- uniform response shape ----------------------------------------------

@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    # Thinking-token accounting. Anthropic currently bundles thinking into
    # output_tokens; the SDK does not always surface a separate counter. We
    # populate this from the SDK if available, otherwise from a char/4
    # estimate of concatenated thinking blocks. `thinking_tokens_source`
    # preserves provenance so downstream analysis can filter or flag.
    thinking_tokens: int | None
    thinking_tokens_source: str | None = None   # "sdk" | "estimated_char_per_4" | None

    @property
    def uncached_input_tokens(self) -> int:
        return max(0, self.input_tokens - self.cache_read_input_tokens)


@dataclass(frozen=True)
class CallResult:
    # Raw content blocks from the API (mix of text + thinking).
    content: list[dict[str, Any]]
    # Concatenated text from type="text" blocks (analyst answer body).
    text: str
    # Concatenated text from type="thinking" blocks, if exposed.
    thinking_text: str
    stop_reason: str | None
    model: str
    usage: Usage
    latency_seconds: float
    attempts: int
    request_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


# ---- retry helpers -------------------------------------------------------

def _is_retriable(exc: BaseException) -> bool:
    if isinstance(exc, (RateLimitError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        return 500 <= int(getattr(exc, "status_code", 0)) < 600
    return False


def _backoff(attempt: int, cfg: RetryConfig) -> float:
    base = cfg.base_delay_seconds * (2 ** (attempt - 1))
    jitter = random.uniform(0.8, 1.2)
    return min(base * jitter, cfg.max_delay_seconds)


# ---- main call -----------------------------------------------------------

async def call_messages(
    client: AsyncAnthropic,
    *,
    model: str,
    system: list[dict[str, Any]] | None,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    thinking_effort: str | None,
    extra_headers: dict[str, str] | None,
    retry: RetryConfig,
    per_call_timeout_seconds: int,
) -> CallResult:
    """
    Single Anthropic call with retry. Used by all three pipeline stages.

    Opus 4.7 schema: thinking={"type": "adaptive"} with the effort controlled
    via top-level output_config.effort (passed through extra_body since the
    SDK may not yet have first-class output_config support). Empirically
    verified against claude-opus-4-7 on 2026-04-24 (scripts/probe_effort.py).

    Always streams: with max_tokens >=~16K the SDK refuses non-streaming
    requests (10-min nonstreaming timeout cap), and analyst/judge calls run
    Opus at effort=max which can spend many minutes. Streaming is functionally
    equivalent — we accumulate and return the final message in the same shape.
    """
    thinking: dict[str, Any] | None = None
    extra_body: dict[str, Any] | None = None
    if thinking_effort:
        thinking = {"type": "adaptive"}
        extra_body = {"output_config": {"effort": thinking_effort}}

    attempt = 0
    t_start_total = time.monotonic()

    while True:
        attempt += 1
        t0 = time.monotonic()
        try:
            kwargs: dict[str, Any] = dict(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if system is not None:
                kwargs["system"] = system
            if thinking is not None:
                kwargs["thinking"] = thinking
            if extra_body is not None:
                kwargs["extra_body"] = extra_body
            if extra_headers:
                kwargs["extra_headers"] = extra_headers

            response = await asyncio.wait_for(
                _stream_to_final(client, kwargs),
                timeout=per_call_timeout_seconds,
            )
            latency = time.monotonic() - t0
            return _extract(response, latency=latency, attempts=attempt)

        except Exception as e:  # noqa: BLE001 — intentional broad catch, classified below
            if not _is_retriable(e) or attempt >= retry.max_attempts:
                log.warning(
                    "api call failed after %d attempts (%.1fs total): %s",
                    attempt, time.monotonic() - t_start_total, e,
                )
                raise
            delay = _backoff(attempt, retry)
            log.info("api retry %d/%d in %.1fs: %s", attempt, retry.max_attempts, delay, e)
            await asyncio.sleep(delay)


async def _stream_to_final(client: AsyncAnthropic, kwargs: dict[str, Any]) -> Any:
    """Open a streaming context, drain events, return the final assembled message."""
    async with client.messages.stream(**kwargs) as stream:
        async for _ in stream:
            pass
        return await stream.get_final_message()


# ---- response extraction -------------------------------------------------

def _extract(response: Any, latency: float, attempts: int) -> CallResult:
    blocks: list[dict[str, Any]] = []
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    # Encrypted thinking signature lengths — Opus 4.7 redacts thinking text
    # but exposes an encrypted `signature` (~1 base64 char per source byte).
    # Total signature length is the only first-class proxy we have for
    # thinking depth across reps/cells.
    signature_chars: int = 0
    n_thinking_blocks: int = 0

    for block in getattr(response, "content", []):
        btype = getattr(block, "type", None)
        if btype == "text":
            txt = getattr(block, "text", "")
            blocks.append({"type": "text", "text": txt})
            text_parts.append(txt)
        elif btype == "thinking":
            # Plaintext thinking (empty when redacted by Opus 4.7).
            txt = getattr(block, "thinking", None) or ""
            sig = getattr(block, "signature", None) or ""
            n_thinking_blocks += 1
            signature_chars += len(sig)
            blocks.append({"type": "thinking", "text": txt, "signature_chars": len(sig)})
            thinking_parts.append(txt)
        else:
            blocks.append({"type": btype or "unknown", "raw": repr(block)})

    usage_obj = getattr(response, "usage", None)
    sdk_thinking = getattr(usage_obj, "thinking_tokens", None)
    if sdk_thinking is not None:
        thinking_tokens: int | None = int(sdk_thinking)
        thinking_source: str | None = "sdk"
    elif thinking_parts and any(p for p in thinking_parts):
        # Plaintext thinking present — char/4 estimate.
        total_chars = sum(len(p) for p in thinking_parts)
        thinking_tokens = max(1, total_chars // 4)
        thinking_source = "estimated_char_per_4"
    elif signature_chars > 0:
        # Redacted thinking — signature is base64-encoded ciphertext. Signature
        # length is the only available proxy for thinking depth. Calibrate
        # downstream against output_tokens deltas vs. a no-thinking control.
        thinking_tokens = signature_chars // 4
        thinking_source = "estimated_signature_chars_per_4"
    else:
        thinking_tokens = None
        thinking_source = None

    usage = Usage(
        input_tokens=getattr(usage_obj, "input_tokens", 0) or 0,
        output_tokens=getattr(usage_obj, "output_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(usage_obj, "cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=getattr(usage_obj, "cache_read_input_tokens", 0) or 0,
        thinking_tokens=thinking_tokens,
        thinking_tokens_source=thinking_source,
    )

    return CallResult(
        content=blocks,
        text="".join(text_parts),
        thinking_text="".join(thinking_parts),
        stop_reason=getattr(response, "stop_reason", None),
        model=getattr(response, "model", "") or "",
        usage=usage,
        latency_seconds=latency,
        attempts=attempts,
        request_id=getattr(response, "_request_id", None)
                   or getattr(response, "id", None),
    )


# ---- convenience: analyst call ------------------------------------------

async def run_analyst(
    client: AsyncAnthropic,
    prompt: AssembledPrompt,
    cfg: ExperimentConfig,
) -> CallResult:
    # Opus 4.7 1M context + prompt caching are both GA — no anthropic-beta
    # header required. The model is `claude-opus-4-7`.
    return await call_messages(
        client=client,
        model=cfg.models.analyst.snapshot,
        system=prompt.system,
        messages=prompt.messages,
        max_tokens=cfg.models.analyst.max_output_tokens,
        temperature=cfg.models.analyst.temperature,
        thinking_effort=cfg.models.analyst.thinking_effort,
        extra_headers=None,
        retry=cfg.execution.retry,
        per_call_timeout_seconds=cfg.execution.per_run_timeout_seconds,
    )

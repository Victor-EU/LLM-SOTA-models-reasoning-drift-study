"""
Vendor-agnostic analyst API + Anthropic-only utility (extractor / judge).

Two layers:
  1. `call_messages` — Anthropic streaming wrapper used by the extractor and
     both judges. Always Anthropic; not vendor-dispatched.
  2. `AnalystClient` ABC — vendor-dispatched analyst-call adapter. Subclasses
     for Anthropic / OpenAI / Google / DeepSeek. Constructed via
     `make_analyst_client(cfg, anthropic_client)`.

Backward compat: `run_analyst(client, prompt, cfg)` is preserved as a
function that delegates to `AnthropicAnalystClient` so existing call sites
(`runner.py`) continue to work for v1 (Anthropic-only) arms without edits.

Schema discipline: all four adapters return the same `CallResult` shape.
Vendor-specific accounting (DeepSeek `system_fingerprint`, OpenAI
`encrypted_content` length, Gemini thought-signature length) lands in the
existing `signature_chars` slot or in `extra` — no shape divergence.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx
from anthropic import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    InternalServerError,
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
    thinking_tokens_source: str | None = None   # "sdk" | "estimated_char_per_4" | "estimated_signature_chars_per_4" | None

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
    # Sonnet/DeepSeek populate this; Opus/Gemini/OpenAI leave it empty.
    thinking_text: str
    stop_reason: str | None
    model: str
    usage: Usage
    latency_seconds: float
    attempts: int
    request_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    # v2 multi-vendor additions — all default-valued for back-compat.
    vendor: str = "anthropic"
    system_fingerprint: str | None = None  # OpenAI / DeepSeek build identifier; None for vendors that don't expose it


# ---- retry helpers -------------------------------------------------------

def _is_retriable_anthropic(exc: BaseException) -> bool:
    """Anthropic-SDK + httpx-base retry classifier."""
    if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)):
        return True
    if isinstance(exc, APIStatusError):
        return 500 <= int(getattr(exc, "status_code", 0)) < 600
    # httpx-level transient streaming errors. Long Sonnet/Opus calls (5-15 min)
    # frequently see the upstream connection drop mid-response — the server
    # accepted the request but the chunked stream was cut. Always retriable.
    if isinstance(exc, (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout,
                        httpx.WriteError, httpx.ConnectError, httpx.ConnectTimeout,
                        httpx.PoolTimeout)):
        return True
    # Last-resort: anthropic.APIError whose message looks like a transient
    # network/stream failure. Catches edge cases where the SDK wraps the
    # underlying httpx error in a custom type without preserving the type info.
    if isinstance(exc, APIError):
        msg = str(exc).lower()
        for marker in ("peer closed", "incomplete chunked", "connection reset",
                       "connection aborted", "stream", "remote protocol"):
            if marker in msg:
                return True
    return False


# Public alias preserved for any downstream code that imported _is_retriable.
_is_retriable = _is_retriable_anthropic


def _backoff(attempt: int, cfg: RetryConfig) -> float:
    base = cfg.base_delay_seconds * (2 ** (attempt - 1))
    jitter = random.uniform(0.8, 1.2)
    return min(base * jitter, cfg.max_delay_seconds)


# ---- main Anthropic call (extractor / judge / Anthropic-analyst) --------

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
    Single Anthropic call with retry. Used by extractor + both judges + the
    Anthropic analyst adapter.

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
            return _extract_anthropic(response, latency=latency, attempts=attempt)

        except Exception as e:  # noqa: BLE001 — intentional broad catch, classified below
            if not _is_retriable_anthropic(e) or attempt >= retry.max_attempts:
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


# ---- Anthropic response extraction --------------------------------------

def _extract_anthropic(response: Any, latency: float, attempts: int) -> CallResult:
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
        vendor="anthropic",
        system_fingerprint=None,  # Anthropic does not expose a per-call build id
    )


# ---- vendor-agnostic prompt flattener (for non-Anthropic adapters) ------

def _flatten_anthropic_prompt(prompt: AssembledPrompt) -> tuple[str, str]:
    """Concatenate the Anthropic-shaped system + user content blocks into
    plain (instructions, user_input) strings.

    Used by all non-Anthropic adapters. The materials and prompt assembly
    are identical across arms (apples-to-apples constraint); the only
    transformation is dropping cache_control hints (non-Anthropic vendors
    auto-cache via prefix matching, or do not cache at all). Tokenizer
    differences vs. Anthropic are disclosed per arm in tokenizer_note —
    see MULTI_VENDOR_ADDENDUM.md §4.
    """
    instructions_parts: list[str] = []
    for block in prompt.system or []:
        if isinstance(block, dict) and block.get("type") == "text":
            instructions_parts.append(block.get("text", "") or "")
    instructions = "\n\n".join(p for p in instructions_parts if p)

    user_parts: list[str] = []
    for msg in prompt.messages or []:
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            user_parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    user_parts.append(block.get("text", "") or "")
    user_input = "\n\n".join(p for p in user_parts if p)
    return instructions, user_input


# ---- OpenAI retry classifier + streaming finalizer + extractor ----------

def _is_retriable_openai(exc: BaseException) -> bool:
    """OpenAI-SDK + httpx-base retry classifier. Mirrors _is_retriable_anthropic."""
    try:
        from openai import (
            APIConnectionError as OAIAPIConnectionError,
            APIStatusError as OAIAPIStatusError,
            APITimeoutError as OAIAPITimeoutError,
            InternalServerError as OAIInternalServerError,
            RateLimitError as OAIRateLimitError,
        )
    except ImportError:
        # SDK not installed — caller is on a vendor that doesn't need it,
        # so the exception clearly isn't an OpenAI SDK exception.
        OAIRateLimitError = OAIAPIConnectionError = OAIAPITimeoutError = ()
        OAIInternalServerError = OAIAPIStatusError = ()

    if OAIRateLimitError and isinstance(
        exc,
        (OAIRateLimitError, OAIAPIConnectionError, OAIAPITimeoutError, OAIInternalServerError),
    ):
        return True
    if OAIAPIStatusError and isinstance(exc, OAIAPIStatusError):
        sc = getattr(exc, "status_code", 0)
        if isinstance(sc, int) and 500 <= sc < 600:
            return True
    # httpx-level transient errors (same pool as Anthropic).
    if isinstance(exc, (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout,
                        httpx.WriteError, httpx.ConnectError, httpx.ConnectTimeout,
                        httpx.PoolTimeout)):
        return True
    # OpenAI Responses streaming has been observed to occasionally drain to
    # completion without ever emitting a `response.completed` event — measured
    # at ~3% on gpt-5.5 xhigh during the v3 full-grid run (2026-05-05). The
    # call returns 200, the stream closes cleanly, but the assembled response
    # never lands. _openai_stream_to_final raises a custom RuntimeError on
    # this; treat as transient and retry. Real model errors surface as OAI
    # exceptions and won't match this string.
    if isinstance(exc, RuntimeError) and "response.completed" in str(exc):
        return True
    return False


async def _openai_stream_to_final(
    client: Any,
    *,
    model: str,
    instructions: str,
    input_text: str,
    reasoning: dict[str, Any],
    max_output_tokens: int,
    temperature: float,
) -> Any:
    """Open the OpenAI Responses streaming API, drain events, return the
    final assembled Response object.

    Uses `responses.create(..., stream=True)` for explicit async streaming
    rather than the sync `responses.stream(...)` context manager. Listens
    for the `response.completed` event which carries the fully-assembled
    final response.
    """
    stream = await client.responses.create(
        model=model,
        instructions=instructions,
        input=input_text,
        reasoning=reasoning,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        # Encrypted reasoning blob is the only thinking-depth proxy OpenAI
        # exposes (raw CoT is redacted). We capture the blob length per
        # reasoning item — analogous to Anthropic Opus signature_chars.
        include=["reasoning.encrypted_content"],
        stream=True,
    )
    final_response: Any = None
    async for event in stream:
        etype = getattr(event, "type", None)
        if etype == "response.completed":
            final_response = getattr(event, "response", None)
        # All other event types are streaming deltas — drain and ignore;
        # the final assembled response is what we return.
    if final_response is None:
        raise RuntimeError(
            "OpenAI Responses stream completed without a response.completed event"
        )
    return final_response


def _extract_openai(response: Any, latency: float, attempts: int) -> CallResult:
    """Map OpenAI Responses API response → CallResult.

    Output-item schema (per Responses API):
      output[].type == "message"   → content[].type == "output_text" carries text
      output[].type == "reasoning" → summary[].text carries synthetic summary;
                                     encrypted_content carries the opaque blob
    """
    blocks: list[dict[str, Any]] = []
    text_parts: list[str] = []
    reasoning_summary_parts: list[str] = []
    encrypted_chars_total: int = 0

    output_items = getattr(response, "output", None) or []
    for item in output_items:
        itype = getattr(item, "type", None)
        if itype == "message":
            content_arr = getattr(item, "content", None) or []
            for c in content_arr:
                ctype = getattr(c, "type", None)
                if ctype == "output_text":
                    txt = getattr(c, "text", "") or ""
                    blocks.append({"type": "text", "text": txt})
                    text_parts.append(txt)
                elif ctype == "refusal":
                    refusal = getattr(c, "refusal", "") or ""
                    blocks.append({"type": "refusal", "text": refusal})
        elif itype == "reasoning":
            summary_arr = getattr(item, "summary", None) or []
            summary_text = ""
            for s in summary_arr:
                stype = getattr(s, "type", None)
                if stype == "summary_text":
                    t = getattr(s, "text", "") or ""
                    summary_text += t
                    reasoning_summary_parts.append(t)
            enc = getattr(item, "encrypted_content", None) or ""
            enc_chars = len(enc)
            encrypted_chars_total += enc_chars
            blocks.append({
                "type": "reasoning",
                "text": summary_text,
                "encrypted_chars": enc_chars,
            })
        else:
            blocks.append({"type": itype or "unknown", "raw": repr(item)})

    usage_obj = getattr(response, "usage", None)
    input_tokens = int(getattr(usage_obj, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage_obj, "output_tokens", 0) or 0)

    cached_tokens = 0
    in_details = getattr(usage_obj, "input_tokens_details", None)
    if in_details is not None:
        cached_tokens = int(getattr(in_details, "cached_tokens", 0) or 0)

    reasoning_tokens: int | None = None
    out_details = getattr(usage_obj, "output_tokens_details", None)
    if out_details is not None:
        rt = getattr(out_details, "reasoning_tokens", None)
        if rt is not None:
            reasoning_tokens = int(rt)

    usage = Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        # OpenAI auto-prefix-caches; no separate "cache write" cost like
        # Anthropic. Charging maps cache_read_input_tokens → pricing.cache_read.
        cache_creation_input_tokens=0,
        cache_read_input_tokens=cached_tokens,
        thinking_tokens=reasoning_tokens,
        thinking_tokens_source="sdk" if reasoning_tokens is not None else None,
    )

    return CallResult(
        content=blocks,
        text="".join(text_parts),
        # synthetic summary text — NOT raw CoT (OpenAI redacts the latter)
        thinking_text="".join(reasoning_summary_parts),
        stop_reason=getattr(response, "status", None)
                    or getattr(response, "stop_reason", None),
        model=getattr(response, "model", "") or "",
        usage=usage,
        latency_seconds=latency,
        attempts=attempts,
        request_id=getattr(response, "_request_id", None)
                   or getattr(response, "id", None),
        vendor="openai",
        system_fingerprint=getattr(response, "system_fingerprint", None),
        extra={"encrypted_chars_total": encrypted_chars_total},
    )


# ---- Gemini retry classifier + streaming finalizer + extractor ----------

def _is_retriable_gemini(exc: BaseException) -> bool:
    """google-genai SDK + httpx-base retry classifier."""
    try:
        from google.genai import errors as gerrors
        ServerError = getattr(gerrors, "ServerError", None)
        ClientError = getattr(gerrors, "ClientError", None)
    except ImportError:
        ServerError = ClientError = None

    if ServerError is not None and isinstance(exc, ServerError):
        return True
    if ClientError is not None and isinstance(exc, ClientError):
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None) or 0
        if isinstance(code, int) and code == 429:
            return True
    if isinstance(exc, (httpx.RemoteProtocolError, httpx.ReadError, httpx.ReadTimeout,
                        httpx.WriteError, httpx.ConnectError, httpx.ConnectTimeout,
                        httpx.PoolTimeout)):
        return True
    return False


async def _gemini_stream_to_final(
    client: Any,
    *,
    model: str,
    contents: str,
    config: Any,
) -> dict[str, Any]:
    """Drain a Gemini streaming generation, return assembled state.

    Each streaming chunk carries delta parts; the final chunk carries
    `usage_metadata` totals. Thought parts (when include_thoughts=True)
    carry `thought_signature` (opaque bytes); we sum signature lengths
    across chunks as the thinking-depth proxy.
    """
    text_segments: list[str] = []
    thought_segments: list[str] = []
    thought_sig_lens: list[int] = []
    final_usage = None
    final_finish_reason = None
    final_model_version = None

    stream = await client.aio.models.generate_content_stream(
        model=model,
        contents=contents,
        config=config,
    )
    async for chunk in stream:
        um = getattr(chunk, "usage_metadata", None)
        if um is not None:
            final_usage = um
        mv = getattr(chunk, "model_version", None)
        if mv:
            final_model_version = mv

        for cand in (getattr(chunk, "candidates", None) or []):
            fr = getattr(cand, "finish_reason", None)
            if fr:
                final_finish_reason = fr
            content = getattr(cand, "content", None)
            if content is None:
                continue
            for part in (getattr(content, "parts", None) or []):
                ptext = getattr(part, "text", "") or ""
                is_thought = bool(getattr(part, "thought", False))
                sig = getattr(part, "thought_signature", None)
                if is_thought:
                    if ptext:
                        thought_segments.append(ptext)
                    if sig:
                        try:
                            thought_sig_lens.append(len(sig))
                        except TypeError:
                            pass
                else:
                    if ptext:
                        text_segments.append(ptext)

    return {
        "text_segments": text_segments,
        "thought_segments": thought_segments,
        "thought_sig_lens": thought_sig_lens,
        "usage_metadata": final_usage,
        "finish_reason": final_finish_reason,
        "model_version": final_model_version,
    }


def _extract_gemini(response: dict[str, Any], *, latency: float,
                    attempts: int, snapshot: str) -> CallResult:
    """Map assembled Gemini stream state → CallResult."""
    text = "".join(response["text_segments"])
    thinking_text = "".join(response["thought_segments"])
    sig_chars_total = sum(response["thought_sig_lens"])

    blocks: list[dict[str, Any]] = []
    if text:
        blocks.append({"type": "text", "text": text})
    if thinking_text or sig_chars_total > 0:
        blocks.append({
            "type": "thinking",
            "text": thinking_text,
            "signature_chars": sig_chars_total,
        })

    um = response.get("usage_metadata")
    input_tokens = int(getattr(um, "prompt_token_count", 0) or 0) if um else 0
    candidates_tokens = int(getattr(um, "candidates_token_count", 0) or 0) if um else 0
    cached_tokens = int(getattr(um, "cached_content_token_count", 0) or 0) if um else 0
    thoughts_tokens = 0
    if um is not None:
        tt = getattr(um, "thoughts_token_count", None)
        if tt is not None:
            thoughts_tokens = int(tt)

    # Gemini reports answer tokens (candidates_token_count) and thinking
    # tokens (thoughts_token_count) SEPARATELY. Anthropic and OpenAI bundle
    # both into output_tokens. To keep cost.py vendor-agnostic, sum them
    # into output_tokens here so output_tokens means "everything billed at
    # the output rate" across all vendors. thinking_tokens stays separate
    # for analysis (the bias-cancelling within-arm thinking-allocation
    # endpoint per DESIGN.md §5).
    output_tokens = candidates_tokens + thoughts_tokens
    thinking_tokens: int | None = thoughts_tokens if thoughts_tokens > 0 else None

    usage = Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=cached_tokens,
        thinking_tokens=thinking_tokens,
        thinking_tokens_source="sdk" if thinking_tokens is not None else None,
    )

    served_model = str(response.get("model_version") or "") or snapshot
    return CallResult(
        content=blocks,
        text=text,
        thinking_text=thinking_text,
        stop_reason=str(response.get("finish_reason") or "") or None,
        model=served_model,
        usage=usage,
        latency_seconds=latency,
        attempts=attempts,
        request_id=None,  # google-genai does not surface a per-call request id
        vendor="google",
        # Gemini's snapshot string is mutable (alias). The model_version
        # returned per-call is our build-identifier audit trail.
        system_fingerprint=str(response.get("model_version") or "") or None,
        extra={"thought_signature_chars_total": sig_chars_total},
    )


# ---- DeepSeek streaming finalizer + extractor ---------------------------
# DeepSeek runs through the openai SDK so it reuses _is_retriable_openai
# (DeepSeek's API surfaces openai-compatible errors via that SDK).

async def _deepseek_stream_to_final(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    extra_body: dict[str, Any],
) -> dict[str, Any]:
    """Drain a DeepSeek streaming chat-completion, return assembled state.

    DeepSeek extends OpenAI's chat-completion delta with a `reasoning_content`
    field carrying raw chain-of-thought text. We accumulate both text deltas
    and reasoning deltas, plus capture the final usage + system_fingerprint.
    """
    text_segments: list[str] = []
    reasoning_segments: list[str] = []
    final_usage = None
    final_finish_reason = None
    final_system_fingerprint: str | None = None
    final_model: str | None = None
    final_id: str | None = None

    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
        # The OpenAI SDK doesn't natively know about DeepSeek's
        # reasoning_effort param; pass via extra_body. Also request usage
        # in stream so the final chunk carries totals.
        extra_body={**extra_body, "stream_options": {"include_usage": True}},
    )
    async for chunk in stream:
        sf = getattr(chunk, "system_fingerprint", None)
        if sf:
            final_system_fingerprint = sf
        mv = getattr(chunk, "model", None)
        if mv:
            final_model = mv
        cid = getattr(chunk, "id", None)
        if cid:
            final_id = cid

        usage = getattr(chunk, "usage", None)
        if usage is not None:
            final_usage = usage

        choices = getattr(chunk, "choices", None) or []
        for choice in choices:
            fr = getattr(choice, "finish_reason", None)
            if fr:
                final_finish_reason = fr
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue
            txt = getattr(delta, "content", None)
            if txt:
                text_segments.append(txt)
            # DeepSeek extension. Tolerated when absent (V4 carryover unconfirmed).
            # The openai SDK may surface reasoning_content via the explicit
            # attribute AND mirror it in model_extra (unknown-field bag) — only
            # fall back to model_extra when the attribute itself is empty,
            # otherwise we double-count every CoT chunk.
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                reasoning_segments.append(rc)
            elif hasattr(delta, "model_extra"):
                me = delta.model_extra or {}
                rc2 = me.get("reasoning_content")
                if rc2:
                    reasoning_segments.append(rc2)

    return {
        "text_segments": text_segments,
        "reasoning_segments": reasoning_segments,
        "usage": final_usage,
        "finish_reason": final_finish_reason,
        "system_fingerprint": final_system_fingerprint,
        "model": final_model,
        "id": final_id,
    }


def _extract_deepseek(response: dict[str, Any], latency: float, attempts: int) -> CallResult:
    """Map assembled DeepSeek stream state → CallResult."""
    text = "".join(response["text_segments"])
    thinking_text = "".join(response["reasoning_segments"])

    blocks: list[dict[str, Any]] = []
    if text:
        blocks.append({"type": "text", "text": text})
    if thinking_text:
        # Approximate token count from raw CoT char length (consistent with
        # Anthropic Sonnet's char/4 estimate when SDK doesn't expose tokens).
        blocks.append({"type": "thinking", "text": thinking_text})

    usage_obj = response.get("usage")
    input_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0) if usage_obj else 0
    output_tokens = int(getattr(usage_obj, "completion_tokens", 0) or 0) if usage_obj else 0
    # DeepSeek usage extras: prompt_cache_hit_tokens / prompt_cache_miss_tokens.
    cache_hit = 0
    if usage_obj is not None:
        # Standard openai-compat field; DeepSeek populates it.
        cache_hit = int(getattr(usage_obj, "prompt_cache_hit_tokens", 0) or 0)
        if cache_hit == 0 and hasattr(usage_obj, "model_extra"):
            cache_hit = int((usage_obj.model_extra or {}).get("prompt_cache_hit_tokens", 0) or 0)

    # DeepSeek does not separately count reasoning tokens — they're bundled
    # into completion_tokens. Estimate from raw CoT char length when present;
    # otherwise leave None.
    if thinking_text:
        thinking_tokens: int | None = max(1, len(thinking_text) // 4)
        thinking_source: str | None = "estimated_char_per_4"
    else:
        thinking_tokens = None
        thinking_source = None

    usage = Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_input_tokens=0,  # DeepSeek auto-caches; no separate write rate
        cache_read_input_tokens=cache_hit,
        thinking_tokens=thinking_tokens,
        thinking_tokens_source=thinking_source,
    )

    return CallResult(
        content=blocks,
        text=text,
        thinking_text=thinking_text,
        stop_reason=response.get("finish_reason"),
        model=response.get("model") or "",
        usage=usage,
        latency_seconds=latency,
        attempts=attempts,
        request_id=response.get("id"),
        vendor="deepseek",
        system_fingerprint=response.get("system_fingerprint"),
    )


# ---- AnalystClient adapter protocol -------------------------------------

class AnalystClient(ABC):
    """Vendor-specific analyst API adapter.

    All adapters normalize their vendor's response into `CallResult`. The
    runner is vendor-agnostic — it constructs the right adapter via
    `make_analyst_client(cfg, anthropic_client)` and invokes `.run(prompt)`.
    """

    def __init__(self, cfg: ExperimentConfig) -> None:
        self.cfg = cfg

    @abstractmethod
    async def run(self, prompt: AssembledPrompt) -> CallResult:
        """Issue one analyst call against the assembled prompt."""

    async def aclose(self) -> None:
        """Optional cleanup hook (e.g., closing per-vendor httpx sessions)."""
        return None


class AnthropicAnalystClient(AnalystClient):
    """Anthropic adapter — wraps `call_messages` for v1 Opus/Sonnet arms.

    Reuses the AsyncAnthropic client the rest of the harness already
    constructs (extractor + judges always need it). No new SDK session.
    """

    def __init__(self, cfg: ExperimentConfig, client: AsyncAnthropic) -> None:
        super().__init__(cfg)
        self.client = client

    async def run(self, prompt: AssembledPrompt) -> CallResult:
        return await call_messages(
            client=self.client,
            model=self.cfg.models.analyst.snapshot,
            system=prompt.system,
            messages=prompt.messages,
            max_tokens=self.cfg.models.analyst.max_output_tokens,
            temperature=self.cfg.models.analyst.temperature,
            thinking_effort=self.cfg.models.analyst.thinking_effort,
            extra_headers=None,
            retry=self.cfg.execution.retry,
            per_call_timeout_seconds=self.cfg.execution.per_run_timeout_seconds,
        )


class OpenAIAnalystClient(AnalystClient):
    """GPT-5.5 via OpenAI Responses API.

    Reference snapshot: gpt-5.5-2026-04-23 (per-arm yaml supplies the actual
    snapshot). Reasoning effort defaults to "xhigh" (vendor max) and can be
    overridden via cfg.models.analyst.thinking_config["reasoning"].

    Streaming is mandatory: at xhigh, GPT-5.5 reasoning calls regularly
    exceed several minutes, beyond the OpenAI non-streaming wall-clock cap.
    The `response.completed` event carries the final assembled Response.

    Output extraction parallels the Anthropic shape: text concatenated from
    `output[].type=message → content[].type=output_text`, reasoning summary
    text concatenated from `output[].type=reasoning → summary[].text`.
    Encrypted reasoning blob lengths (the only thinking-depth proxy
    OpenAI exposes since raw CoT is redacted) are summed into
    `extra["encrypted_chars_total"]` and stored per-block in `content[]`.

    No strict structured-output schema is enforced — keeps cross-arm
    parity with the Anthropic free-form-JSON path. The Haiku extractor
    parses the analyst body downstream regardless of vendor.
    """

    def __init__(self, cfg: ExperimentConfig) -> None:
        super().__init__(cfg)
        self._client: Any | None = None  # AsyncOpenAI; lazily constructed

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI
            # AsyncOpenAI() reads OPENAI_API_KEY from env automatically.
            self._client = AsyncOpenAI()
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    async def run(self, prompt: AssembledPrompt) -> CallResult:
        client = self._get_client()
        instructions, user_input = _flatten_anthropic_prompt(prompt)

        # Default to vendor-max reasoning. Per-arm yaml may override via
        # thinking_config: { reasoning: { effort: <one of: low, medium, high, xhigh> } }
        thinking_cfg = self.cfg.models.analyst.thinking_config or {}
        reasoning_cfg = thinking_cfg.get("reasoning") or {"effort": "xhigh"}
        # Optional summary surfacing — synthetic, not the raw CoT.
        if "summary" not in reasoning_cfg:
            reasoning_cfg = {**reasoning_cfg, "summary": "auto"}

        cfg = self.cfg
        retry = cfg.execution.retry
        per_call_timeout = cfg.execution.per_run_timeout_seconds

        attempt = 0
        t_start_total = time.monotonic()
        while True:
            attempt += 1
            t0 = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    _openai_stream_to_final(
                        client,
                        model=cfg.models.analyst.snapshot,
                        instructions=instructions,
                        input_text=user_input,
                        reasoning=reasoning_cfg,
                        max_output_tokens=cfg.models.analyst.max_output_tokens,
                        temperature=cfg.models.analyst.temperature,
                    ),
                    timeout=per_call_timeout,
                )
                latency = time.monotonic() - t0
                return _extract_openai(response, latency=latency, attempts=attempt)
            except Exception as e:  # noqa: BLE001 — classified below
                if not _is_retriable_openai(e) or attempt >= retry.max_attempts:
                    log.warning(
                        "openai call failed after %d attempts (%.1fs total): %s",
                        attempt, time.monotonic() - t_start_total, e,
                    )
                    raise
                delay = _backoff(attempt, retry)
                log.info("openai retry %d/%d in %.1fs: %s",
                         attempt, retry.max_attempts, delay, e)
                await asyncio.sleep(delay)


class GeminiAnalystClient(AnalystClient):
    """Gemini 3.x Pro via google-genai SDK.

    Reference snapshot: gemini-3-pro-preview (alias redirects to current
    3.1 Pro per Google docs as of 2026-04-25). thinking_level=HIGH is the
    vendor max — top of {MINIMAL, LOW, MEDIUM, HIGH} for Gemini 3.

    Streaming via client.aio.models.generate_content_stream(); accumulates
    parts across chunks. Thought parts (when include_thoughts=True) carry
    `part.thought_signature` (opaque bytes) — analogous to Anthropic Opus
    signature_chars. Usage in `usage_metadata.thoughts_token_count`.

    No strict structured-output schema is enforced — keeps cross-arm
    parity with the Anthropic free-form-JSON path. Haiku extractor parses
    the analyst body downstream regardless of vendor.
    """

    def __init__(self, cfg: ExperimentConfig) -> None:
        super().__init__(cfg)
        self._client: Any | None = None  # genai.Client; lazily constructed

    def _get_client(self) -> Any:
        if self._client is None:
            from google import genai
            # genai.Client() reads GEMINI_API_KEY (or GOOGLE_API_KEY) from env.
            self._client = genai.Client()
        return self._client

    async def aclose(self) -> None:
        # google-genai SDK's Client doesn't expose an explicit close as of
        # v1.7x — the underlying httpx session is GC-managed. Safe to no-op.
        self._client = None

    async def run(self, prompt: AssembledPrompt) -> CallResult:
        from google.genai import types as gtypes
        client = self._get_client()
        instructions, user_input = _flatten_anthropic_prompt(prompt)

        # Default to vendor-max thinking. Per-arm yaml may override via
        # thinking_config: { thinking_level: <one of MINIMAL/LOW/MEDIUM/HIGH> }
        thinking_cfg_yaml = self.cfg.models.analyst.thinking_config or {}
        level_str = str(
            thinking_cfg_yaml.get("thinking_level", "HIGH")
        ).upper()
        # Map string to ThinkingLevel enum; tolerates "HIGH" / "high" / "High"
        try:
            thinking_level = getattr(gtypes.ThinkingLevel, level_str)
        except AttributeError as e:
            raise ValueError(
                f"unknown gemini thinking_level {level_str!r}; valid: "
                "MINIMAL, LOW, MEDIUM, HIGH"
            ) from e

        gen_config = gtypes.GenerateContentConfig(
            system_instruction=instructions or None,
            temperature=self.cfg.models.analyst.temperature,
            max_output_tokens=self.cfg.models.analyst.max_output_tokens,
            thinking_config=gtypes.ThinkingConfig(
                thinking_level=thinking_level,
                include_thoughts=True,  # surfaces thought parts (for signature_chars proxy)
            ),
        )

        cfg = self.cfg
        retry = cfg.execution.retry
        per_call_timeout = cfg.execution.per_run_timeout_seconds

        attempt = 0
        t_start_total = time.monotonic()
        while True:
            attempt += 1
            t0 = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    _gemini_stream_to_final(
                        client,
                        model=cfg.models.analyst.snapshot,
                        contents=user_input,
                        config=gen_config,
                    ),
                    timeout=per_call_timeout,
                )
                latency = time.monotonic() - t0
                return _extract_gemini(response, latency=latency, attempts=attempt,
                                        snapshot=cfg.models.analyst.snapshot)
            except Exception as e:  # noqa: BLE001 — classified below
                if not _is_retriable_gemini(e) or attempt >= retry.max_attempts:
                    log.warning(
                        "gemini call failed after %d attempts (%.1fs total): %s",
                        attempt, time.monotonic() - t_start_total, e,
                    )
                    raise
                delay = _backoff(attempt, retry)
                log.info("gemini retry %d/%d in %.1fs: %s",
                         attempt, retry.max_attempts, delay, e)
                await asyncio.sleep(delay)


class DeepSeekAnalystClient(AnalystClient):
    """DeepSeek V4 Pro via openai SDK against api.deepseek.com.

    DeepSeek does not publish a first-party Python SDK; their official
    integration recommendation is the openai SDK pointed at their
    OpenAI-compatible endpoint. We therefore reuse `AsyncOpenAI` with a
    base_url override + DEEPSEEK_API_KEY.

    Reference snapshot: deepseek-v4-pro (alias — mutable per
    MULTI_VENDOR_ADDENDUM §6). Per-call system_fingerprint is logged
    into raw records as the build identifier for the audit trail.

    Reasoning controls: V4 introduced `reasoning_effort` (per third-party
    report at lock authoring time; not yet in official docs). Per-arm
    yaml may set thinking_config: { reasoning_effort: <high | max> }.
    DeepSeek V4 thinking mode is the default; legacy `deepseek-reasoner`
    is being retired 2026-07-24.

    Reasoning content (`reasoning_content` field on the message; V3
    behavior — V4 carryover unconfirmed at lock time but adapter handles
    presence/absence gracefully) is captured into thinking_text — the
    only vendor besides Anthropic Sonnet exposing raw CoT text.
    """

    def __init__(self, cfg: ExperimentConfig) -> None:
        super().__init__(cfg)
        self._client: Any | None = None  # AsyncOpenAI; lazily constructed

    def _get_client(self) -> Any:
        if self._client is None:
            import os
            from openai import AsyncOpenAI
            api_key = os.environ.get("DEEPSEEK_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "DEEPSEEK_API_KEY not set in environment — required for "
                    "DeepSeekAnalystClient"
                )
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com",
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    async def run(self, prompt: AssembledPrompt) -> CallResult:
        client = self._get_client()
        instructions, user_input = _flatten_anthropic_prompt(prompt)

        # Per-arm thinking_config: { reasoning_effort: high | max }
        thinking_cfg = self.cfg.models.analyst.thinking_config or {}
        reasoning_effort = thinking_cfg.get("reasoning_effort", "max")

        # DeepSeek-specific kwargs land in extra_body since openai SDK does
        # not natively expose `reasoning_effort` in the chat.completions
        # signature (it's a vendor extension).
        extra_body: dict[str, Any] = {"reasoning_effort": str(reasoning_effort)}

        messages: list[dict[str, Any]] = []
        if instructions:
            messages.append({"role": "system", "content": instructions})
        messages.append({"role": "user", "content": user_input})

        cfg = self.cfg
        retry = cfg.execution.retry
        per_call_timeout = cfg.execution.per_run_timeout_seconds

        attempt = 0
        t_start_total = time.monotonic()
        while True:
            attempt += 1
            t0 = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    _deepseek_stream_to_final(
                        client,
                        model=cfg.models.analyst.snapshot,
                        messages=messages,
                        max_tokens=cfg.models.analyst.max_output_tokens,
                        temperature=cfg.models.analyst.temperature,
                        extra_body=extra_body,
                    ),
                    timeout=per_call_timeout,
                )
                latency = time.monotonic() - t0
                return _extract_deepseek(response, latency=latency, attempts=attempt)
            except Exception as e:  # noqa: BLE001 — classified below
                if not _is_retriable_openai(e) or attempt >= retry.max_attempts:
                    log.warning(
                        "deepseek call failed after %d attempts (%.1fs total): %s",
                        attempt, time.monotonic() - t_start_total, e,
                    )
                    raise
                delay = _backoff(attempt, retry)
                log.info("deepseek retry %d/%d in %.1fs: %s",
                         attempt, retry.max_attempts, delay, e)
                await asyncio.sleep(delay)


def make_analyst_client(
    cfg: ExperimentConfig,
    anthropic_client: AsyncAnthropic,
) -> AnalystClient:
    """Factory: dispatch by `cfg.models.analyst.vendor`.

    `anthropic_client` is reused for the Anthropic adapter (extractor + judge
    + Anthropic analyst all share one session). Non-Anthropic adapters
    construct their own per-vendor SDK clients internally.
    """
    vendor = (cfg.models.analyst.vendor or "anthropic").lower()
    if vendor == "anthropic":
        return AnthropicAnalystClient(cfg, anthropic_client)
    if vendor == "openai":
        return OpenAIAnalystClient(cfg)
    if vendor == "google":
        return GeminiAnalystClient(cfg)
    if vendor == "deepseek":
        return DeepSeekAnalystClient(cfg)
    raise ValueError(
        f"unknown analyst vendor {vendor!r} — must be one of "
        "{anthropic, openai, google, deepseek}"
    )


# ---- backward-compat: legacy run_analyst entry point --------------------

async def run_analyst(
    client: AsyncAnthropic,
    prompt: AssembledPrompt,
    cfg: ExperimentConfig,
) -> CallResult:
    """Vendor-dispatched analyst call. Preserved as a function so
    `runner.py` and existing call sites work unchanged for any vendor.

    For Anthropic arms, dispatches to AnthropicAnalystClient (reuses the
    runner's AsyncAnthropic client). For non-Anthropic arms, dispatches
    to the appropriate vendor adapter, which constructs its own SDK
    client lazily from environment credentials.

    The `client` argument is the AsyncAnthropic client the rest of the
    harness already holds (extractor + judge always need it). It is
    passed through to AnthropicAnalystClient and ignored by other
    adapters.
    """
    adapter = make_analyst_client(cfg, client)
    return await adapter.run(prompt)

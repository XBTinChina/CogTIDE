"""Single async LLM client for any OpenAI-compatible chat-completions API.

The client talks to any endpoint that speaks the OpenAI chat-completions
protocol (OpenAI, Azure OpenAI, Zhipu GLM, Moonshot Kimi, Together,
Groq, a local vLLM/Ollama server, etc.). Point it at a provider by
setting ``api_base_url``, ``model``, and the API-key environment
variable in ``configs/models.yaml``.

Rate-limit hardening
--------------------
Three layers defend against provider 429s:

1. **Bounded concurrency**: ``asyncio.Semaphore(concurrency_limit)`` caps
   in-flight request count (default 2).
2. **Global token bucket** (``_RateLimiter``): enforces a minimum
   wall-clock interval between consecutive requests across *all* stages
   (default 1.0s = 60 RPM global ceiling). This is what keeps an
   RPM-bound provider happy even if the semaphore allows parallelism.
3. **429-aware backoff**: the retry loop detects rate-limit errors
   (``RateLimitError``, HTTP 429, and some providers' proprietary
   rate-limit codes such as ``1302``), honors ``Retry-After`` headers
   when present, applies ``rate_limit_backoff_multiplier`` (default 4×)
   on top of the base wait, and adds uniform ``retry_jitter`` so
   concurrent failing calls don't retry in lockstep.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, TypeVar

from openai import AsyncOpenAI

from .normalization import NormalizationReport, extract_json

T = TypeVar("T")


@dataclass
class ModelConfig:
    provider: str = "openai-compatible"
    api_base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "LLM_API_KEY"
    fallback_api_key_env: str = "OPENAI_API_KEY"
    model: str = "gpt-4o-mini"
    temperature: float = 1.0
    max_tokens: int = 8192
    response_format_json: bool = True


@dataclass
class RetryConfig:
    attempts: int = 5
    waits_seconds: tuple[int, ...] = (5, 15, 30, 60, 120)
    timeout_seconds: int = 300
    concurrency_limit: int = 2
    min_request_interval_seconds: float = 1.0
    rate_limit_backoff_multiplier: float = 4.0
    retry_jitter: float = 0.5


@dataclass
class CallRecord:
    agent_id: str
    model: str
    temperature: float
    max_tokens: int
    system_prompt: str
    user_message: str
    raw_response: str
    attempts_used: int
    succeeded: bool
    last_error: str | None
    normalization: NormalizationReport | None = None
    finish_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "system_prompt": self.system_prompt,
            "user_message": self.user_message,
            "raw_response": self.raw_response,
            "attempts_used": self.attempts_used,
            "succeeded": self.succeeded,
            "last_error": self.last_error,
            "finish_reason": self.finish_reason,
            "normalization": self.normalization.to_dict() if self.normalization else None,
        }

    @property
    def was_truncated(self) -> bool:
        """True when the provider stopped because the output hit max_tokens.

        Both OpenAI-style ``"length"`` and the variant ``"max_tokens"``
        used by some compatible providers count as truncation.
        """
        return self.finish_reason in {"length", "max_tokens"}


class _RateLimiter:
    """Token bucket: guarantees ``acquire()`` calls are spaced by at
    least ``interval`` seconds wall-clock, globally across all async
    tasks sharing the instance. Zero-interval instances are a no-op
    fast path.
    """

    def __init__(self, interval: float) -> None:
        self._interval = max(0.0, float(interval))
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def acquire(self) -> None:
        if self._interval <= 0.0:
            return
        async with self._lock:
            now = time.monotonic()
            wait = max(0.0, self._next_allowed - now)
            # Schedule the next slot from whichever is later: now, or the
            # existing reservation. This prevents a backlog from compressing
            # once a quiet period ends.
            self._next_allowed = max(now, self._next_allowed) + self._interval
        if wait > 0:
            await asyncio.sleep(wait)


def _looks_like_rate_limit(exc: BaseException) -> bool:
    """Heuristic: is this exception a 429 / rate-limit error?"""
    if type(exc).__name__ == "RateLimitError":
        return True
    msg = str(exc)
    return "429" in msg or "1302" in msg or "rate limit" in msg.lower()


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Extract ``Retry-After`` header (seconds) from an HTTP error if any.

    The OpenAI SDK attaches ``.response`` (httpx.Response) to
    ``APIStatusError`` subclasses. Retry-After may be an integer of
    seconds, or an HTTP-date; we only parse the integer form.
    """
    response = getattr(exc, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        raw = headers.get("retry-after") or headers.get("Retry-After")
    except Exception:
        return None
    if not raw:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


class LLMClient:
    def __init__(
        self,
        model_config: ModelConfig | None = None,
        retry_config: RetryConfig | None = None,
        record_sink: Callable[[CallRecord], None] | None = None,
    ) -> None:
        self.model_config = model_config or ModelConfig()
        self.retry_config = retry_config or RetryConfig()
        self.record_sink = record_sink
        api_key = os.environ.get(self.model_config.api_key_env) or os.environ.get(
            self.model_config.fallback_api_key_env, ""
        )
        if not api_key:
            raise RuntimeError(
                f"No API key found in env vars "
                f"{self.model_config.api_key_env} or {self.model_config.fallback_api_key_env}. "
                f"Either export {self.model_config.api_key_env}=sk-... in your shell, "
                f"or create a .env file at the repo root (copy .env.example). "
                f"RunContext.create() auto-loads .env on startup."
            )
        self._client = AsyncOpenAI(
            base_url=self.model_config.api_base_url,
            api_key=api_key,
        )
        self._semaphore = asyncio.Semaphore(self.retry_config.concurrency_limit)
        self._rate_limiter = _RateLimiter(
            self.retry_config.min_request_interval_seconds
        )

    async def chat(
        self,
        agent_id: str,
        system_prompt: str,
        user_message: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        timeout_override: float | None = None,
    ) -> CallRecord:
        model = model or self.model_config.model
        temperature = temperature if temperature is not None else self.model_config.temperature
        max_tokens = max_tokens or self.model_config.max_tokens
        request_timeout = (
            timeout_override
            if timeout_override is not None
            else self.retry_config.timeout_seconds
        )

        record = CallRecord(
            agent_id=agent_id,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            user_message=user_message,
            raw_response="",
            attempts_used=0,
            succeeded=False,
            last_error=None,
        )

        waits = list(self.retry_config.waits_seconds)
        rl_multiplier = max(1.0, float(self.retry_config.rate_limit_backoff_multiplier))
        jitter = max(0.0, float(self.retry_config.retry_jitter))

        async with self._semaphore:
            for attempt in range(self.retry_config.attempts):
                # Global token bucket: pace requests even within the
                # semaphore, so RPM-bound providers don't get bursted.
                await self._rate_limiter.acquire()
                record.attempts_used = attempt + 1
                try:
                    kwargs: dict[str, Any] = {
                        "model": model,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                    }
                    if json_mode and self.model_config.response_format_json:
                        kwargs["response_format"] = {"type": "json_object"}
                    response = await asyncio.wait_for(
                        self._client.chat.completions.create(**kwargs),
                        timeout=request_timeout,
                    )
                    choice = response.choices[0]
                    record.raw_response = choice.message.content or ""
                    record.finish_reason = getattr(choice, "finish_reason", None)
                    record.succeeded = True
                    record.last_error = None
                    break
                except Exception as e:
                    record.last_error = f"{type(e).__name__}: {e}"
                    is_rl = _looks_like_rate_limit(e)
                    tag = "retry-429" if is_rl else "retry-transport"
                    if attempt < self.retry_config.attempts - 1:
                        base = waits[min(attempt, len(waits) - 1)]
                        if is_rl:
                            base = base * rl_multiplier
                        # Jittered wait so concurrent failing calls don't
                        # retry in lockstep (the storm pattern).
                        if jitter > 0:
                            factor = random.uniform(1.0 - jitter, 1.0 + jitter)
                            wait_s = base * factor
                        else:
                            wait_s = float(base)
                        # If the server gave us a Retry-After header, honor
                        # it as a floor (don't go below what it asked).
                        ra = _retry_after_seconds(e)
                        if ra is not None and ra > wait_s:
                            wait_s = ra
                        print(
                            f"  [{tag}] {agent_id} attempt {attempt + 1} failed: "
                            f"{record.last_error}. Waiting {wait_s:.1f}s..."
                        )
                        await asyncio.sleep(wait_s)
                    else:
                        print(
                            f"  [error] {agent_id} failed after "
                            f"{self.retry_config.attempts} attempts "
                            f"({'rate-limit' if is_rl else 'transport'}): "
                            f"{record.last_error}"
                        )

        if self.record_sink is not None:
            try:
                self.record_sink(record)
            except Exception as sink_err:
                print(f"  [warn] record_sink failed: {sink_err}")

        return record

    async def chat_json(
        self,
        agent_id: str,
        system_prompt: str,
        user_message: str,
        *,
        expect: str = "auto",
        **kwargs: Any,
    ) -> tuple[Any, CallRecord]:
        record = await self.chat(
            agent_id=agent_id,
            system_prompt=system_prompt,
            user_message=user_message,
            json_mode=True,
            **kwargs,
        )
        parsed, report = extract_json(record.raw_response, expect=expect)
        record.normalization = report
        return parsed, record


async def gather_with_limit(
    coros: Iterable[Awaitable[T]],
    *,
    max_concurrency: int | None = None,
) -> list[T]:
    if max_concurrency is None:
        return await asyncio.gather(*coros)
    sem = asyncio.Semaphore(max_concurrency)

    async def _run(c: Awaitable[T]) -> T:
        async with sem:
            return await c

    return await asyncio.gather(*[_run(c) for c in coros])

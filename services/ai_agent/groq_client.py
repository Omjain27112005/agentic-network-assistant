"""
Groq LLM Client — production-grade wrapper around the Groq SDK.

Production features:
- Exponential backoff retry on rate limits and transient errors
- Request timeout enforcement
- Token usage tracking for cost monitoring
- Structured error types for different failure modes
- Tool calling support (required for ReAct pattern)

Why Groq over OpenAI?
- 10-20x faster inference (critical for real-time agent loops)
- Free tier with generous limits
- Compatible API surface with OpenAI SDK patterns
- Supports llama3-70b — excellent for structured reasoning tasks
"""
import time
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

import structlog
from groq import (
    Groq,
    RateLimitError,
    APITimeoutError,
    APIConnectionError,
    APIStatusError,
)

logger = structlog.get_logger(__name__)


# -----------------------------------------------
# Custom Exception Hierarchy
# -----------------------------------------------

class GroqClientError(Exception):
    """Base exception for all Groq client errors."""


class GroqRateLimitError(GroqClientError):
    """Raised when Groq API rate limit is hit. Agent should back off."""


class GroqTimeoutError(GroqClientError):
    """Raised when Groq API call exceeds timeout. Agent should retry."""


class GroqMaxRetriesError(GroqClientError):
    """Raised when all retry attempts are exhausted."""


# -----------------------------------------------
# Token Usage Tracker
# -----------------------------------------------

@dataclass
class TokenUsage:
    """Tracks token consumption across a ReAct session."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    api_calls: int = 0

    def add(self, usage) -> None:
        """Add usage from a Groq API response."""
        if usage:
            self.prompt_tokens += usage.prompt_tokens or 0
            self.completion_tokens += usage.completion_tokens or 0
            self.total_tokens += usage.total_tokens or 0
        self.api_calls += 1

    def __str__(self) -> str:
        return (
            f"TokenUsage(calls={self.api_calls}, "
            f"prompt={self.prompt_tokens}, "
            f"completion={self.completion_tokens}, "
            f"total={self.total_tokens})"
        )


# -----------------------------------------------
# Groq Client
# -----------------------------------------------

class GroqLLMClient:
    """
    Production-ready Groq LLM client with retry logic and observability.

    Usage:
        client = GroqLLMClient(api_key="...", model="llama3-70b-8192")
        response = client.chat(messages=[...], tools=[...])

    Retry Strategy (exponential backoff):
        Attempt 1 → immediate
        Attempt 2 → wait 2s
        Attempt 3 → wait 4s
        Attempt 4 → wait 8s
        Attempt 5 → give up → raise GroqMaxRetriesError
    """

    # Model to use — llama3-70b-8192 is best for structured reasoning
    DEFAULT_MODEL = "llama3-70b-8192"
    MAX_RETRIES = 4
    BASE_BACKOFF_SECONDS = 2.0
    DEFAULT_TIMEOUT_SECONDS = 30.0
    DEFAULT_MAX_TOKENS = 2048

    def __init__(self, api_key: str, model: Optional[str] = None):
        if not api_key:
            raise ValueError("GROQ_API_KEY is required but not set in .env")

        self._client = Groq(api_key=api_key, timeout=self.DEFAULT_TIMEOUT_SECONDS)
        self._model = model or self.DEFAULT_MODEL
        self._total_usage = TokenUsage()  # Lifetime token tracking

        logger.info(
            "groq_client.initialized",
            model=self._model,
            timeout=self.DEFAULT_TIMEOUT_SECONDS,
        )

    def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]] = None,
        tool_choice: str = "auto",
        temperature: float = 0.1,        # Low temperature = more deterministic reasoning
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> Any:
        """
        Send a chat request to Groq with automatic retry on transient errors.

        Args:
            messages: Conversation history in OpenAI message format
            tools: Optional list of tool definitions for function calling
            tool_choice: "auto" | "none" | specific tool name
            temperature: 0.0-1.0. Low = deterministic, High = creative.
                         Use 0.1 for reasoning tasks.
            max_tokens: Max tokens in the response

        Returns:
            Groq ChatCompletion response object

        Raises:
            GroqMaxRetriesError: After all retry attempts exhausted
            GroqRateLimitError: If rate limit hit and not recovering
        """
        last_exception = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                kwargs = {
                    "model": self._model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }

                # Only add tools if provided (Groq requires tools list to be non-empty)
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice

                response = self._client.chat.completions.create(**kwargs)

                # Track token usage for observability
                self._total_usage.add(response.usage)

                logger.debug(
                    "groq.api_call_success",
                    attempt=attempt + 1,
                    model=self._model,
                    prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                    completion_tokens=response.usage.completion_tokens if response.usage else 0,
                    finish_reason=response.choices[0].finish_reason,
                )

                return response

            except RateLimitError as e:
                last_exception = GroqRateLimitError(str(e))
                wait = self._backoff_wait(attempt)
                logger.warning(
                    "groq.rate_limit_hit",
                    attempt=attempt + 1,
                    wait_seconds=wait,
                )
                time.sleep(wait)

            except APITimeoutError as e:
                last_exception = GroqTimeoutError(str(e))
                wait = self._backoff_wait(attempt)
                logger.warning(
                    "groq.timeout",
                    attempt=attempt + 1,
                    wait_seconds=wait,
                )
                time.sleep(wait)

            except APIConnectionError as e:
                last_exception = GroqClientError(f"Connection error: {e}")
                wait = self._backoff_wait(attempt)
                logger.warning(
                    "groq.connection_error",
                    attempt=attempt + 1,
                    wait_seconds=wait,
                )
                time.sleep(wait)

            except APIStatusError as e:
                # 4xx errors are not retryable (bad request, auth failure)
                if e.status_code < 500:
                    logger.error(
                        "groq.client_error",
                        status_code=e.status_code,
                        message=str(e),
                    )
                    raise GroqClientError(f"Groq API client error {e.status_code}: {e}") from e
                # 5xx server errors — retry
                last_exception = GroqClientError(f"Server error {e.status_code}: {e}")
                wait = self._backoff_wait(attempt)
                logger.warning(
                    "groq.server_error",
                    status_code=e.status_code,
                    attempt=attempt + 1,
                    wait_seconds=wait,
                )
                time.sleep(wait)

        # All retries exhausted
        logger.error(
            "groq.max_retries_exhausted",
            max_retries=self.MAX_RETRIES,
            last_error=str(last_exception),
        )
        raise GroqMaxRetriesError(
            f"Groq API failed after {self.MAX_RETRIES} retries: {last_exception}"
        ) from last_exception

    def get_total_usage(self) -> TokenUsage:
        """Return lifetime token usage stats for this client instance."""
        return self._total_usage

    def _backoff_wait(self, attempt: int) -> float:
        """
        Calculate exponential backoff wait time.
        attempt=0 → 2s, attempt=1 → 4s, attempt=2 → 8s, attempt=3 → 16s
        """
        return self.BASE_BACKOFF_SECONDS ** (attempt + 1)

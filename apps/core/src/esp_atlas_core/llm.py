"""Injectable LLM client for ask(). Real calls go to Groq's OpenAI-compatible
chat-completions endpoint; tests inject a fake implementing the same
`.complete(system_prompt, user_prompt, temperature=0) -> str` interface so no
network call is ever made off of `pytest`.

Model: env GROQ_MODEL, default a current Llama-70B-class Groq instruct model.
Key:   env GROQ_API_KEY, resolved lazily — missing key raises only when a real
       call is actually attempted, never at import/construction time.
"""
import os

import httpx

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_CAP_SECONDS = 30


class GroqConfigError(RuntimeError):
    """Raised when a real Groq call is attempted without GROQ_API_KEY set."""


class GroqRateLimitError(RuntimeError):
    """Raised when Groq keeps returning 429 past the retry budget."""


def _parse_wait_seconds(value):
    if value is None:
        return None
    text = value.strip()
    if text.endswith("s"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


class GroqClient:
    """Real Groq chat-completions client. Injectable http_client/sleep_fn for tests."""

    def __init__(self, model=None, api_key=None, http_client=None, sleep_fn=None, max_retries=DEFAULT_MAX_RETRIES):
        self._model = model
        self._api_key = api_key
        self._http_client = http_client
        self._sleep = sleep_fn or _real_sleep
        self._max_retries = max_retries

    def _resolve_model(self):
        return self._model or os.environ.get("GROQ_MODEL") or DEFAULT_MODEL

    def _resolve_api_key(self):
        key = self._api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise GroqConfigError(
                "GROQ_API_KEY is not set. Export it, or pass api_key= explicitly, before calling ask()."
            )
        return key

    def _backoff_seconds(self, headers, attempt):
        for header in ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
            wait = _parse_wait_seconds(headers.get(header))
            if wait is not None:
                return wait
        return min(2 ** attempt, DEFAULT_BACKOFF_CAP_SECONDS)

    def complete(self, system_prompt, user_prompt, temperature=0):
        api_key = self._resolve_api_key()
        payload = {
            "model": self._resolve_model(),
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        client = self._http_client or httpx.Client(timeout=30)
        owns_client = self._http_client is None
        try:
            attempt = 0
            while True:
                response = client.post(GROQ_CHAT_URL, json=payload, headers=headers)
                if response.status_code == 429:
                    attempt += 1
                    if attempt > self._max_retries:
                        raise GroqRateLimitError(
                            f"Groq rate limit exceeded after {self._max_retries} retries."
                        )
                    self._sleep(self._backoff_seconds(response.headers, attempt))
                    continue
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        finally:
            if owns_client:
                client.close()


def _real_sleep(seconds):
    import time

    time.sleep(seconds)

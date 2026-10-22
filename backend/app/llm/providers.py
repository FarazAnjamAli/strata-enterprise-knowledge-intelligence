"""LLM provider adapters.

Three wire protocols cover every tier:
  * Ollama            (local tier)
  * OpenAI-compatible (free tier: Groq/OpenRouter/Together/...; paid: OpenAI)
  * Anthropic         (paid tier)

Adapters are stateless and raise ProviderError on any failure, so the router
can treat every backend the same way.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

import httpx

from app.config import TierName, get_settings


class ProviderError(Exception):
    pass


@dataclass
class Usage:
    prompt_tokens: int
    completion_tokens: int


def estimate_tokens(text: str) -> int:
    """~4 chars per token; good enough for cost tracking when the API is silent."""
    return max(1, len(text) // 4)


class Provider(ABC):
    tier: TierName
    label: str
    model: str

    @property
    @abstractmethod
    def configured(self) -> bool: ...

    @abstractmethod
    def generate(self, system: str, prompt: str) -> tuple[str, Usage]: ...

    @abstractmethod
    def stream(self, system: str, prompt: str) -> Iterator[str]: ...

    def ping(self) -> bool:
        """Cheap reachability check for the status page (no tokens spent)."""
        return self.configured

    @property
    def name(self) -> str:
        return f"{self.label} · {self.model}"


# --------------------------------------------------------------------- Ollama


class OllamaProvider(Provider):
    tier: TierName = "local"

    def __init__(self) -> None:
        s = get_settings()
        self.url = s.ollama_url.rstrip("/")
        self.model = s.ollama_model
        self.label = "Ollama"
        self.timeout = s.ollama_timeout
        self.options = {"temperature": s.llm_temperature, "num_ctx": s.ollama_num_ctx}
        self.keep_alive = s.ollama_keep_alive
        self.enabled = s.local_llm_enabled

    @property
    def configured(self) -> bool:
        return self.enabled and bool(self.url and self.model)

    def _body(self, system: str, prompt: str, stream: bool) -> dict:
        return {
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "stream": stream,
            # keep the model resident: a cold load + CPU prompt eval is what
            # blows request timeouts on on-prem hardware
            "keep_alive": self.keep_alive,
            "options": self.options,
        }

    def generate(self, system: str, prompt: str) -> tuple[str, Usage]:
        try:
            r = httpx.post(
                f"{self.url}/api/generate", json=self._body(system, prompt, False), timeout=self.timeout
            )
            r.raise_for_status()
            data = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"ollama: {exc}") from exc
        text = (data.get("response") or "").strip()
        return text, Usage(
            data.get("prompt_eval_count") or estimate_tokens(system + prompt),
            data.get("eval_count") or estimate_tokens(text),
        )

    def stream(self, system: str, prompt: str) -> Iterator[str]:
        try:
            with httpx.stream(
                "POST",
                f"{self.url}/api/generate",
                json=self._body(system, prompt, True),
                timeout=httpx.Timeout(self.timeout, read=self.timeout),
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line:
                        continue
                    piece = json.loads(line)
                    if piece.get("error"):
                        raise ProviderError(f"ollama: {piece['error']}")
                    if tok := piece.get("response"):
                        yield tok
                    if piece.get("done"):
                        return
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"ollama: {exc}") from exc

    def ping(self) -> bool:
        if not self.configured:
            return False
        try:
            r = httpx.get(f"{self.url}/api/tags", timeout=2.5)
            r.raise_for_status()
            names = {m.get("name", "") for m in r.json().get("models", [])}
            base = self.model.split(":")[0]
            return any(n == self.model or n.split(":")[0] == base for n in names)
        except (httpx.HTTPError, ValueError):
            return False


# ---------------------------------------------------------- OpenAI-compatible


class OpenAICompatibleProvider(Provider):
    def __init__(
        self,
        *,
        tier: TierName,
        label: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int,
        enabled: bool,
    ) -> None:
        s = get_settings()
        self.tier = tier
        self.label = label
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.enabled = enabled
        self.temperature = s.llm_temperature
        self.max_tokens = s.llm_max_tokens

    @property
    def configured(self) -> bool:
        return self.enabled and bool(self.api_key and self.model and self.base_url)

    def _body(self, system: str, prompt: str, stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def generate(self, system: str, prompt: str) -> tuple[str, Usage]:
        try:
            r = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers,
                json=self._body(system, prompt, False),
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            raise ProviderError(f"{self.label}: {exc}") from exc
        u = data.get("usage") or {}
        return text, Usage(
            u.get("prompt_tokens") or estimate_tokens(system + prompt),
            u.get("completion_tokens") or estimate_tokens(text),
        )

    def stream(self, system: str, prompt: str) -> Iterator[str]:
        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers,
                json=self._body(system, prompt, True),
                timeout=httpx.Timeout(self.timeout, read=self.timeout),
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        return
                    choices = json.loads(payload).get("choices") or [{}]
                    if tok := (choices[0].get("delta") or {}).get("content"):
                        yield tok
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"{self.label}: {exc}") from exc


# ------------------------------------------------------------------ Anthropic


class AnthropicProvider(Provider):
    tier: TierName = "paid"
    VERSION = "2023-06-01"

    def __init__(self) -> None:
        s = get_settings()
        base = s.paid_llm_base_url.rstrip("/")
        self.base_url = base if "anthropic" in base else "https://api.anthropic.com/v1"
        self.api_key = s.paid_llm_api_key
        self.model = s.paid_llm_model
        self.label = "Anthropic"
        self.timeout = s.paid_llm_timeout
        self.enabled = s.paid_llm_enabled
        self.temperature = s.llm_temperature
        self.max_tokens = s.llm_max_tokens

    @property
    def configured(self) -> bool:
        return self.enabled and bool(self.api_key and self.model)

    @property
    def _headers(self) -> dict:
        return {"x-api-key": self.api_key, "anthropic-version": self.VERSION}

    def _body(self, system: str, prompt: str, stream: bool) -> dict:
        return {
            "model": self.model,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": stream,
        }

    def generate(self, system: str, prompt: str) -> tuple[str, Usage]:
        try:
            r = httpx.post(
                f"{self.base_url}/messages",
                headers=self._headers,
                json=self._body(system, prompt, False),
                timeout=self.timeout,
            )
            r.raise_for_status()
            data = r.json()
            text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text").strip()
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise ProviderError(f"anthropic: {exc}") from exc
        u = data.get("usage") or {}
        return text, Usage(
            u.get("input_tokens") or estimate_tokens(system + prompt),
            u.get("output_tokens") or estimate_tokens(text),
        )

    def stream(self, system: str, prompt: str) -> Iterator[str]:
        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/messages",
                headers=self._headers,
                json=self._body(system, prompt, True),
                timeout=httpx.Timeout(self.timeout, read=self.timeout),
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    if event.get("type") == "content_block_delta":
                        if tok := (event.get("delta") or {}).get("text"):
                            yield tok
                    elif event.get("type") == "message_stop":
                        return
                    elif event.get("type") == "error":
                        raise ProviderError(f"anthropic: {event.get('error')}")
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"anthropic: {exc}") from exc


# -------------------------------------------------------------------- factory


def build_providers() -> dict[TierName, Provider]:
    s = get_settings()
    free = OpenAICompatibleProvider(
        tier="free",
        label=s.free_llm_label,
        base_url=s.free_llm_base_url,
        api_key=s.free_llm_api_key,
        model=s.free_llm_model,
        timeout=s.free_llm_timeout,
        enabled=s.free_llm_enabled,
    )
    if s.paid_llm_provider == "anthropic":
        paid: Provider = AnthropicProvider()
    else:
        paid = OpenAICompatibleProvider(
            tier="paid",
            label="OpenAI" if s.paid_llm_provider == "openai" else "Premium API",
            base_url=s.paid_llm_base_url,
            api_key=s.paid_llm_api_key,
            model=s.paid_llm_model,
            timeout=s.paid_llm_timeout,
            enabled=s.paid_llm_enabled,
        )
    return {"local": OllamaProvider(), "free": free, "paid": paid}

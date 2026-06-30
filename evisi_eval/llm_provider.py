from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from .config import ProviderConfig


@dataclass
class LLMResponse:
    data: dict[str, Any]
    provider: str
    model: str
    request_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    provider_name: str
    model_name: str

    def generate_json(self, system_prompt: str, payload: dict[str, Any], task: str) -> LLMResponse:
        ...


class HTTPJSONClient:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.provider_name = config.name
        self.model_name = config.model

    def generate_json(self, system_prompt: str, payload: dict[str, Any], task: str) -> LLMResponse:
        if self.config.protocol == "gemini":
            return self._call_gemini(system_prompt, payload, task)
        if self.config.protocol == "openai_compatible":
            return self._call_openai_compatible(system_prompt, payload, task)
        raise ValueError(f"Unsupported provider protocol: {self.config.protocol}")

    def _call_openai_compatible(
        self, system_prompt: str, payload: dict[str, Any], task: str
    ) -> LLMResponse:
        url = _chat_completions_url(self.config.base_url)
        body = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "max_tokens": self.config.max_output_tokens,
        }
        raw, headers = self._post(
            url,
            body,
            {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            task,
        )
        try:
            content = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"{task}: provider returned an unexpected chat-completions shape") from exc
        return LLMResponse(
            data=parse_json_object(content),
            provider=self.provider_name,
            model=self.model_name,
            request_id=headers.get("x-request-id") or raw.get("id"),
            usage=raw.get("usage") or {},
        )

    def _call_gemini(self, system_prompt: str, payload: dict[str, Any], task: str) -> LLMResponse:
        model = urllib.parse.quote(self.config.model, safe="-_.")
        key = urllib.parse.quote(self.config.api_key, safe="")
        url = f"{self.config.base_url}/models/{model}:generateContent?key={key}"
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": json.dumps(payload, ensure_ascii=False)}],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "maxOutputTokens": self.config.max_output_tokens,
            },
        }
        raw, headers = self._post(url, body, {"Content-Type": "application/json"}, task)
        try:
            content = raw["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"{task}: Gemini returned an unexpected response shape") from exc
        usage = raw.get("usageMetadata") or {}
        return LLMResponse(
            data=parse_json_object(content),
            provider=self.provider_name,
            model=self.model_name,
            request_id=headers.get("x-request-id"),
            usage=usage,
        )

    def _post(
        self,
        url: str,
        body: dict[str, Any],
        headers: dict[str, str],
        task: str,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            request = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                    response_bytes = response.read()
                    if not response_bytes:
                        raise http.client.IncompleteRead(response_bytes, 1)
                    response_data = json.loads(response_bytes.decode("utf-8"))
                    if not isinstance(response_data, dict):
                        raise ValueError("provider response root is not a JSON object")
                    response_headers = {k.casefold(): v for k, v in response.headers.items()}
                    return response_data, response_headers
            except urllib.error.HTTPError as exc:
                last_error = RuntimeError(f"{task}: provider HTTP {exc.code}")
                if exc.code not in {408, 409, 429, 500, 502, 503, 504}:
                    break
            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                http.client.IncompleteRead,
                http.client.RemoteDisconnected,
                json.JSONDecodeError,
                UnicodeDecodeError,
                ValueError,
            ) as exc:
                last_error = exc
            if attempt < self.config.max_retries:
                time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"{task}: provider request failed after retries: {last_error}") from last_error


class ScriptedLLMClient:
    """Deterministic client for tests; it never performs network I/O."""

    def __init__(self, responses: list[dict[str, Any]], provider: str = "scripted", model: str = "fixture"):
        self.responses = list(responses)
        self.provider_name = provider
        self.model_name = model
        self.calls: list[dict[str, Any]] = []

    def generate_json(self, system_prompt: str, payload: dict[str, Any], task: str) -> LLMResponse:
        if not self.responses:
            raise AssertionError(f"No scripted response left for task={task}")
        self.calls.append({"task": task, "payload": payload, "system_prompt": system_prompt})
        return LLMResponse(
            data=self.responses.pop(0),
            provider=self.provider_name,
            model=self.model_name,
            request_id=f"scripted-{len(self.calls)}",
        )


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise ValueError("Provider output is not a JSON object or string")
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Provider output does not contain a JSON object")
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Provider JSON root must be an object")
    return parsed


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"

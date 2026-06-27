from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    protocol: str
    api_key: str
    model: str
    base_url: str
    timeout_seconds: int = 180
    max_retries: int = 2


_DEFAULTS: dict[str, dict[str, str]] = {
    "deepseek": {
        "protocol": "openai_compatible",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "openai": {
        "protocol": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "model": "",
    },
    "gemini": {
        "protocol": "gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "",
    },
    "custom": {
        "protocol": "openai_compatible",
        "base_url": "",
        "model": "",
    },
}


def get_provider_config(provider: str | None = None) -> ProviderConfig:
    name = (provider or _setting("EVISI_PRIMARY_PROVIDER") or "deepseek").strip().lower()
    if name not in _DEFAULTS:
        raise ValueError(f"Unsupported provider {name!r}; choose deepseek, openai, gemini, or custom")

    prefix = "EVISI_CUSTOM" if name == "custom" else name.upper()
    defaults = _DEFAULTS[name]
    api_key = _setting(f"{prefix}_API_KEY")
    model = _setting(f"{prefix}_MODEL") or defaults["model"]
    base_url = _setting(f"{prefix}_BASE_URL") or defaults["base_url"]
    protocol = _setting(f"{prefix}_PROTOCOL") or defaults["protocol"]

    missing = []
    if not api_key:
        missing.append(f"{prefix}_API_KEY")
    if not model:
        missing.append(f"{prefix}_MODEL")
    if not base_url:
        missing.append(f"{prefix}_BASE_URL")
    if missing:
        joined = ", ".join(missing)
        raise ValueError(
            f"Provider {name!r} is not configured. Set {joined} in local_secrets.py "
            "or environment variables."
        )

    return ProviderConfig(
        name=name,
        protocol=protocol,
        api_key=api_key,
        model=model,
        base_url=base_url.rstrip("/"),
        timeout_seconds=_int_setting("EVISI_TIMEOUT_SECONDS", 180),
        max_retries=_int_setting("EVISI_MAX_RETRIES", 2),
    )


def get_review_provider_name(primary_provider: str) -> str:
    return (_setting("EVISI_REVIEW_PROVIDER") or primary_provider).strip().lower()


def get_openai_api_key() -> str | None:
    """Backward-compatible key loader used by the legacy API check."""
    return _setting("OPENAI_API_KEY")


def _setting(name: str) -> str | None:
    local_value = _local_secret(name)
    if local_value:
        return local_value
    value = os.getenv(name)
    if value and value.strip() and "replace-with" not in value.casefold():
        return value.strip()
    return None


def _local_secret(name: str) -> str | None:
    try:
        import local_secrets  # type: ignore
    except ImportError:
        return None
    value: Any = getattr(local_secrets, name, None)
    if isinstance(value, str) and value.strip() and "replace-with" not in value.casefold():
        return value.strip()
    return None


def _int_setting(name: str, default: int) -> int:
    value = _setting(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    return parsed

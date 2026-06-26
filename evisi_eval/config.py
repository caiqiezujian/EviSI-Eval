from __future__ import annotations

import os


def get_openai_api_key() -> str | None:
    """Load the OpenAI API key without printing or logging it."""
    try:
        import local_secrets  # type: ignore
    except ImportError:
        local_secrets = None

    if local_secrets is not None:
        value = getattr(local_secrets, "OPENAI_API_KEY", None)
        if isinstance(value, str) and value.strip() and "replace-with" not in value:
            return value.strip()

    value = os.getenv("OPENAI_API_KEY")
    if value and value.strip():
        return value.strip()
    return None


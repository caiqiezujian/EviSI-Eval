from __future__ import annotations

from .config import get_openai_api_key, get_provider_config
from .llm_provider import HTTPJSONClient


def check_openai_api(model: str = "gpt-4.1-mini") -> dict:
    api_key = get_openai_api_key()
    if not api_key:
        return {
            "ok": False,
            "reason": "OPENAI_API_KEY not configured. Create local_secrets.py or set the environment variable.",
        }

    try:
        from openai import OpenAI
    except ImportError:
        return {
            "ok": False,
            "reason": "The openai package is not installed. Run: python -m pip install openai",
        }

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        input="Return exactly: ok",
        max_output_tokens=8,
    )
    text = getattr(response, "output_text", "").strip()
    return {
        "ok": bool(text),
        "model": model,
        "response_preview": text[:20],
    }


def check_provider_api(provider: str) -> dict:
    try:
        config = get_provider_config(provider)
        client = HTTPJSONClient(config)
        response = client.generate_json(
            "Return JSON only. Follow the requested schema exactly.",
            {"task": "health_check", "required_output": {"ok": True}},
            task="health_check",
        )
    except Exception as exc:
        return {"ok": False, "provider": provider, "reason": str(exc)}
    return {
        "ok": response.data.get("ok") is True,
        "provider": response.provider,
        "model": response.model,
        "request_id": response.request_id,
    }

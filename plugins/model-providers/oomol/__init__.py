"""OOMOL-hosted OpenAI-compatible LLM provider for Hermes."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from providers import register_provider
from providers.base import ProviderProfile


_VALID_API_MODES = {"chat_completions", "codex_responses"}


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for the OOMOL LLM provider.")
    return value


def _base_url() -> str:
    value = _required_environment("OO_LLM_BASE_URL").rstrip("/")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.rstrip("/").endswith("/v1")
    ):
        raise RuntimeError(
            "OO_LLM_BASE_URL must be a safe HTTPS base URL ending in /v1."
        )
    return value


model = _required_environment("OO_LLM_MODEL")
api_mode = _required_environment("OO_LLM_API_MODE")
if api_mode not in _VALID_API_MODES:
    supported = ", ".join(sorted(_VALID_API_MODES))
    raise RuntimeError(
        f"Unsupported OO_LLM_API_MODE '{api_mode}'. Supported values: {supported}."
    )


oomol = ProviderProfile(
    name="oomol",
    aliases=("oo", "oo-llm", "oomol-llm"),
    display_name="OOMOL LLM",
    description="OOMOL-hosted OpenAI-compatible language models",
    env_vars=("OO_API_KEY",),
    base_url=_base_url(),
    api_mode=api_mode,
    supports_health_check=False,
    fallback_models=(model,),
    default_aux_model=model,
)

register_provider(oomol)

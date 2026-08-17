"""OOMOL-managed Jina Reader web search provider for Hermes.

This plugin invokes the authenticated OO Fusion API instead of requiring a
separate Jina API key. It intentionally implements search only: page
extraction remains unavailable in the OOMOL runtime.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from typing import Any, Dict

from agent.web_search_provider import WebSearchProvider
from oomol_hermes_oo import require_oo_authentication


_SERVICE = "fusion-api"
_ACTION = "jina_reader_search"
_TIMEOUT_SECONDS = 45
_RESULT_PATTERN = re.compile(
    r"^\[(?P<position>\d+)\] Title: (?P<title>.*?)\n"
    r"\[(?P=position)\] URL Source: (?P<url>.*?)\n"
    r"\[(?P=position)\] Description: (?P<description>.*?)(?=\n\n\[\d+\] Title:|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _run_search(query: str) -> Dict[str, Any]:
    """Run the documented OO Fusion Jina Reader search action."""
    command = [
        "oo", "connector", "run", _SERVICE, "--action", _ACTION, "--data",
        json.dumps({"content": query}, ensure_ascii=False), "--json",
    ]
    try:
        completed = subprocess.run(
            command, check=False, text=True, capture_output=True, timeout=_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("The `oo` CLI is required for OOMOL Jina web search.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("OOMOL Jina web search timed out.") from exc
    if completed.returncode != 0:
        raise RuntimeError(
            f"OOMOL Jina web search failed with exit code {completed.returncode}."
        )
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OOMOL Jina web search returned invalid JSON.") from exc
    if not isinstance(response, dict):
        raise RuntimeError("OOMOL Jina web search returned unexpected JSON.")
    return response


def _normalize_results(response: Dict[str, Any], limit: int) -> list[Dict[str, Any]]:
    """Convert Jina Reader's indexed text response to Hermes web results."""
    data = response.get("data")
    content = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content, str):
        raise RuntimeError("OOMOL Jina web search response is missing data.content.")

    results = []
    for match in _RESULT_PATTERN.finditer(content):
        title = match.group("title").strip()
        url = match.group("url").strip()
        if not url:
            continue
        results.append(
            {
                "title": title,
                "url": url,
                "description": match.group("description").strip(),
                "position": len(results) + 1,
            }
        )
        if len(results) >= limit:
            break
    if content.strip() and not results:
        raise RuntimeError("OOMOL Jina web search returned an unrecognized result format.")
    return results


class OOJinaWebSearchProvider(WebSearchProvider):
    """Search the web through the OOMOL-managed Jina Reader action."""

    @property
    def name(self) -> str:
        return "oo_jina"

    @property
    def display_name(self) -> str:
        return "OOMOL Jina Reader Search"

    def is_available(self) -> bool:
        """Check only for the CLI; authentication is validated on execution."""
        return shutil.which("oo") is not None

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return False

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        try:
            bounded_limit = min(max(int(limit), 1), 100)
        except (TypeError, ValueError):
            bounded_limit = 5
        try:
            require_oo_authentication()
            return {
                "success": True,
                "data": {"web": _normalize_results(_run_search(query), bounded_limit)},
            }
        except RuntimeError as exc:
            return {"success": False, "error": str(exc)}

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": self.display_name,
            "badge": "OOMOL",
            "tag": "Managed Jina Reader search through the authenticated OO CLI.",
            "env_vars": [],
        }


def register(ctx: Any) -> None:
    """Register the OOMOL-managed web-search provider."""
    ctx.register_web_search_provider(OOJinaWebSearchProvider())

#!/usr/bin/env python3
"""Materialize non-secret OOMOL runtime settings in Hermes config YAML."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


MODEL_SETTINGS = {
    "default": ("${OO_LLM_MODEL}", "OO_LLM_MODEL"),
    "base_url": ("${OO_LLM_BASE_URL}", "OO_LLM_BASE_URL"),
    "api_mode": ("${OO_LLM_API_MODE}", "OO_LLM_API_MODE"),
}

MANAGED_MODEL_STATE = ".oomol-managed-model.json"

LEGACY_TERMINAL_ENV_PASSTHROUGH = """\
  env_passthrough:
    - OO_CONFIG_DIR
    - OO_API_KEY
    - OO_LLM_BASE_URL
    - OO_LLM_MODEL
    - OO_LLM_API_MODE
"""

TERMINAL_ENV_PASSTHROUGH = """\
  env_passthrough:
    - OO_CONFIG_DIR
"""


def _replace_model_scalar(
    content: str,
    key: str,
    expected: str,
    replacement: str,
) -> tuple[str, bool]:
    lines = content.splitlines(keepends=True)
    in_model = False
    target = f"  {key}: {expected}"

    for index, line in enumerate(lines):
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        if body == "model:":
            in_model = True
            continue
        if in_model and body and not body.startswith((" ", "#")):
            break
        if in_model and body == target:
            lines[index] = f"  {key}: {replacement}{ending}"
            return "".join(lines), True

    return content, False


def _load_managed_model_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    model = payload.get("model") if isinstance(payload, dict) else None
    if not isinstance(model, dict):
        return {}
    return {
        key: value
        for key, value in model.items()
        if key in MODEL_SETTINGS and isinstance(value, str)
    }


def _write_atomic(path: Path, content: str, mode: int) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def materialize(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    rendered = original
    state_path = path.with_name(MANAGED_MODEL_STATE)
    previous_model = _load_managed_model_state(state_path)
    managed_model: dict[str, str] = {}

    for key, (placeholder, variable) in MODEL_SETTINGS.items():
        value = os.environ.get(variable, "").strip()
        if not value:
            raise RuntimeError(f"{variable} is required to materialize config.yaml")
        encoded = json.dumps(value, ensure_ascii=False)

        rendered, replaced = _replace_model_scalar(
            rendered,
            key,
            placeholder,
            encoded,
        )
        if replaced:
            managed_model[key] = value
            continue

        previous = previous_model.get(key)
        if previous is not None:
            rendered, replaced = _replace_model_scalar(
                rendered,
                key,
                json.dumps(previous, ensure_ascii=False),
                encoded,
            )
            if replaced:
                managed_model[key] = value
                continue

    rendered = rendered.replace(
        LEGACY_TERMINAL_ENV_PASSTHROUGH,
        TERMINAL_ENV_PASSTHROUGH,
    )

    changed = rendered != original
    if changed:
        _write_atomic(path, rendered, path.stat().st_mode & 0o777)

    state_content = json.dumps(
        {"version": 1, "model": managed_model},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    previous_state_content = (
        state_path.read_text(encoding="utf-8") if state_path.exists() else None
    )
    if state_content != previous_state_content:
        _write_atomic(state_path, state_content, 0o600)
        changed = True

    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    materialize(args.config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

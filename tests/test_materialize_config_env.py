from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/materialize-config-env.py"


def _run(config: Path, *, model: str) -> None:
    env = os.environ.copy()
    env.update(
        {
            "OO_LLM_MODEL": model,
            "OO_LLM_BASE_URL": "https://llm.example.com/v1",
            "OO_LLM_API_MODE": "codex_responses",
        }
    )
    subprocess.run(
        [sys.executable, str(SCRIPT), str(config)],
        check=True,
        cwd=ROOT,
        env=env,
    )


def test_materializes_only_supported_non_secret_placeholders(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        """\
# Preserve user comments.
model:
  provider: oomol
  default: ${OO_LLM_MODEL}
  base_url: ${OO_LLM_BASE_URL}
  api_mode: ${OO_LLM_API_MODE}
unrelated: ${KEEP_ME}
""",
        encoding="utf-8",
    )

    _run(config, model="deepseek-v4-flash")

    rendered = config.read_text(encoding="utf-8")
    parsed = yaml.safe_load(rendered)
    assert "# Preserve user comments." in rendered
    assert parsed["model"] == {
        "provider": "oomol",
        "default": "deepseek-v4-flash",
        "base_url": "https://llm.example.com/v1",
        "api_mode": "codex_responses",
    }
    assert parsed["unrelated"] == "${KEEP_ME}"
    assert "OO_API_KEY" not in rendered

    _run(config, model="replacement-refreshes-managed-config")
    assert yaml.safe_load(config.read_text(encoding="utf-8"))["model"]["default"] == (
        "replacement-refreshes-managed-config"
    )
    state = yaml.safe_load((tmp_path / ".oomol-managed-model.json").read_text())
    assert state["model"]["default"] == "replacement-refreshes-managed-config"


def test_removes_only_the_exact_legacy_terminal_passthrough(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        """\
terminal:
  backend: local
  env_passthrough:
    - OO_CONFIG_DIR
    - OO_API_KEY
    - OO_LLM_BASE_URL
    - OO_LLM_MODEL
    - OO_LLM_API_MODE
    - USER_CUSTOM_VALUE
other_passthrough:
  - OO_API_KEY
model:
  default: custom-model
""",
        encoding="utf-8",
    )

    _run(config, model="replacement-must-not-overwrite-user-config")

    parsed = yaml.safe_load(config.read_text(encoding="utf-8"))
    assert parsed["terminal"]["env_passthrough"] == [
        "OO_CONFIG_DIR",
        "USER_CUSTOM_VALUE",
    ]
    assert parsed["other_passthrough"] == ["OO_API_KEY"]
    assert parsed["model"]["default"] == "custom-model"


def test_preserves_user_model_value_after_managed_state_exists(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        """\
model:
  default: ${OO_LLM_MODEL}
  base_url: ${OO_LLM_BASE_URL}
  api_mode: ${OO_LLM_API_MODE}
""",
        encoding="utf-8",
    )

    _run(config, model="managed-model")
    rendered = config.read_text(encoding="utf-8").replace(
        '  default: "managed-model"',
        '  default: "user-model"',
    )
    config.write_text(rendered, encoding="utf-8")

    _run(config, model="new-runtime-model")

    assert yaml.safe_load(config.read_text(encoding="utf-8"))["model"]["default"] == (
        "user-model"
    )
    state = yaml.safe_load((tmp_path / ".oomol-managed-model.json").read_text())
    assert "default" not in state["model"]


def test_does_not_adopt_matching_preexisting_model_value(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        """\
model:
  default: "matching-model"
  base_url: "https://llm.example.com/v1"
  api_mode: "codex_responses"
""",
        encoding="utf-8",
    )

    _run(config, model="matching-model")
    _run(config, model="changed-runtime-model")

    assert yaml.safe_load(config.read_text(encoding="utf-8"))["model"]["default"] == (
        "matching-model"
    )
    state = yaml.safe_load((tmp_path / ".oomol-managed-model.json").read_text())
    assert state["model"] == {}

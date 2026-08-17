from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/configure-oo-skills.py"
FRAMEWORK_SKILLS = (
    "oo",
    "oo-create-skill",
    "oo-find-skills",
    "oo-publish-skill",
)


def _create_skill(root: Path, name: str) -> None:
    skill = root / name
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {'A' * 100}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _frontmatter(path: Path) -> dict[str, object]:
    raw = path.read_text(encoding="utf-8")[4:].split("\n---\n", 1)[0]
    parsed = yaml.safe_load(raw)
    assert isinstance(parsed, dict)
    return parsed


def test_configures_only_framework_skills(tmp_path: Path) -> None:
    for name in FRAMEWORK_SKILLS:
        _create_skill(tmp_path, name)
    _create_skill(tmp_path, "oo-github")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--skills-dir", str(tmp_path)],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "configured=4" in result.stdout
    for name in FRAMEWORK_SKILLS:
        metadata = _frontmatter(tmp_path / name / "SKILL.md")["metadata"]
        assert metadata["hermes"]["prompt_description_max_chars"] == 1200
    assert "metadata" not in _frontmatter(tmp_path / "oo-github" / "SKILL.md")


def test_missing_framework_skill_fails(tmp_path: Path) -> None:
    for name in FRAMEWORK_SKILLS[:-1]:
        _create_skill(tmp_path, name)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--skills-dir", str(tmp_path)],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert FRAMEWORK_SKILLS[-1] in result.stderr

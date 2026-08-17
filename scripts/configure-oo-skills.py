#!/usr/bin/env python3
"""Apply Hermes routing metadata to the OO framework Skills."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


OO_FRAMEWORK_SKILLS = (
    "oo",
    "oo-create-skill",
    "oo-find-skills",
    "oo-publish-skill",
)
PROMPT_DESCRIPTION_MAX_CHARS = 1200


def _parse_skill(path: Path) -> tuple[dict[str, Any], str]:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n") or "\n---\n" not in content[4:]:
        raise ValueError(f"invalid SKILL.md frontmatter: {path}")
    raw_frontmatter, body = content[4:].split("\n---\n", 1)
    frontmatter = yaml.safe_load(raw_frontmatter)
    if not isinstance(frontmatter, dict):
        raise ValueError(f"invalid SKILL.md frontmatter: {path}")
    return frontmatter, body


def _configure_skill(path: Path) -> None:
    frontmatter, body = _parse_skill(path)
    metadata = frontmatter.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError(f"invalid metadata mapping: {path}")
    hermes_metadata = metadata.setdefault("hermes", {})
    if not isinstance(hermes_metadata, dict):
        raise ValueError(f"invalid metadata.hermes mapping: {path}")
    hermes_metadata["prompt_description_max_chars"] = PROMPT_DESCRIPTION_MAX_CHARS
    rendered = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{rendered}---\n{body}", encoding="utf-8", newline="\n")


def configure(skills_dir: Path) -> int:
    for skill_name in OO_FRAMEWORK_SKILLS:
        skill_file = skills_dir / skill_name / "SKILL.md"
        if not skill_file.is_file() or skill_file.is_symlink():
            raise FileNotFoundError(f"missing OO framework skill: {skill_name}")
        _configure_skill(skill_file)
    return len(OO_FRAMEWORK_SKILLS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills-dir", required=True, type=Path)
    args = parser.parse_args()
    configured = configure(args.skills_dir)
    print(f"OO Skill metadata: configured={configured}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

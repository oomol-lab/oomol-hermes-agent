from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _docker_arg(name: str) -> str:
    content = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    match = re.search(rf"^ARG {re.escape(name)}=(.+)$", content, re.MULTILINE)
    assert match is not None, f"missing Docker ARG {name}"
    return match.group(1).strip()


def _frontmatter(path: Path) -> dict[str, object]:
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    raw = content[4:].split("\n---\n", 1)[0]
    parsed = yaml.safe_load(raw)
    assert isinstance(parsed, dict)
    return parsed


def test_version_lock_matches_docker_defaults() -> None:
    lock = json.loads((ROOT / "upstream.lock.json").read_text(encoding="utf-8"))
    assert _docker_arg("HERMES_COMMIT") == lock["hermes"]["commit"]
    assert _docker_arg("HERMES_VERSION") == lock["hermes"]["version"]
    assert _docker_arg("OO_CLI_VERSION") == lock["oo_cli"]["version"]
    assert (
        _docker_arg("OO_CLI_SHA256_AMD64")
        == lock["oo_cli"]["artifacts"]["linux-amd64"]["sha256"]
    )
    assert (
        _docker_arg("OO_CLI_SHA256_ARM64")
        == lock["oo_cli"]["artifacts"]["linux-arm64"]["sha256"]
    )


def test_curated_skill_allowlist_is_exact() -> None:
    expected = {
        "productivity/office-files",
        "productivity/pdf-files",
        "research/public-social-research",
    }
    configured = {
        line.split("#", 1)[0].strip()
        for line in (ROOT / "config/curated-skills.txt").read_text().splitlines()
        if line.split("#", 1)[0].strip()
    }
    actual = {
        path.parent.relative_to(ROOT / "skills").as_posix()
        for path in (ROOT / "skills").rglob("SKILL.md")
    }
    assert configured == expected
    assert actual == expected


def test_ordinary_skill_descriptions_respect_default_limit() -> None:
    for relative in (
        "skills/productivity/office-files/SKILL.md",
        "skills/productivity/pdf-files/SKILL.md",
    ):
        metadata = _frontmatter(ROOT / relative)
        description = metadata["description"]
        assert isinstance(description, str)
        assert len(description) <= 60
        assert description.endswith(".")


def test_long_curated_description_explicitly_opts_in() -> None:
    metadata = _frontmatter(
        ROOT / "skills/research/public-social-research/SKILL.md"
    )
    description = metadata["description"]
    assert isinstance(description, str) and len(description) > 60
    assert (
        metadata["metadata"]["hermes"]["prompt_description_max_chars"] == 1200
    )


def test_seeded_plugins_have_manifests_and_sources() -> None:
    config = yaml.safe_load((ROOT / "config/config.seed.yaml").read_text())
    enabled = config["plugins"]["enabled"]
    for key in enabled:
        plugin = ROOT / "plugins" / key
        assert (plugin / "plugin.yaml").is_file(), key
        assert (plugin / "__init__.py").is_file(), key


def test_description_patch_is_fail_closed() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    patch = (ROOT / "patches/0001-skill-description-opt-in.patch").read_text(
        encoding="utf-8"
    )
    assert "git apply --check" in dockerfile
    assert "SKILL_PROMPT_DESC_LIMIT" in patch
    assert "min(configured_max, 2000)" in patch


def test_public_compose_uses_published_image_and_persistent_data() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    service = compose["services"]["hermes"]
    assert service["image"].startswith(
        "${HERMES_IMAGE:-ghcr.io/oomol/oomol-hermes-agent:"
    )
    assert "build" not in service
    assert service["command"] == ["hermes", "gateway", "run"]
    assert "hermes-data:/data" in service["volumes"]
    assert "hermes-data" in compose["volumes"]
    assert service["environment"]["OO_API_KEY"] == "${OO_API_KEY:-}"
    assert "oo-auth" not in compose["services"]

    seed = yaml.safe_load((ROOT / "config/config.seed.yaml").read_text())
    assert "OO_API_KEY" in seed["terminal"]["env_passthrough"]


def test_development_compose_builds_the_local_image() -> None:
    compose = yaml.safe_load((ROOT / "compose.dev.yaml").read_text())
    service = compose["services"]["hermes"]
    assert service["image"] == "oomol-hermes-agent:dev"
    assert service["build"]["context"] == "."


def test_makefile_does_not_manage_oo_authentication() -> None:
    makefile = (ROOT / "Makefile").read_text()
    assert "oo auth" not in makefile
    assert "compose-auth" not in makefile


def test_scripts_compile() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "scripts", "plugins"],
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout

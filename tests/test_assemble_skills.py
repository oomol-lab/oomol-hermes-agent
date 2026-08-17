from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/assemble-skills.py"


def _skill(root: Path, relative: str) -> None:
    path = root / relative
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {path.name}\ndescription: Test.\n---\n",
        encoding="utf-8",
    )


def _run(source: Path, allowlist: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(source),
            "--allowlist",
            str(allowlist),
            "--output",
            str(output),
        ],
        check=False,
        text=True,
        capture_output=True,
    )


def test_assembles_only_allowlisted_skills(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _skill(source, "productivity/selected")
    _skill(source, "productivity/omitted")
    allowlist = tmp_path / "allowlist.txt"
    allowlist.write_text("productivity/selected\n", encoding="utf-8")
    output = tmp_path / "output"

    result = _run(source, allowlist, output)

    assert result.returncode == 0, result.stderr
    assert (output / "productivity/selected/SKILL.md").is_file()
    assert not (output / "productivity/omitted").exists()


def test_rejects_path_traversal(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    allowlist = tmp_path / "allowlist.txt"
    allowlist.write_text("../outside\n", encoding="utf-8")

    result = _run(source, allowlist, tmp_path / "output")

    assert result.returncode != 0
    assert "invalid skill path" in result.stderr

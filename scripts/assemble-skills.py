#!/usr/bin/env python3
"""Build the OOMOL Hermes bundled-skill tree from an explicit allowlist."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath


def parse_allowlist(path: Path) -> list[PurePosixPath]:
    entries: list[PurePosixPath] = []
    seen: set[str] = set()

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        value = raw_line.split("#", 1)[0].strip()
        if not value:
            continue
        if any(character.isspace() for character in value):
            raise ValueError(f"{path}:{line_number}: skill path must not contain whitespace")

        relative_path = PurePosixPath(value)
        normalized = relative_path.as_posix()
        if (
            relative_path.is_absolute()
            or not relative_path.parts
            or any(part in {"", ".", ".."} for part in relative_path.parts)
            or normalized != value
        ):
            raise ValueError(f"{path}:{line_number}: invalid skill path: {value}")

        if normalized in seen:
            raise ValueError(f"{path}:{line_number}: duplicate skill path: {value}")
        seen.add(normalized)
        entries.append(relative_path)

    if not entries:
        raise ValueError(f"{path}: allowlist must contain at least one skill")
    return entries


def _reject_symlinks(path: Path, label: str) -> None:
    if path.is_symlink() or any(child.is_symlink() for child in path.rglob("*")):
        raise ValueError(f"{label} contains a symlink: {path}")


def _resolve_skill_dir(source: Path, relative_path: PurePosixPath) -> Path:
    candidate = source
    for part in relative_path.parts:
        candidate /= part
        if candidate.is_symlink():
            raise ValueError(f"allowlisted skill path contains a symlink: {relative_path}")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(source)
    except ValueError as error:
        raise ValueError(f"allowlisted skill escapes source: {relative_path}") from error
    return resolved


def _validate_paths(source: Path, output: Path) -> tuple[Path, Path]:
    if not source.is_absolute() or not output.is_absolute():
        raise ValueError("source and output paths must be absolute")

    resolved_source = source.resolve(strict=True)
    resolved_output = output.resolve(strict=False)
    if resolved_source == Path("/") or resolved_output == Path("/"):
        raise ValueError("source and output paths must not be root")
    if resolved_source == resolved_output:
        raise ValueError("source and output paths must be different")
    try:
        resolved_output.relative_to(resolved_source)
    except ValueError:
        pass
    else:
        raise ValueError("output path must not be inside the source tree")
    if output.is_symlink():
        raise ValueError(f"output path must not be a symlink: {output}")
    return resolved_source, resolved_output


def _select_skills(
    source: Path,
    allowlist: Path,
) -> list[tuple[Path, PurePosixPath]]:
    entries = parse_allowlist(allowlist)
    selected: list[tuple[Path, PurePosixPath]] = []
    for relative_path in entries:
        try:
            skill_dir = _resolve_skill_dir(source, relative_path)
        except FileNotFoundError as error:
            raise ValueError(
                f"allowlisted skill directory does not exist: {relative_path}"
            ) from error
        if not skill_dir.is_dir():
            raise ValueError(f"allowlisted skill directory does not exist: {relative_path}")
        _reject_symlinks(skill_dir, f"allowlisted skill {relative_path}")
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            raise ValueError(f"allowlisted skill is missing SKILL.md: {relative_path}")
        selected.append((skill_dir, relative_path))
    return selected


def assemble_skills(
    source: Path,
    allowlist: Path,
    output: Path,
    additional_source: Path | None = None,
    additional_allowlist: Path | None = None,
) -> int:
    source, output = _validate_paths(source, output)
    if (additional_source is None) != (additional_allowlist is None):
        raise ValueError(
            "additional source and allowlist must be provided together"
        )

    selected = _select_skills(source, allowlist)
    if additional_source is not None and additional_allowlist is not None:
        additional_source, additional_output = _validate_paths(
            additional_source,
            output,
        )
        if additional_output != output:
            raise ValueError("additional source resolved to an unexpected output")
        selected.extend(_select_skills(additional_source, additional_allowlist))

    seen_paths: set[str] = set()
    for _skill_dir, relative_path in selected:
        normalized = relative_path.as_posix()
        if normalized in seen_paths:
            raise ValueError(f"duplicate assembled skill path: {relative_path}")
        seen_paths.add(normalized)

    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    backup: Path | None = None
    try:
        for skill_dir, relative_path in selected:
            destination = staging.joinpath(*relative_path.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(skill_dir, destination)
        shutil.copymode(source, staging)

        if output.exists():
            backup = output.with_name(f".{output.name}.previous.{os.getpid()}")
            if backup.exists() or backup.is_symlink():
                raise ValueError(f"refusing existing backup path: {backup}")
            os.replace(output, backup)
        os.replace(staging, output)
        if backup is not None:
            shutil.rmtree(backup)
        return len(selected)
    except BaseException:
        if backup is not None and backup.exists() and not output.exists():
            os.replace(backup, output)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--allowlist", required=True, type=Path)
    parser.add_argument("--additional-source", type=Path)
    parser.add_argument("--additional-allowlist", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    try:
        count = assemble_skills(
            args.source,
            args.allowlist,
            args.output,
            args.additional_source,
            args.additional_allowlist,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"OOMOL Hermes bundled skills: selected={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

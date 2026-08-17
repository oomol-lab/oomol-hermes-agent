from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(
    *command: str,
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    return subprocess.run(
        command,
        cwd=cwd,
        env=process_env,
        check=check,
        capture_output=True,
        text=True,
    )


def _release_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    (repository / "scripts").mkdir(parents=True)
    for name in (
        "prepare-release.sh",
        "release.sh",
        "generate-release-notes.sh",
        "generate-release-summary.py",
        "release-summary-context.md",
    ):
        shutil.copy2(ROOT / "scripts" / name, repository / "scripts" / name)
    shutil.copy2(ROOT / "upstream.lock.json", repository / "upstream.lock.json")
    shutil.copy2(ROOT / "Dockerfile", repository / "Dockerfile")

    _run("git", "init", "-b", "main", cwd=repository)
    _run("git", "config", "user.name", "Release Test", cwd=repository)
    _run("git", "config", "user.email", "release@example.invalid", cwd=repository)
    _run("git", "add", ".", cwd=repository)
    _run("git", "commit", "-m", "initial", cwd=repository)
    return repository


def _prepare_env(repository: Path) -> dict[str, str]:
    return {
        "REPO_ROOT": str(repository),
        "RELEASE_DISPATCH_SHA": _run(
            "git", "rev-parse", "HEAD", cwd=repository
        ).stdout.strip(),
        "PREPARE_RELEASE_TODAY": "2026.08.17",
        "PREPARE_RELEASE_SKIP_FETCH_TAGS": "1",
    }


def test_prepare_release_creates_annotated_tag_from_lock(tmp_path: Path) -> None:
    repository = _release_repository(tmp_path)
    result = _run(
        "scripts/prepare-release.sh",
        "--tag",
        "v2026.08.17-1",
        cwd=repository,
        env=_prepare_env(repository),
    )

    assert "prepare-release: v2026.08.17-1" in result.stdout
    assert _run(
        "git", "cat-file", "-t", "v2026.08.17-1", cwd=repository
    ).stdout.strip() == "tag"
    tag_message = _run(
        "git", "for-each-ref", "--format=%(contents)",
        "refs/tags/v2026.08.17-1", cwd=repository
    ).stdout
    lock = json.loads((repository / "upstream.lock.json").read_text())
    assert f"HERMES_COMMIT={lock['hermes']['commit']}" in tag_message
    assert f"HERMES_VERSION={lock['hermes']['version']}" in tag_message
    assert f"OO_CLI_VERSION={lock['oo_cli']['version']}" in tag_message

    dry_run = _run(
        "scripts/prepare-release.sh",
        "--dry-run",
        cwd=repository,
        env=_prepare_env(repository),
    )
    assert "release tag: v2026.08.17-2" in dry_run.stdout


def test_release_dry_run_rejects_metadata_drift(tmp_path: Path) -> None:
    repository = _release_repository(tmp_path)
    env = _prepare_env(repository)
    _run(
        "scripts/prepare-release.sh",
        "--tag",
        "v2026.08.17-1",
        cwd=repository,
        env=env,
    )
    commit = env["RELEASE_DISPATCH_SHA"]
    release_env = {
        "REPO_ROOT": str(repository),
        "RELEASE_TAG": "v2026.08.17-1",
        "RELEASE_COMMIT_SHA": commit,
        "IMAGE_REPOSITORY": "ghcr.io/oomol-lab/oomol-hermes-agent",
        "DRY_RUN": "1",
    }
    result = _run("scripts/release.sh", cwd=repository, env=release_env)
    assert "platforms: linux/amd64,linux/arm64" in result.stdout
    assert "release: dry run complete" in result.stdout

    lock_path = repository / "upstream.lock.json"
    lock = json.loads(lock_path.read_text())
    lock["oo_cli"]["version"] = "9.9.9"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    rejected = _run(
        "scripts/release.sh",
        cwd=repository,
        env=release_env,
        check=False,
    )
    assert rejected.returncode != 0
    assert "does not match upstream.lock.json" in rejected.stderr


def test_release_script_builds_verifiable_multi_platform_image() -> None:
    release_script = (ROOT / "scripts/release.sh").read_text()

    assert "linux/amd64,linux/arm64" in release_script
    assert "--provenance=mode=max" in release_script
    assert "--sbom=true" in release_script
    assert "version/SHA digest mismatch" in release_script
    assert "version/latest digest mismatch" in release_script


def test_generate_release_notes_exports_optional_ai_summary(tmp_path: Path) -> None:
    repository = _release_repository(tmp_path)
    previous_tag = "v2026.08.17-1"
    release_tag = "v2026.08.17-2"
    _run("git", "tag", "-a", previous_tag, "-m", previous_tag, cwd=repository)
    (repository / "README.md").write_text("reader-visible change\n", encoding="utf-8")
    _run("git", "add", "README.md", cwd=repository)
    _run("git", "commit", "-m", "feat: improve startup diagnostics", cwd=repository)
    release_commit = _run("git", "rev-parse", "HEAD", cwd=repository).stdout.strip()
    _run("git", "tag", "-a", release_tag, "-m", release_tag, cwd=repository)
    summary_file = tmp_path / "release-summary.md"

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            body = json.dumps(
                {"choices": [{"message": {"content": "本版本改善了启动诊断。"}}]}
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        result = _run(
            "scripts/generate-release-notes.sh",
            cwd=repository,
            env={
                "REPO_ROOT": str(repository),
                "RELEASE_TAG": release_tag,
                "RELEASE_COMMIT_SHA": release_commit,
                "RELEASE_IMAGE": f"ghcr.io/example/hermes:{release_tag}",
                "RELEASE_IMAGE_DIGEST": "sha256:test",
                "RELEASE_HERMES_VERSION": "0.20.2",
                "RELEASE_OO_CLI_VERSION": "1.7.4",
                "IMAGE_REPOSITORY": "ghcr.io/example/hermes",
                "OOMOL_RELEASE_SUMMARY_API_KEY": "test-key",
                "OOMOL_RELEASE_SUMMARY_BASE_URL": (
                    f"http://127.0.0.1:{server.server_port}/v1"
                ),
                "RELEASE_SUMMARY_FILE": str(summary_file),
            },
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert "## Release summary\n\n本版本改善了启动诊断。" in result.stdout
    assert "feat: improve startup diagnostics" in result.stdout
    assert summary_file.read_text(encoding="utf-8") == "本版本改善了启动诊断。\n"

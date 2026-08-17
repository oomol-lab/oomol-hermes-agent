"""Bounded, shared OO device-login handling for Hermes providers."""

from __future__ import annotations

import json
import re
import subprocess
import threading
from dataclasses import dataclass, field
from typing import IO, Any


_AUTH_STATUS_TIMEOUT_SECONDS = 10
_LOGIN_URL_TIMEOUT_SECONDS = 20
_LOGIN_COMPLETION_TIMEOUT_SECONDS = 600
_LOGIN_TERMINATE_GRACE_SECONDS = 5
_LOGIN_URL_PATTERN = re.compile(
    r"https://console\.oomol\.com/login/device\?[^\s]+"
)


class OOLoginRequired(RuntimeError):
    """Raised with a browser URL while OO CLI waits for device login."""

    def __init__(self, login_url: str) -> None:
        self.login_url = login_url
        super().__init__(
            "OOMOL authentication is required. Open this login URL in your "
            f"browser: {login_url} After login completes, retry the request."
        )


@dataclass
class _LoginAttempt:
    process: subprocess.Popen[str]
    ready: threading.Event = field(default_factory=threading.Event)
    login_url: str | None = None
    expiry_timer: threading.Timer | None = None


_login_lock = threading.Lock()
_login_attempt: _LoginAttempt | None = None


def _extract_login_url(line: str) -> str | None:
    match = _LOGIN_URL_PATTERN.search(line)
    return match.group(0) if match else None


def _consume_login_output(attempt: _LoginAttempt, output: IO[str]) -> None:
    global _login_attempt

    try:
        for line in output:
            if attempt.login_url is not None:
                continue
            if login_url := _extract_login_url(line):
                attempt.login_url = login_url
                attempt.ready.set()
        attempt.process.wait()
    finally:
        if attempt.expiry_timer is not None:
            attempt.expiry_timer.cancel()
        attempt.ready.set()
        with _login_lock:
            if _login_attempt is attempt:
                _login_attempt = None


def _terminate_login_attempt(attempt: _LoginAttempt) -> None:
    if attempt.process.poll() is not None:
        return
    attempt.process.terminate()
    try:
        attempt.process.wait(timeout=_LOGIN_TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        attempt.process.kill()


def _new_login_attempt() -> _LoginAttempt:
    try:
        process = subprocess.Popen(
            ["oo", "auth", "login"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("The `oo` CLI is required for OOMOL providers.") from exc

    if process.stdout is None:
        process.terminate()
        raise RuntimeError("OO device login did not expose an output stream.")

    attempt = _LoginAttempt(process=process)
    attempt.expiry_timer = threading.Timer(
        _LOGIN_COMPLETION_TIMEOUT_SECONDS,
        _terminate_login_attempt,
        args=(attempt,),
    )
    attempt.expiry_timer.daemon = True
    attempt.expiry_timer.start()
    threading.Thread(
        target=_consume_login_output,
        args=(attempt, process.stdout),
        name="oo-device-login",
        daemon=True,
    ).start()
    return attempt


def _device_login_url(timeout: float = _LOGIN_URL_TIMEOUT_SECONDS) -> str:
    global _login_attempt

    with _login_lock:
        attempt = _login_attempt
        if attempt is None or attempt.process.poll() is not None:
            attempt = _new_login_attempt()
            _login_attempt = attempt

    attempt.ready.wait(timeout)
    if attempt.login_url is not None:
        return attempt.login_url

    _terminate_login_attempt(attempt)
    raise RuntimeError("Timed out while starting OO device login. Retry the request.")


def _read_auth_status() -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["oo", "auth", "status", "--json"],
            check=False,
            text=True,
            capture_output=True,
            timeout=_AUTH_STATUS_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("The `oo` CLI is required for OOMOL providers.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("OO authentication status check timed out.") from exc

    if completed.returncode != 0:
        raise RuntimeError(
            f"OO authentication status check failed with exit code {completed.returncode}."
        )
    try:
        status = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OO authentication status returned invalid JSON.") from exc
    if not isinstance(status, dict):
        raise RuntimeError("OO authentication status returned an unexpected response.")
    return status


def require_oo_authentication() -> None:
    """Return when authenticated, otherwise raise with a live device-login URL."""
    status = _read_auth_status()
    env_override = status.get("envOverride")
    if (
        isinstance(env_override, dict)
        and env_override.get("apiKeyStatus") == "invalid"
    ):
        raise RuntimeError(
            "OO_API_KEY is invalid. Correct or remove it before using device login."
        )
    if status.get("status") == "logged-in":
        return
    raise OOLoginRequired(_device_login_url())

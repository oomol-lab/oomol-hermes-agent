from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "plugins" / "common"))

from oomol_hermes_oo import auth  # noqa: E402


def _status(value: dict[str, object]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["oo", "auth", "status", "--json"],
        returncode=0,
        stdout=json.dumps(value),
        stderr="",
    )


def test_authenticated_status_does_not_start_device_login(monkeypatch) -> None:
    monkeypatch.setattr(
        auth.subprocess,
        "run",
        lambda *args, **kwargs: _status({"status": "logged-in"}),
    )
    monkeypatch.setattr(
        auth,
        "_device_login_url",
        lambda: pytest.fail("device login should not start"),
    )

    auth.require_oo_authentication()


def test_logged_out_status_returns_device_login_url(monkeypatch) -> None:
    login_url = "https://console.oomol.com/login/device?user_code=TEST12"
    monkeypatch.setattr(
        auth.subprocess,
        "run",
        lambda *args, **kwargs: _status({"status": "logged-out"}),
    )
    monkeypatch.setattr(auth, "_device_login_url", lambda: login_url)

    with pytest.raises(auth.OOLoginRequired, match=re.escape(login_url)) as raised:
        auth.require_oo_authentication()

    assert raised.value.login_url == login_url


def test_invalid_environment_key_does_not_start_device_login(monkeypatch) -> None:
    monkeypatch.setattr(
        auth.subprocess,
        "run",
        lambda *args, **kwargs: _status(
            {
                "status": "logged-in",
                "envOverride": {"apiKeyStatus": "invalid"},
            }
        ),
    )
    monkeypatch.setattr(
        auth,
        "_device_login_url",
        lambda: pytest.fail("device login should not start"),
    )

    with pytest.raises(RuntimeError, match="OO_API_KEY is invalid"):
        auth.require_oo_authentication()

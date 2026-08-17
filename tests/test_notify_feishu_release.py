from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = ROOT / "scripts/notify-feishu-release.py"
    spec = importlib.util.spec_from_file_location("notify_feishu_release", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_signed_payload_matches_feishu_signature_contract(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module.time, "time", lambda: 1_700_000_000)

    payload = json.loads(module.signed_payload("发布成功", "test-secret"))
    expected_sign = base64.b64encode(
        hmac.new(
            b"1700000000\ntest-secret",
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("ascii")

    assert payload == {
        "msg_type": "text",
        "content": {"text": "发布成功"},
        "timestamp": "1700000000",
        "sign": expected_sign,
    }


def test_unsigned_payload_omits_signature_fields() -> None:
    module = _load_module()
    payload = json.loads(module.signed_payload("published", ""))

    assert payload == {
        "msg_type": "text",
        "content": {"text": "published"},
    }

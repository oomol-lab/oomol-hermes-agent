#!/usr/bin/env python3
"""Send a Hermes Agent release notification through a Feishu custom bot."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def feishu_signature(secret: str) -> tuple[str, str] | None:
    if not secret:
        return None
    timestamp = str(int(time.time()))
    sign = base64.b64encode(
        hmac.new(
            f"{timestamp}\n{secret}".encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("ascii")
    return timestamp, sign


def signed_payload(text: str, secret: str) -> bytes:
    payload: dict[str, object] = {
        "msg_type": "text",
        "content": {"text": text},
    }
    signature = feishu_signature(secret)
    if signature is not None:
        payload["timestamp"], payload["sign"] = signature
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def send_message(webhook: str, payload: bytes, target: str) -> None:
    request = urllib.request.Request(
        webhook,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=15) as response:
            response_payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"Feishu {target} notification failed: HTTP {exc.code}"
        ) from None
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Feishu {target} notification failed: {exc.reason}"
        ) from None
    except TimeoutError:
        raise SystemExit(f"Feishu {target} notification timed out") from None
    except json.JSONDecodeError:
        raise SystemExit(
            f"Feishu {target} notification returned invalid JSON"
        ) from None

    if not isinstance(response_payload, dict) or response_payload.get(
        "code", response_payload.get("StatusCode")
    ) != 0:
        raise SystemExit(f"Feishu {target} notification was rejected")


def main() -> None:
    release_tag = required_env("RELEASE_TAG")
    release_image = required_env("RELEASE_IMAGE")
    repository = required_env("GITHUB_REPOSITORY")
    server_url = required_env("GITHUB_SERVER_URL").rstrip("/")
    run_id = required_env("GITHUB_RUN_ID")
    webhook = required_env("FEISHU_RELEASE_WEBHOOK")
    secret = os.getenv("FEISHU_RELEASE_SECRET", "")
    summary = os.getenv("RELEASE_SUMMARY", "").strip()

    message_lines = [
        f"Hermes Agent {release_tag} 已发布",
        "",
        f"镜像：{release_image}",
        f"Release：{server_url}/{repository}/releases/tag/{release_tag}",
        f"Workflow：{server_url}/{repository}/actions/runs/{run_id}",
    ]
    if summary:
        message_lines.extend(("", "发布摘要：", summary))

    send_message(
        webhook,
        signed_payload(
            "\n".join(message_lines),
            secret,
        ),
        "release group",
    )


if __name__ == "__main__":
    main()

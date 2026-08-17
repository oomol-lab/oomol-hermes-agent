"""OOMOL/OOCI GPT Image 2 image generation backend for Hermes."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    resolve_aspect_ratio,
    save_b64_image,
    save_url_image,
    success_response,
)


PROVIDER_NAME = "oo_gpt_image_2"
DEFAULT_SERVICE = "fusion-api"
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_QUALITY = "high"
DEFAULT_N = 1

_ASPECT_TO_SIZE = {
    "landscape": "2048x1152",
    "square": "1024x1024",
    "portrait": "1152x2048",
}

_TEXT_SUBMIT_ACTION = "openai_image_async_submit"
_TEXT_RESULT_ACTION = "openai_image_async_result"
_EDIT_SUBMIT_ACTION = "openai_image_edit_async_submit"
_EDIT_RESULT_ACTION = "openai_image_edit_async_result"

_PROCESS_ERROR_PREVIEW_MAX_CHARS = 2_000
_SENSITIVE_PROCESS_OUTPUT_PATTERNS = (
    # Match a bearer credential before generic key/value patterns can consume
    # only its ``Bearer`` prefix.
    re.compile(r'(?i)\bbearer\b[^\r\n,;]*'),
    # Structured payload fields that can carry credentials or user input.
    re.compile(
        r'(?i)("(?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|'
        r'token|secret|password|cookie|prompt|image_url|images)"\s*:\s*)'
        r'("(?:[^"\\]|\\.)*"|\[[^\]]*\]|\{[^}]*\}|[^,\s}]+)'
    ),
    # Textual CLI diagnostics commonly include these forms.
    re.compile(
        r'(?i)(\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|'
        r'token|secret|password|cookie)\b\s*(?:[:=]\s*|\s+))[^\s,;]+'
    ),
    # Keep generic test/sentinel values and obvious sensitive labels out of logs.
    re.compile(r'(?i)\bsecret[-\w]*\b'),
    re.compile(r'(?i)\bsensitive\s+stdout\b'),
)


def _safe_process_error_output(stdout: str, stderr: str) -> str:
    """Return a bounded, redacted preview of a failed OO CLI invocation."""
    parts: list[str] = []
    for label, output in (("stderr", stderr), ("stdout", stdout)):
        value = output.strip()
        if not value:
            continue
        for pattern in _SENSITIVE_PROCESS_OUTPUT_PATTERNS:
            value = pattern.sub(
                lambda match: (
                    f"{match.group(1)}<redacted>"
                    if match.lastindex and match.group(1) is not None
                    else "<redacted>"
                ),
                value,
            )
        parts.append(f"{label}: {value}")

    return " | ".join(parts)[:_PROCESS_ERROR_PREVIEW_MAX_CHARS]


def _env_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _run_oo_connector(action: str, payload: dict[str, Any], *, service: str) -> dict[str, Any]:
    cmd = [
        "oo",
        "connector",
        "run",
        service,
        "--action",
        action,
        "--data",
        json.dumps(payload, ensure_ascii=False),
        "--json",
    ]

    organization = os.environ.get("OO_GPT_IMAGE_2_ORGANIZATION") or os.environ.get("OO_IMAGE_ORGANIZATION")
    personal = _env_bool("OO_GPT_IMAGE_2_PERSONAL")
    if personal is None:
        personal = _env_bool("OO_IMAGE_PERSONAL")
    if organization and personal:
        raise ValueError("OO_GPT_IMAGE_2_ORGANIZATION/OO_IMAGE_ORGANIZATION and personal mode cannot both be set.")
    if organization:
        cmd.extend(["--organization", organization])
    elif personal:
        cmd.append("--personal")

    try:
        proc = subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=900)
    except FileNotFoundError as exc:
        raise RuntimeError("The `oo` CLI is required for the oo_gpt_image_2 image provider.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"oo connector action timed out: {action}") from exc

    if proc.returncode != 0:
        message = f"oo connector action {action} failed with exit code {proc.returncode}"
        if detail := _safe_process_error_output(proc.stdout, proc.stderr):
            message = f"{message}: {detail}"
        raise RuntimeError(message)

    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"oo connector action {action} returned invalid JSON") from exc

    if isinstance(parsed, dict) and isinstance(parsed.get("data"), dict):
        return parsed["data"]
    if isinstance(parsed, dict):
        return parsed
    raise RuntimeError(f"oo connector action {action} returned unexpected JSON")


def _run_oo_file_upload(path: str) -> str:
    cmd = ["oo", "file", "upload", path, "--json"]
    try:
        proc = subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=300)
    except FileNotFoundError as exc:
        raise RuntimeError("The `oo` CLI is required to upload local reference images.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"oo file upload timed out: {path}") from exc

    if proc.returncode != 0:
        raise RuntimeError(f"oo file upload failed with exit code {proc.returncode}")

    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("oo file upload returned invalid JSON") from exc
    download_url = parsed.get("downloadUrl") if isinstance(parsed, dict) else None
    if not isinstance(download_url, str) or not download_url.strip():
        raise RuntimeError("oo file upload response missing downloadUrl")
    return download_url.strip()


def _extract_session_id(payload: dict[str, Any]) -> str:
    session_id = (
        payload.get("sessionId")
        or payload.get("sessionID")
        or payload.get("taskId")
        or payload.get("taskID")
        or (payload.get("task") or {}).get("id")
    )
    if not isinstance(session_id, str) or not session_id.strip():
        raise RuntimeError("GPT Image 2 submit response missing sessionId")
    return session_id


def _poll_result(session_id: str, *, action: str, service: str) -> dict[str, Any]:
    interval = float(os.environ.get("OO_GPT_IMAGE_2_POLL_SECONDS") or os.environ.get("OO_IMAGE_POLL_SECONDS") or "5")
    timeout = float(os.environ.get("OO_GPT_IMAGE_2_TIMEOUT_SECONDS") or os.environ.get("OO_IMAGE_TIMEOUT_SECONDS") or "1800")
    start = time.time()

    while True:
        payload = _run_oo_connector(action, {"sessionID": session_id}, service=service)
        state = str(payload.get("state") or "").strip().lower()
        if state in {"completed", "complete", "succeeded", "success"}:
            data = payload.get("data")
            return data if isinstance(data, dict) else payload
        if state in {"failed", "error", "canceled", "cancelled", "not_found"}:
            raise RuntimeError(f"GPT Image 2 task failed with state {state or 'unknown'}")
        if time.time() - start > timeout:
            raise RuntimeError(f"Timed out after {timeout:.0f}s waiting for GPT Image 2 session {session_id}")
        time.sleep(interval)


def _walk_values(value: Any):
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)
    else:
        yield value


def _extract_image_payload(payload: dict[str, Any]) -> tuple[str, str] | None:
    data = payload.get("data")
    if isinstance(data, dict):
        nested = _extract_image_payload(data)
        if nested is not None:
            return nested
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for key in ("url", "image_url", "imageUrl", "b64_json", "base64", "b64"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        return _classify_image_value(value.strip(), key=key)

    images = payload.get("images")
    if isinstance(images, list):
        for image in images:
            if isinstance(image, dict):
                for key in ("url", "image_url", "imageUrl", "base64", "b64", "b64_json"):
                    value = image.get(key)
                    if isinstance(value, str) and value.strip():
                        return _classify_image_value(value.strip(), key=key)
            elif isinstance(image, str) and image.strip():
                return _classify_image_value(image.strip())

    for value in _walk_values(payload):
        if isinstance(value, str) and value.strip():
            maybe = _classify_image_value(value.strip())
            if maybe is not None:
                return maybe
    return None


def _classify_image_value(value: str, *, key: str = "") -> tuple[str, str] | None:
    if value.startswith(("http://", "https://")):
        return ("url", value)
    if value.startswith("data:image/"):
        _, _, b64_data = value.partition(",")
        if b64_data:
            return ("base64", b64_data)
    if key.lower() in {"b64_json", "base64", "b64"}:
        return ("base64", value)
    return None


def _normalize_reference(ref: str) -> str:
    value = ref.strip()
    if value.startswith(("http://", "https://")):
        return value
    if value.startswith("file://"):
        value = value[7:]
    expanded = os.path.expanduser(value)
    if os.path.isfile(expanded):
        return _run_oo_file_upload(expanded)
    if value.startswith("data:image/"):
        suffix = ".png"
        header = value.split(",", 1)[0]
        if "image/jpeg" in header or "image/jpg" in header:
            suffix = ".jpg"
        elif "image/webp" in header:
            suffix = ".webp"
        _, _, b64_data = value.partition(",")
        if not b64_data:
            raise RuntimeError("Inline data image is missing base64 payload.")
        tmp_path = Path(os.environ.get("TMPDIR") or "/tmp") / f"oo_gpt_image_2_ref_{int(time.time() * 1000)}{suffix}"
        tmp_path.write_bytes(base64.b64decode(b64_data))
        try:
            return _run_oo_file_upload(str(tmp_path))
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return value


class OOGPTImage2Provider(ImageGenProvider):
    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def display_name(self) -> str:
        return "OOMOL GPT Image 2"

    def is_available(self) -> bool:
        return shutil.which("oo") is not None

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "gpt-image-2",
                "display": "GPT Image 2",
                "speed": "~30-120s",
                "strengths": "OOCI/Fusion API text-to-image and image editing through oo connector",
                "price": "OOMOL connector billing",
            }
        ]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "OOMOL GPT Image 2",
            "badge": "oomol",
            "tag": "Uses `oo connector run fusion-api`; no OPENAI_API_KEY required.",
            "env_vars": [],
        }

    def capabilities(self) -> Dict[str, Any]:
        return {"modalities": ["text", "image"], "max_reference_images": 16}

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        *,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        aspect = resolve_aspect_ratio(aspect_ratio)
        model = str(kwargs.get("model") or os.environ.get("OO_GPT_IMAGE_2_MODEL") or DEFAULT_MODEL).strip()
        service = os.environ.get("OO_GPT_IMAGE_2_SERVICE") or DEFAULT_SERVICE
        output_format = str(kwargs.get("output_format") or os.environ.get("OO_GPT_IMAGE_2_OUTPUT_FORMAT") or DEFAULT_OUTPUT_FORMAT).strip()
        quality = str(kwargs.get("quality") or os.environ.get("OO_GPT_IMAGE_2_QUALITY") or DEFAULT_QUALITY).strip()
        size = str(kwargs.get("size") or os.environ.get("OO_GPT_IMAGE_2_SIZE") or _ASPECT_TO_SIZE[aspect]).strip()
        n = int(kwargs.get("n") or os.environ.get("OO_GPT_IMAGE_2_N") or DEFAULT_N)

        refs: list[str] = []
        if isinstance(image_url, str) and image_url.strip():
            refs.append(image_url.strip())
        for ref in reference_image_urls or []:
            if isinstance(ref, str) and ref.strip():
                refs.append(ref.strip())
        refs = refs[:16]

        request: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "output_format": output_format,
            "quality": quality,
            "size": size,
            "n": n,
        }

        action_submit = _TEXT_SUBMIT_ACTION
        action_result = _TEXT_RESULT_ACTION
        modality = "text"
        if refs:
            action_submit = _EDIT_SUBMIT_ACTION
            action_result = _EDIT_RESULT_ACTION
            modality = "image"
            request["images"] = [{"image_url": _normalize_reference(ref)} for ref in refs]

        try:
            submit_payload = _run_oo_connector(action_submit, request, service=service)
            session_id = _extract_session_id(submit_payload)
            result_payload = _poll_result(session_id, action=action_result, service=service)
            image_payload = _extract_image_payload(result_payload)
            if image_payload is None:
                raise RuntimeError("GPT Image 2 result did not contain an image")

            kind, value = image_payload
            response_extra = {
                "session_id": session_id,
                "size": size,
                "quality": quality,
            }
            if kind == "base64":
                path = save_b64_image(value, prefix="oo_gpt_image_2", extension=output_format)
            else:
                path = save_url_image(value, prefix="oo_gpt_image_2", timeout=120)
                response_extra["remote_url"] = value

            return success_response(
                image=str(path),
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
                provider=PROVIDER_NAME,
                modality=modality,
                extra=response_extra,
            )
        except Exception as exc:  # noqa: BLE001
            return error_response(
                error=str(exc),
                error_type=type(exc).__name__,
                provider=PROVIDER_NAME,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )


def register(ctx) -> None:
    ctx.register_image_gen_provider(OOGPTImage2Provider())

"""OOMOL/OOCI Nano Banana image generation backend for Hermes."""

from __future__ import annotations

import base64
import json
import os
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
from oomol_hermes_oo import require_oo_authentication


PROVIDER_NAME = "oo_nano_banana"
DEFAULT_SERVICE = "fusion-api"
DEFAULT_MODEL = "nano-banana-pro"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_RESOLUTION = "1K"

_ASPECT_TO_NATIVE = {
    "landscape": "16:9",
    "square": "1:1",
    "portrait": "9:16",
}

_ACTION_SETS = {
    "nano-banana-pro": {
        "submit": "fal_nano_banana_pro_submit",
        "result": "fal_nano_banana_pro_result",
        "image_urls_field": "imageUrls",
        "resolution_field": "resolution",
    },
    "nano-banana-2": {
        "submit": "fal_nano_banana_2_submit",
        "result": "fal_nano_banana_2_result",
        "image_urls_field": "imageURLs",
        "resolution_field": "resolution",
    },
    "nano-banana": {
        "submit": "fal_nano_banana_submit",
        "result": "fal_nano_banana_result",
        "image_urls_field": "imageURLs",
        "resolution_field": None,
    },
}

_MODEL_ALIASES = {
    "pro": "nano-banana-pro",
    "nano_banana_pro": "nano-banana-pro",
    "nanobanana-pro": "nano-banana-pro",
    "2": "nano-banana-2",
    "v2": "nano-banana-2",
    "nano_banana_2": "nano-banana-2",
    "legacy": "nano-banana",
    "fal": "nano-banana",
}


def _env_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_model(model: Optional[str]) -> str:
    raw = (
        model
        or os.environ.get("OO_NANO_BANANA_VARIANT")
        or os.environ.get("OO_NANO_BANANA_MODEL")
        or DEFAULT_MODEL
    )
    normalized = _MODEL_ALIASES.get(raw.strip().lower(), raw.strip().lower())
    if normalized not in _ACTION_SETS:
        raise ValueError(
            f"Unsupported Nano Banana model '{raw}'. "
            f"Supported: {', '.join(sorted(_ACTION_SETS))}"
        )
    return normalized


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

    organization = os.environ.get("OO_NANO_BANANA_ORGANIZATION")
    personal = _env_bool("OO_NANO_BANANA_PERSONAL")
    if organization and personal:
        raise ValueError("OO_NANO_BANANA_ORGANIZATION and OO_NANO_BANANA_PERSONAL cannot both be set.")
    if organization:
        cmd.extend(["--organization", organization])
    elif personal:
        cmd.append("--personal")

    try:
        proc = subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=900)
    except FileNotFoundError as exc:
        raise RuntimeError("The `oo` CLI is required for the oo_nano_banana image provider.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"oo connector action timed out: {action}") from exc

    if proc.returncode != 0:
        raise RuntimeError(
            f"oo connector action {action} failed with exit code {proc.returncode}"
        )

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
        raise RuntimeError("oo file upload timed out") from exc

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
        _, _, encoded = value.partition(",")
        if not encoded:
            raise RuntimeError("Inline data image is missing base64 payload.")
        temporary = (
            Path(os.environ.get("TMPDIR") or "/tmp")
            / f"oo_nano_banana_ref_{time.time_ns()}{suffix}"
        )
        temporary.write_bytes(base64.b64decode(encoded))
        try:
            return _run_oo_file_upload(str(temporary))
        finally:
            temporary.unlink(missing_ok=True)
    return value


def _extract_session_id(payload: dict[str, Any]) -> str:
    session_id = (
        payload.get("sessionId")
        or payload.get("sessionID")
        or payload.get("taskId")
        or payload.get("taskID")
        or (payload.get("task") or {}).get("id")
    )
    if not isinstance(session_id, str) or not session_id.strip():
        raise RuntimeError("Nano Banana submit response missing sessionId")
    return session_id


def _poll_result(session_id: str, *, action: str, service: str) -> dict[str, Any]:
    interval = float(os.environ.get("OO_NANO_BANANA_POLL_SECONDS") or "3")
    timeout = float(os.environ.get("OO_NANO_BANANA_TIMEOUT_SECONDS") or "600")
    start = time.time()

    while True:
        payload = _run_oo_connector(action, {"sessionID": session_id}, service=service)
        state = str(payload.get("state") or "").strip().lower()
        if state in {"completed", "complete", "succeeded", "success"}:
            data = payload.get("data")
            return data if isinstance(data, dict) else payload
        if state in {"failed", "error", "canceled", "cancelled", "not_found"}:
            raise RuntimeError(f"Nano Banana task failed with state {state or 'unknown'}")
        if time.time() - start > timeout:
            raise RuntimeError(
                f"Timed out after {timeout:.0f}s waiting for Nano Banana session {session_id}"
            )
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
    images = payload.get("images")
    if isinstance(images, list):
        for image in images:
            if isinstance(image, dict):
                for key in ("base64", "b64", "image_base64", "url", "imageUrl", "imageURL"):
                    value = image.get(key)
                    if isinstance(value, str) and value.strip():
                        if key.lower() in {"base64", "b64", "image_base64"}:
                            return ("base64", value.strip())
                        return ("url", value.strip())
            elif isinstance(image, str) and image.strip():
                return ("url", image.strip())

    for value in _walk_values(payload):
        if isinstance(value, str) and value.strip():
            stripped = value.strip()
            if stripped.startswith(("http://", "https://")):
                return ("url", stripped)
    return None


class OONanoBananaImageGenProvider(ImageGenProvider):
    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def display_name(self) -> str:
        return "OOMOL Nano Banana"

    def is_available(self) -> bool:
        return shutil.which("oo") is not None

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "nano-banana-pro",
                "display": "Nano Banana Pro",
                "speed": "~30-90s",
                "strengths": "OOMOL connector, high-quality text-to-image and image editing",
                "price": "OOMOL connector billing",
            },
            {
                "id": "nano-banana-2",
                "display": "Nano Banana 2",
                "speed": "~30-90s",
                "strengths": "OOMOL connector fallback model",
                "price": "OOMOL connector billing",
            },
            {
                "id": "nano-banana",
                "display": "Nano Banana",
                "speed": "~30-90s",
                "strengths": "Legacy OOMOL connector action",
                "price": "OOMOL connector billing",
            },
        ]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "OOMOL Nano Banana",
            "badge": "oomol",
            "tag": "Uses `oo connector run fusion-api`; no FAL_KEY or OPENAI_API_KEY required.",
            "env_vars": [],
        }

    def capabilities(self) -> Dict[str, Any]:
        return {"modalities": ["text", "image"], "max_reference_images": 2}

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
        model = _resolve_model(kwargs.get("model"))
        actions = _ACTION_SETS[model]
        service = os.environ.get("OO_NANO_BANANA_SERVICE") or DEFAULT_SERVICE
        output_format = os.environ.get("OO_NANO_BANANA_OUTPUT_FORMAT") or DEFAULT_OUTPUT_FORMAT
        resolution = os.environ.get("OO_NANO_BANANA_RESOLUTION") or DEFAULT_RESOLUTION

        try:
            require_oo_authentication()
        except RuntimeError as exc:
            return error_response(
                error=str(exc),
                error_type=type(exc).__name__,
                provider=PROVIDER_NAME,
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        refs: list[str] = []
        if isinstance(image_url, str) and image_url.strip():
            refs.append(image_url.strip())
        for ref in reference_image_urls or []:
            if isinstance(ref, str) and ref.strip():
                refs.append(ref.strip())
        refs = refs[:2]

        request: dict[str, Any] = {
            "prompt": prompt,
            "aspectRatio": _ASPECT_TO_NATIVE[aspect],
            "numImages": 1,
            "outputFormat": output_format,
        }
        resolution_field = actions.get("resolution_field")
        if resolution_field:
            request[resolution_field] = resolution
        if refs:
            request[actions["image_urls_field"]] = [
                _normalize_reference(ref) for ref in refs
            ]

        try:
            submit_payload = _run_oo_connector(actions["submit"], request, service=service)
            session_id = _extract_session_id(submit_payload)
            result_payload = _poll_result(session_id, action=actions["result"], service=service)
            image_payload = _extract_image_payload(result_payload)
            if image_payload is None:
                raise RuntimeError("Nano Banana result did not contain an image")

            kind, value = image_payload
            response_extra = {"session_id": session_id}
            if kind == "base64":
                path = save_b64_image(value, prefix="oo_nano_banana", extension=output_format)
            else:
                path = save_url_image(value, prefix="oo_nano_banana", timeout=120)
                response_extra["remote_url"] = value

            return success_response(
                image=str(path),
                model=model,
                prompt=prompt,
                aspect_ratio=aspect,
                provider=PROVIDER_NAME,
                modality="image" if refs else "text",
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
    ctx.register_image_gen_provider(OONanoBananaImageGenProvider())

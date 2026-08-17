"""OOMOL/OOCI Seedance video generation backend for Hermes."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.video_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    DEFAULT_RESOLUTION,
    VideoGenProvider,
    error_response,
    save_url_video,
    success_response,
)
from agent.image_gen_provider import save_url_image
from oomol_hermes_oo import require_oo_authentication


PROVIDER_NAME = "oo_seedance"
DEFAULT_SERVICE = "fusion-api"
DEFAULT_MODEL = "doubao-seedance-2-0-260128"
FAST_MODEL = "doubao-seedance-2-0-fast-260128"
DEFAULT_DURATION = 5
DEFAULT_RETURN_LAST_FRAME = True
DEFAULT_WATERMARK = False
DEFAULT_GENERATE_AUDIO = False

_SUBMIT_ACTION = "seedance_video_submit"
_STATE_ACTION = "seedance_video_state"
_RESULT_ACTION = "seedance_video_result"

_MODELS = {DEFAULT_MODEL, FAST_MODEL}
_RATIOS = ("16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive")
_RESOLUTIONS = ("480p", "720p", "1080p")
_DELIVERY_METADATA_SUFFIX = ".delivery.json"


def _write_delivery_metadata(video_path: Path, metadata: dict[str, Any]) -> None:
    """Persist private delivery hints next to a generated video."""
    metadata_path = Path(f"{video_path}{_DELIVERY_METADATA_SUFFIX}")
    temp_path = metadata_path.with_name(
        f".{metadata_path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    try:
        temp_path.write_text(
            json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, metadata_path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def _env_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _clamp_duration(value: Any) -> int:
    if value is None or value == "":
        return DEFAULT_DURATION
    try:
        duration = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DURATION
    if duration == -1:
        return -1
    return max(4, min(15, duration))


def _resolve_model(model: Optional[str]) -> str:
    raw = (model or os.environ.get("OO_SEEDANCE_MODEL") or DEFAULT_MODEL).strip()
    if raw not in _MODELS:
        raise ValueError(f"Unsupported Seedance model '{raw}'. Supported: {', '.join(sorted(_MODELS))}")
    return raw


def _resolve_ratio(value: str) -> str:
    normalized = (value or DEFAULT_ASPECT_RATIO).strip()
    return normalized if normalized in _RATIOS else DEFAULT_ASPECT_RATIO


def _resolve_resolution(value: str) -> str:
    normalized = (value or DEFAULT_RESOLUTION).strip()
    return normalized if normalized in _RESOLUTIONS else DEFAULT_RESOLUTION


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

    organization = os.environ.get("OO_SEEDANCE_ORGANIZATION") or os.environ.get("OO_VIDEO_ORGANIZATION")
    personal = _env_bool("OO_SEEDANCE_PERSONAL")
    if personal is None:
        personal = _env_bool("OO_VIDEO_PERSONAL")
    if organization and personal:
        raise ValueError("OO_SEEDANCE_ORGANIZATION/OO_VIDEO_ORGANIZATION and personal mode cannot both be set.")
    if organization:
        cmd.extend(["--organization", organization])
    elif personal:
        cmd.append("--personal")

    try:
        proc = subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=900)
    except FileNotFoundError as exc:
        raise RuntimeError("The `oo` CLI is required for the oo_seedance video provider.") from exc
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
        raise RuntimeError("The `oo` CLI is required to upload local video reference images.") from exc
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
        tmp_path = Path(os.environ.get("TMPDIR") or "/tmp") / f"oo_seedance_ref_{int(time.time() * 1000)}{suffix}"
        tmp_path.write_bytes(base64.b64decode(b64_data))
        try:
            return _run_oo_file_upload(str(tmp_path))
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return value


def _extract_session_id(payload: dict[str, Any]) -> str:
    session_id = payload.get("sessionId") or payload.get("sessionID") or payload.get("taskId") or payload.get("taskID")
    if not isinstance(session_id, str) or not session_id.strip():
        raise RuntimeError("Seedance submit response missing sessionId")
    return session_id.strip()


def _poll_result(session_id: str, *, service: str) -> dict[str, Any]:
    interval = float(os.environ.get("OO_SEEDANCE_POLL_SECONDS") or os.environ.get("OO_VIDEO_POLL_SECONDS") or "5")
    timeout = float(os.environ.get("OO_SEEDANCE_TIMEOUT_SECONDS") or os.environ.get("OO_VIDEO_TIMEOUT_SECONDS") or "1800")
    start = time.time()

    while True:
        state_payload = _run_oo_connector(_STATE_ACTION, {"sessionID": session_id}, service=service)
        state = str(state_payload.get("state") or "").strip().lower()
        if state in {"completed", "complete", "succeeded", "success"}:
            result_payload = _run_oo_connector(_RESULT_ACTION, {"sessionID": session_id}, service=service)
            result_state = str(result_payload.get("state") or "").strip().lower()
            if result_state in {"", "completed", "complete", "succeeded", "success"}:
                return result_payload
            if result_state not in {"processing", "pending", "running", "queued"}:
                raise RuntimeError(
                    f"Seedance result failed with state {result_state or 'unknown'}"
                )
        if state in {"failed", "error", "canceled", "cancelled", "not_found"}:
            raise RuntimeError(f"Seedance task failed with state {state or 'unknown'}")

        result_payload = _run_oo_connector(_RESULT_ACTION, {"sessionID": session_id}, service=service)
        result_state = str(result_payload.get("state") or "").strip().lower()
        if result_state in {"completed", "complete", "succeeded", "success"}:
            return result_payload
        if result_state in {"failed", "error", "canceled", "cancelled", "not_found"}:
            raise RuntimeError(
                f"Seedance result failed with state {result_state or 'unknown'}"
            )

        if time.time() - start > timeout:
            raise RuntimeError(f"Timed out after {timeout:.0f}s waiting for Seedance session {session_id}")
        time.sleep(interval)


class OOSeedanceVideoGenProvider(VideoGenProvider):
    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def display_name(self) -> str:
        return "OOMOL Seedance"

    def is_available(self) -> bool:
        return shutil.which("oo") is not None

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": DEFAULT_MODEL,
                "display": "Doubao Seedance 2.0",
                "speed": "~1-5min",
                "strengths": "OOCI/Fusion API Seedance text-to-video and image-to-video",
                "price": "OOMOL connector billing",
                "modalities": ["text", "image"],
            },
            {
                "id": FAST_MODEL,
                "display": "Doubao Seedance 2.0 Fast",
                "speed": "~30s-3min",
                "strengths": "Faster OOCI/Fusion API Seedance drafts and previews",
                "price": "OOMOL connector billing",
                "modalities": ["text", "image"],
            },
        ]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "OOMOL Seedance",
            "badge": "oomol",
            "tag": "Uses `oo connector run fusion-api`; no FAL_KEY or XAI_API_KEY required.",
            "env_vars": [],
        }

    def capabilities(self) -> Dict[str, Any]:
        return {
            "modalities": ["text", "image"],
            "aspect_ratios": list(_RATIOS),
            "resolutions": list(_RESOLUTIONS),
            "max_duration": 15,
            "min_duration": 4,
            "supports_audio": True,
            "supports_negative_prompt": False,
            "max_reference_images": 9,
        }

    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        duration: Optional[int] = None,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        resolution: str = DEFAULT_RESOLUTION,
        negative_prompt: Optional[str] = None,
        audio: Optional[bool] = None,
        seed: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        del negative_prompt
        resolved_model = _resolve_model(model)
        ratio = _resolve_ratio(aspect_ratio)
        resolved_resolution = _resolve_resolution(resolution)
        resolved_duration = _clamp_duration(duration)
        service = os.environ.get("OO_SEEDANCE_SERVICE") or DEFAULT_SERVICE
        generate_audio = _coerce_bool(audio, _coerce_bool(os.environ.get("OO_SEEDANCE_GENERATE_AUDIO"), DEFAULT_GENERATE_AUDIO))
        watermark = _coerce_bool(kwargs.get("watermark"), _coerce_bool(os.environ.get("OO_SEEDANCE_WATERMARK"), DEFAULT_WATERMARK))
        return_last_frame = _coerce_bool(
            kwargs.get("return_last_frame"),
            _coerce_bool(os.environ.get("OO_SEEDANCE_RETURN_LAST_FRAME"), DEFAULT_RETURN_LAST_FRAME),
        )

        try:
            require_oo_authentication()
        except RuntimeError as exc:
            return error_response(
                error=str(exc),
                error_type=type(exc).__name__,
                provider=PROVIDER_NAME,
                model=resolved_model,
                prompt=prompt,
                aspect_ratio=ratio,
            )

        refs: list[dict[str, str]] = []
        if isinstance(image_url, str) and image_url.strip():
            refs.append({"url": _normalize_reference(image_url), "role": "first_frame"})
        for ref in reference_image_urls or []:
            if isinstance(ref, str) and ref.strip():
                refs.append({"url": _normalize_reference(ref), "role": "reference_image"})
        refs = refs[:9]

        request: dict[str, Any] = {
            "model": resolved_model,
            "prompt": prompt,
            "images": refs,
            "returnLastFrame": return_last_frame,
            "generateAudio": generate_audio,
            "resolution": resolved_resolution,
            "ratio": ratio,
            "duration": resolved_duration,
            "watermark": watermark,
        }
        if seed is not None:
            request["seed"] = int(seed)

        try:
            submit_payload = _run_oo_connector(_SUBMIT_ACTION, request, service=service)
            session_id = _extract_session_id(submit_payload)
            result_payload = _poll_result(session_id, service=service)
            data = result_payload.get("data") if isinstance(result_payload.get("data"), dict) else result_payload
            video_url = data.get("videoURL") or data.get("videoUrl") or data.get("video_url") or data.get("url")
            if not isinstance(video_url, str) or not video_url.strip():
                raise RuntimeError("Seedance result did not contain a video URL")
            video_url = video_url.strip()
            video_path = save_url_video(video_url, prefix="oo_seedance", timeout=300)

            result_duration = int(data.get("duration") or (0 if resolved_duration == -1 else resolved_duration))
            last_frame_url = data.get("lastFrameURL") or data.get("lastFrameUrl") or ""
            cover_path = ""
            if isinstance(last_frame_url, str) and last_frame_url.strip():
                try:
                    cover_path = str(
                        save_url_image(
                            last_frame_url.strip(),
                            prefix="oo_seedance_cover",
                            timeout=120,
                        )
                    )
                except Exception:
                    cover_path = ""
            try:
                _write_delivery_metadata(
                    Path(video_path),
                    {
                        "remote_url": video_url,
                        "cover_path": cover_path,
                        "duration": result_duration,
                        "aspect_ratio": str(data.get("ratio") or ratio),
                    },
                )
            except OSError:
                pass
            return success_response(
                video=str(video_path),
                model=str(data.get("model") or resolved_model),
                prompt=prompt,
                modality="image" if refs else "text",
                aspect_ratio=str(data.get("ratio") or ratio),
                duration=result_duration,
                provider=PROVIDER_NAME,
                extra={
                    "session_id": session_id,
                    "remote_url": video_url,
                    "resolution": data.get("resolution") or resolved_resolution,
                    "last_frame_url": last_frame_url,
                    "seed": data.get("seed") if data.get("seed") is not None else seed,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return error_response(
                error=str(exc),
                error_type=type(exc).__name__,
                provider=PROVIDER_NAME,
                model=resolved_model,
                prompt=prompt,
                aspect_ratio=ratio,
            )


def register(ctx) -> None:
    ctx.register_video_gen_provider(OOSeedanceVideoGenProvider())

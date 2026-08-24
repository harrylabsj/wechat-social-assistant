"""Perception connector contracts.

The relationship engine should not know whether evidence came from a visible
window capture, Accessibility, an official connector, or a user import.  This
module is the small seam for those providers.  Accessibility is intentionally
best-effort: it reads the frontmost app's exposed text tree when trusted and
lets callers fall back to Vision OCR when the tree is unavailable or empty.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from collections import Counter
from typing import Protocol, Sequence

from .observations import OCRObservation, observation_from_mapping
from .perception import annotate_accessibility_speakers


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "tools"
PACKAGED_SOURCE_ROOT = PACKAGE_ROOT / "native"
ACCESSIBILITY_SOURCE = (
    SOURCE_ROOT / "macos_accessibility_probe.swift"
    if (SOURCE_ROOT / "macos_accessibility_probe.swift").exists()
    else PACKAGED_SOURCE_ROOT / "macos_accessibility_probe.swift"
)
ACCESSIBILITY_READER_SOURCE = (
    SOURCE_ROOT / "macos_accessibility_reader.swift"
    if (SOURCE_ROOT / "macos_accessibility_reader.swift").exists()
    else PACKAGED_SOURCE_ROOT / "macos_accessibility_reader.swift"
)
SCREEN_CAPTURE_KIT_SOURCE = (
    SOURCE_ROOT / "macos_screencapturekit.swift"
    if (SOURCE_ROOT / "macos_screencapturekit.swift").exists()
    else PACKAGED_SOURCE_ROOT / "macos_screencapturekit.swift"
)
if (SOURCE_ROOT / "macos_ocr.swift").exists() and os.access(PROJECT_ROOT, os.W_OK):
    BINARY_ROOT = PROJECT_ROOT / "bin"
else:
    BINARY_ROOT = Path.home() / "Library" / "Caches" / "wechat-social-assistant" / "bin"
ACCESSIBILITY_BINARY = BINARY_ROOT / "macos_accessibility_probe"
ACCESSIBILITY_READER_BINARY = BINARY_ROOT / "macos_accessibility_reader"
SCREEN_CAPTURE_KIT_BINARY = BINARY_ROOT / "macos_screencapturekit"


@dataclass(frozen=True)
class CaptureRequest:
    output_path: Path
    mode: str = "window"
    crop: str | None = None
    crop_preset: str = "none"
    backend: str = "legacy"


@dataclass(frozen=True)
class ConnectorStatus:
    name: str
    available: bool
    detail: str
    can_capture: bool = False
    can_read_text: bool = False


@dataclass(frozen=True)
class TextCapture:
    """A text-tree capture which can be ingested without an image file."""

    text: str
    observations: tuple[OCRObservation, ...]
    source: str = "accessibility"
    app_name: str | None = None
    window_title: str | None = None
    frame_count: int = 1
    stability: float = 1.0


class CaptureConnector(Protocol):
    name: str

    def capture(self, request: CaptureRequest) -> Path:
        ...

    def status(self) -> ConnectorStatus:
        ...

    def read_text(self) -> TextCapture:
        ...


class MacOSScreenCaptureConnector:
    name = "macos-screen-capture"

    def capture(self, request: CaptureRequest) -> Path:
        from .ocr import _capture_screenshot_legacy

        return _capture_screenshot_legacy(
            request.output_path,
            mode="screen",
            crop=request.crop,
            crop_preset=request.crop_preset,
        )

    def status(self) -> ConnectorStatus:
        available = platform.system() == "Darwin" and shutil.which("screencapture") is not None
        detail = "screencapture available" if available else "requires macOS screencapture"
        return ConnectorStatus(self.name, available, detail, can_capture=available)

    def read_text(self) -> TextCapture:
        raise RuntimeError("screen capture connector does not expose a text tree")


class MacOSWindowCaptureConnector:
    name = "macos-window-capture"

    def capture(self, request: CaptureRequest) -> Path:
        if request.backend in {"auto", "screencapturekit"}:
            kit = MacOSScreenCaptureKitConnector()
            if request.backend == "screencapturekit" or kit.status().available:
                try:
                    return kit.capture(request)
                except RuntimeError:
                    if request.backend == "screencapturekit":
                        raise

        from .ocr import _capture_screenshot_legacy

        return _capture_screenshot_legacy(
            request.output_path,
            mode="window",
            crop=request.crop,
            crop_preset=request.crop_preset,
        )

    def status(self) -> ConnectorStatus:
        available = platform.system() == "Darwin" and shutil.which("screencapture") is not None
        detail = "window capture uses the frontmost window id" if available else "requires macOS screencapture"
        return ConnectorStatus(self.name, available, detail, can_capture=available)

    def read_text(self) -> TextCapture:
        raise RuntimeError("window capture connector does not expose a text tree")


class MacOSScreenCaptureKitConnector:
    """Capture the frontmost app window through ScreenCaptureKit.

    The native helper deliberately selects a concrete shareable window rather
    than recording the entire desktop.  The connector is opt-in at the API
    level and used automatically by CLI callers when the permission and
    helper are available; all failures retain the legacy fallback path.
    """

    name = "macos-screencapturekit"

    def capture(self, request: CaptureRequest) -> Path:
        if platform.system() != "Darwin":
            raise RuntimeError("ScreenCaptureKit currently supports macOS only")
        try:
            binary = ensure_screen_capture_kit()
            result = subprocess.run(
                [str(binary), str(request.output_path)],
                text=True,
                capture_output=True,
                timeout=15,
            )
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"ScreenCaptureKit unavailable: {exc}") from exc
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "ScreenCaptureKit capture failed")
        path = Path(request.output_path)
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError("ScreenCaptureKit returned no image")
        from .ocr import resolve_crop_region, crop_image

        region = resolve_crop_region(path, crop=request.crop, crop_preset=request.crop_preset)
        if region:
            crop_image(path, region)
        return path

    def status(self) -> ConnectorStatus:
        if platform.system() != "Darwin":
            return ConnectorStatus(self.name, False, "requires macOS Screen Recording", can_capture=False)
        try:
            binary = ensure_screen_capture_kit()
            result = subprocess.run([str(binary), "--status"], text=True, capture_output=True, timeout=5)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            return ConnectorStatus(self.name, False, f"ScreenCaptureKit helper unavailable: {exc}")
        trusted = result.returncode == 0 and result.stdout.strip().lower() == "trusted"
        if trusted:
            return ConnectorStatus(
                self.name,
                True,
                "Screen Recording permission granted; specified-window capture available",
                can_capture=True,
            )
        return ConnectorStatus(
            self.name,
            False,
            result.stderr.strip() or "Screen Recording permission not granted",
            can_capture=False,
        )


class MacOSAccessibilityConnector:
    """Read the frontmost app's AX text tree when Accessibility is trusted."""

    name = "macos-accessibility"

    def capture(self, request: CaptureRequest) -> Path:
        raise RuntimeError(
            "Accessibility connector returns text observations; use --mode accessibility instead of an image capture"
        )

    def read_text(self) -> TextCapture:
        if platform.system() != "Darwin":
            raise RuntimeError("Accessibility text capture currently supports macOS only")
        try:
            binary = ensure_accessibility_reader()
            result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=10)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Accessibility text reader unavailable: {exc}") from exc
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Accessibility text reader failed")
        return _parse_accessibility_output(result.stdout)

    def status(self) -> ConnectorStatus:
        if platform.system() != "Darwin":
            return ConnectorStatus(self.name, False, "requires macOS Accessibility", can_read_text=False)
        try:
            binary = ensure_accessibility_probe()
            result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=5)
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            return ConnectorStatus(self.name, False, f"Accessibility probe unavailable: {exc}")
        if result.returncode != 0:
            return ConnectorStatus(
                self.name,
                False,
                result.stderr.strip() or "Accessibility probe failed",
            )
        trusted = result.stdout.strip().lower() == "trusted"
        detail = (
            "Accessibility permission granted; AX text-tree reader available"
            if trusted
            else "Accessibility permission not granted"
        )
        return ConnectorStatus(self.name, trusted, detail, can_read_text=trusted)


def capture_connector(mode: str) -> CaptureConnector:
    if mode == "screen":
        return MacOSScreenCaptureConnector()
    if mode == "window":
        return MacOSWindowCaptureConnector()
    raise ValueError("mode must be 'screen' or 'window'")


def text_connector(mode: str = "accessibility") -> CaptureConnector:
    if mode in {"accessibility", "ax"}:
        return MacOSAccessibilityConnector()
    raise ValueError("text connector mode must be 'accessibility'")


def connector_statuses() -> tuple[ConnectorStatus, ...]:
    return (
        MacOSWindowCaptureConnector().status(),
        MacOSScreenCaptureKitConnector().status(),
        MacOSScreenCaptureConnector().status(),
        MacOSAccessibilityConnector().status(),
    )


def ensure_accessibility_probe() -> Path:
    if platform.system() != "Darwin":
        raise RuntimeError("Accessibility probe currently supports macOS only")
    if not ACCESSIBILITY_SOURCE.exists():
        raise RuntimeError(f"Accessibility probe source missing: {ACCESSIBILITY_SOURCE}")
    if _needs_build(ACCESSIBILITY_SOURCE, ACCESSIBILITY_BINARY):
        ACCESSIBILITY_BINARY.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["swiftc", str(ACCESSIBILITY_SOURCE), "-o", str(ACCESSIBILITY_BINARY)],
            text=True,
            capture_output=True,
            timeout=30,
            env=_swift_compile_env(),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "swiftc failed")
    return ACCESSIBILITY_BINARY


def ensure_accessibility_reader() -> Path:
    if platform.system() != "Darwin":
        raise RuntimeError("Accessibility text reader currently supports macOS only")
    if not ACCESSIBILITY_READER_SOURCE.exists():
        raise RuntimeError(f"Accessibility text reader source missing: {ACCESSIBILITY_READER_SOURCE}")
    if _needs_build(ACCESSIBILITY_READER_SOURCE, ACCESSIBILITY_READER_BINARY):
        ACCESSIBILITY_READER_BINARY.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["swiftc", str(ACCESSIBILITY_READER_SOURCE), "-o", str(ACCESSIBILITY_READER_BINARY)],
            text=True,
            capture_output=True,
            timeout=30,
            env=_swift_compile_env(),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "swiftc failed")
    return ACCESSIBILITY_READER_BINARY


def ensure_screen_capture_kit() -> Path:
    if platform.system() != "Darwin":
        raise RuntimeError("ScreenCaptureKit currently supports macOS only")
    if not SCREEN_CAPTURE_KIT_SOURCE.exists():
        raise RuntimeError(f"ScreenCaptureKit source missing: {SCREEN_CAPTURE_KIT_SOURCE}")
    if _needs_build(SCREEN_CAPTURE_KIT_SOURCE, SCREEN_CAPTURE_KIT_BINARY):
        SCREEN_CAPTURE_KIT_BINARY.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["swiftc", "-parse-as-library", str(SCREEN_CAPTURE_KIT_SOURCE), "-o", str(SCREEN_CAPTURE_KIT_BINARY)],
            text=True,
            capture_output=True,
            timeout=45,
            env=_swift_compile_env(),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "swiftc failed")
    return SCREEN_CAPTURE_KIT_BINARY


def _parse_accessibility_output(output: str) -> TextCapture:
    """Parse JSONL emitted by the native AX reader.

    Metadata records are deliberately kept outside the database observation
    schema.  The text and normalized bounds are mapped to the existing
    ``OCRObservation`` contract, preserving a single downstream ingestion
    path for AX and Vision evidence.
    """

    observations: list[OCRObservation] = []
    app_name: str | None = None
    window_title: str | None = None
    seen: set[tuple[str, tuple[float | None, ...] | None]] = set()
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Accessibility text reader returned invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            continue
        if payload.get("kind") == "meta":
            app_name = _optional_text(payload.get("app_name"))
            window_title = _optional_text(payload.get("window_title"))
            continue
        if payload.get("kind") not in {None, "text"}:
            continue
        text = _optional_text(payload.get("text"))
        if not text:
            continue
        observation = observation_from_mapping(payload, source="accessibility")
        # Only collapse duplicate container/leaf values when AX supplied a
        # spatial bound.  Without bounds, two identical messages are valid
        # separate observations and must not be silently dropped.
        key = (observation.text, observation.bbox)
        if observation.bbox is not None:
            if key in seen:
                continue
            seen.add(key)
        observations.append(observation)
    normalized = tuple(
        OCRObservation(**{**observation.__dict__, "sequence": index})
        for index, observation in enumerate(observations)
    )
    normalized = annotate_accessibility_speakers(normalized)
    return TextCapture(
        text="\n".join(observation.text for observation in normalized),
        observations=normalized,
        app_name=app_name,
        window_title=window_title,
    )


def merge_text_captures(
    captures: Sequence[TextCapture],
    *,
    min_stable_frames: int = 2,
) -> TextCapture:
    """Keep observations that recur across a short AX capture window.

    Bounds are rounded before matching so harmless sub-pixel layout movement
    does not create a new message.  Duplicate unbounded messages are tracked
    by occurrence within each frame, preserving two identical visible lines.
    If no observation reaches the threshold, the latest frame is returned with
    ``stability=0`` so the caller can apply its normal empty/fallback policy.
    """

    if not captures:
        raise ValueError("at least one text capture is required")
    if len(captures) == 1:
        capture = captures[0]
        return TextCapture(
            text=capture.text,
            observations=capture.observations,
            source=capture.source,
            app_name=capture.app_name,
            window_title=capture.window_title,
            frame_count=max(1, capture.frame_count),
            stability=capture.stability,
        )

    threshold = min(max(1, int(min_stable_frames)), len(captures))
    frame_keys = [_frame_keys(capture.observations) for capture in captures]
    counts: Counter[tuple[tuple[object, ...], int]] = Counter()
    for keys in frame_keys:
        counts.update(set(keys))
    stable_keys = {key for key, count in counts.items() if count >= threshold}

    latest_index: dict[tuple[tuple[object, ...], int], int] = {}
    latest_observation: dict[tuple[tuple[object, ...], int], OCRObservation] = {}
    for frame_index, (capture, keys) in enumerate(zip(captures, frame_keys)):
        for key, observation in zip(keys, capture.observations):
            if key not in stable_keys:
                continue
            latest_index[key] = frame_index
            latest_observation[key] = observation

    if not stable_keys:
        selected = captures[-1]
        return TextCapture(
            text=selected.text,
            observations=selected.observations,
            source=selected.source,
            app_name=selected.app_name,
            window_title=selected.window_title,
            frame_count=sum(max(1, capture.frame_count) for capture in captures),
            stability=0.0,
        )

    # Prefer the latest frame's visual order, then append a stable node which
    # briefly disappeared from that frame in its most recent known position.
    ordered_keys: list[tuple[tuple[object, ...], int]] = []
    for key in frame_keys[-1]:
        if key in stable_keys and key not in ordered_keys:
            ordered_keys.append(key)
    missing_keys = [key for key in stable_keys if key not in ordered_keys]
    missing_keys.sort(key=lambda key: (latest_index[key], latest_observation[key].sequence or 0))
    ordered_keys.extend(missing_keys)

    # If a speaker candidate appeared in an earlier stable frame but not the
    # latest one, retain it as evidence rather than dropping the attribution.
    merged: list[OCRObservation] = []
    for key in ordered_keys:
        observation = latest_observation[key]
        if not observation.speaker_candidate:
            for capture, keys in reversed(list(zip(captures, frame_keys))):
                if key not in keys:
                    continue
                earlier = capture.observations[keys.index(key)]
                if earlier.speaker_candidate:
                    observation = OCRObservation(
                        **{
                            **observation.__dict__,
                            "speaker_candidate": earlier.speaker_candidate,
                            "speaker_confidence": earlier.speaker_confidence,
                        }
                    )
                    break
        merged.append(observation)
    normalized = tuple(
        OCRObservation(**{**observation.__dict__, "sequence": index})
        for index, observation in enumerate(merged)
    )
    latest = captures[-1]
    total_keys = len(set(key for keys in frame_keys for key in keys))
    stability = len(stable_keys) / total_keys if total_keys else 0.0
    return TextCapture(
        text="\n".join(observation.text for observation in normalized),
        observations=normalized,
        source=latest.source,
        app_name=latest.app_name or next((capture.app_name for capture in reversed(captures) if capture.app_name), None),
        window_title=latest.window_title or next(
            (capture.window_title for capture in reversed(captures) if capture.window_title), None
        ),
        frame_count=sum(max(1, capture.frame_count) for capture in captures),
        stability=stability,
    )


def _frame_keys(observations: Sequence[OCRObservation]) -> list[tuple[tuple[object, ...], int]]:
    occurrences: Counter[tuple[object, ...]] = Counter()
    keys: list[tuple[tuple[object, ...], int]] = []
    for observation in observations:
        base = (
            " ".join(observation.text.split()).casefold(),
            tuple(round(value, 2) for value in observation.bbox) if observation.bbox is not None else None,
        )
        occurrence = occurrences[base]
        occurrences[base] += 1
        keys.append((base, occurrence))
    return keys


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _swift_compile_env() -> dict[str, str]:
    """Keep Swift's module cache inside the connector cache directory.

    Sandboxed hosts may make ``~/.cache/clang`` read-only.  A project/user
    cache is both writable and naturally scoped to WSA's compiled helpers.
    """

    env = os.environ.copy()
    env.setdefault("CLANG_MODULE_CACHE_PATH", str(BINARY_ROOT / "clang-module-cache"))
    return env


def _needs_build(source: Path, binary: Path) -> bool:
    try:
        return not binary.exists() or binary.stat().st_mtime < source.stat().st_mtime
    except OSError:
        return True

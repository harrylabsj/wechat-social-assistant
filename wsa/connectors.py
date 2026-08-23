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
from typing import Protocol

from .observations import OCRObservation, observation_from_mapping


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
if (SOURCE_ROOT / "macos_ocr.swift").exists() and os.access(PROJECT_ROOT, os.W_OK):
    BINARY_ROOT = PROJECT_ROOT / "bin"
else:
    BINARY_ROOT = Path.home() / "Library" / "Caches" / "wechat-social-assistant" / "bin"
ACCESSIBILITY_BINARY = BINARY_ROOT / "macos_accessibility_probe"
ACCESSIBILITY_READER_BINARY = BINARY_ROOT / "macos_accessibility_reader"


@dataclass(frozen=True)
class CaptureRequest:
    output_path: Path
    mode: str = "window"
    crop: str | None = None
    crop_preset: str = "none"


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
    return TextCapture(
        text="\n".join(observation.text for observation in normalized),
        observations=normalized,
        app_name=app_name,
        window_title=window_title,
    )


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

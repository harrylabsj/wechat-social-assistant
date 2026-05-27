from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import platform
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OCR_SOURCE = PROJECT_ROOT / "tools" / "macos_ocr.swift"
OCR_BINARY = PROJECT_ROOT / "bin" / "macos_ocr"
FRONTMOST_SOURCE = PROJECT_ROOT / "tools" / "macos_frontmost_app.swift"
FRONTMOST_BINARY = PROJECT_ROOT / "bin" / "macos_frontmost_app"


class CaptureError(RuntimeError):
    pass


@dataclass(frozen=True)
class FrontmostAppStatus:
    name: str | None
    method: str
    detail: str


@dataclass(frozen=True)
class CropRegion:
    x: int
    y: int
    width: int
    height: int


def capture_screenshot(
    output_path: Path | str,
    *,
    mode: str = "screen",
    crop: str | None = None,
    crop_preset: str = "none",
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    args = ["screencapture", "-x", "-o"]
    if mode == "window":
        args.append("-W")
    elif mode != "screen":
        raise ValueError("mode must be 'screen' or 'window'")
    args.append(str(path))
    result = subprocess.run(args, text=True, capture_output=True)
    if result.returncode != 0:
        raise CaptureError(result.stderr.strip() or "screencapture failed")
    region = resolve_crop_region(path, crop=crop, crop_preset=crop_preset)
    if region:
        crop_image(path, region)
    return path


def ocr_image(image_path: Path | str, *, build: bool = True) -> str:
    if platform.system() != "Darwin":
        raise CaptureError("OCR helper currently supports macOS only.")
    binary = ensure_ocr_helper() if build else OCR_BINARY
    if not binary.exists():
        raise CaptureError("OCR helper is not built. Run: swiftc tools/macos_ocr.swift -o bin/macos_ocr")
    result = subprocess.run(
        [str(binary), str(image_path)],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise CaptureError(result.stderr.strip() or "OCR failed")
    return result.stdout.strip()


def ensure_ocr_helper() -> Path:
    if _needs_build(OCR_SOURCE, OCR_BINARY):
        OCR_BINARY.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["swiftc", str(OCR_SOURCE), "-o", str(OCR_BINARY)],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise CaptureError(result.stderr.strip() or "swiftc failed")
    return OCR_BINARY


def ensure_frontmost_helper() -> Path:
    if _needs_build(FRONTMOST_SOURCE, FRONTMOST_BINARY):
        FRONTMOST_BINARY.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["swiftc", str(FRONTMOST_SOURCE), "-o", str(FRONTMOST_BINARY)],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise CaptureError(result.stderr.strip() or "swiftc failed")
    return FRONTMOST_BINARY


def next_capture_path(root: Path | str) -> Path:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    return Path(root) / "captures" / f"wechat-{timestamp}.png"


def parse_crop_spec(spec: str) -> CropRegion:
    parts = [part.strip() for part in spec.split(",")]
    if len(parts) != 4:
        raise ValueError("crop must be x,y,width,height")
    try:
        x, y, width, height = (int(part) for part in parts)
    except ValueError as exc:
        raise ValueError("crop values must be integers") from exc
    region = CropRegion(x=x, y=y, width=width, height=height)
    _validate_positive_region(region)
    return region


def image_size(image_path: Path | str) -> tuple[int, int]:
    result = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(image_path)],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise CaptureError(result.stderr.strip() or "failed to inspect image size")
    width = height = None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("pixelWidth:"):
            width = int(stripped.split(":", 1)[1].strip())
        elif stripped.startswith("pixelHeight:"):
            height = int(stripped.split(":", 1)[1].strip())
    if width is None or height is None:
        raise CaptureError("failed to parse image size")
    return width, height


def resolve_crop_region(
    image_path: Path | str,
    *,
    crop: str | None = None,
    crop_preset: str = "none",
) -> CropRegion | None:
    if crop:
        region = parse_crop_spec(crop)
    elif crop_preset == "none":
        return None
    elif crop_preset == "wechat-chat":
        width, height = image_size(image_path)
        region = CropRegion(
            x=round(width * 0.1786),
            y=round(height * 0.0356),
            width=round(width * 0.8135),
            height=round(height * 0.9012),
        )
    else:
        raise ValueError(f"unknown crop preset: {crop_preset}")
    _validate_region_inside_image(region, image_size(image_path))
    return region


def crop_image(image_path: Path | str, region: CropRegion) -> None:
    path = Path(image_path)
    temp_path = path.with_name(f"{path.stem}.crop{path.suffix}")
    result = subprocess.run(
        [
            "sips",
            "-c",
            str(region.height),
            str(region.width),
            "--cropOffset",
            str(region.y),
            str(region.x),
            str(path),
            "--out",
            str(temp_path),
        ],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise CaptureError(result.stderr.strip() or "failed to crop image")
    temp_path.replace(path)


def frontmost_app_name() -> str | None:
    return frontmost_app_status().name


def frontmost_app_status() -> FrontmostAppStatus:
    swift_status = _frontmost_app_from_swift()
    if swift_status.name:
        return swift_status
    fallback_status = _frontmost_app_from_osascript()
    if fallback_status.name:
        return fallback_status
    return FrontmostAppStatus(
        name=None,
        method=f"{swift_status.method}+{fallback_status.method}",
        detail=f"{swift_status.detail}; {fallback_status.detail}",
    )


def _frontmost_app_from_swift() -> FrontmostAppStatus:
    if platform.system() != "Darwin":
        return FrontmostAppStatus(name=None, method="swift", detail="not macOS")
    try:
        binary = ensure_frontmost_helper()
    except Exception as exc:
        return FrontmostAppStatus(name=None, method="swift", detail=str(exc))
    result = subprocess.run([str(binary)], text=True, capture_output=True)
    if result.returncode == 0:
        name = result.stdout.strip()
        if name:
            return FrontmostAppStatus(name=name, method="swift", detail="ok")
    detail = result.stderr.strip() or result.stdout.strip() or "frontmost helper failed"
    return FrontmostAppStatus(name=None, method="swift", detail=detail)


def _frontmost_app_from_osascript() -> FrontmostAppStatus:
    script = 'tell application "System Events" to get name of first application process whose frontmost is true'
    try:
        result = subprocess.run(["osascript", "-e", script], text=True, capture_output=True)
    except OSError as exc:
        return FrontmostAppStatus(name=None, method="osascript", detail=f"osascript unavailable: {exc}")
    if result.returncode == 0:
        name = result.stdout.strip()
        if name:
            return FrontmostAppStatus(name=name, method="osascript", detail="ok")
    detail = result.stderr.strip() or result.stdout.strip() or "osascript failed"
    return FrontmostAppStatus(name=None, method="osascript", detail=detail)


def _validate_positive_region(region: CropRegion) -> None:
    if region.x < 0 or region.y < 0 or region.width <= 0 or region.height <= 0:
        raise ValueError("crop values must describe a positive region")


def _validate_region_inside_image(region: CropRegion, size: tuple[int, int]) -> None:
    _validate_positive_region(region)
    image_width, image_height = size
    if region.x + region.width > image_width or region.y + region.height > image_height:
        raise ValueError("crop region is outside the image bounds")


def _needs_build(source: Path, binary: Path) -> bool:
    if not binary.exists():
        return True
    return source.stat().st_mtime > binary.stat().st_mtime

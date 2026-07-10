import base64
import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import cv2

from src import config


def resolve_asset_path(filepath: str, base_dir: Path | None = None) -> Path:
    """Resolve `filepath` under `base_dir`, rejecting traversal.

    `base_dir` defaults to `config.ASSETS_DIR`, read at call time (not bound
    as a default argument value) so callers that monkeypatch `config.ASSETS_DIR`
    (e.g. tests) keep working. Passing an explicit `base_dir` lets this same
    validated resolution logic be reused against other roots, e.g. a zip
    import's extraction directory.

    `filepath` must be a relative path referencing a file *within* `base_dir`.
    Defense-in-depth checks, each raising `ValueError`:

    - empty `filepath`, or one containing a NUL byte;
    - absolute paths (either `Path.is_absolute()` or a leading `/`);
    - any path with a `..` component;
    - a path that resolves to `base_dir` itself (must be a file within it,
      not the root).

    The final `is_relative_to` guard on the resolved path is the real
    backstop: because `.resolve()` follows symlinks, it also catches escapes
    via symlinked components.
    """
    if not filepath or "\x00" in filepath:
        raise ValueError(f"Invalid filepath: {filepath!r}")
    if Path(filepath).is_absolute() or filepath.startswith("/"):
        raise ValueError(f"Absolute filepath not allowed: {filepath!r}")
    if ".." in PurePosixPath(filepath).parts:
        raise ValueError(f"Path traversal not allowed: {filepath!r}")

    root = (base_dir if base_dir is not None else Path(config.ASSETS_DIR)).resolve()
    resolved = (root / filepath).resolve()
    if resolved == root:
        raise ValueError(f"Filepath must reference a file: {filepath!r}")
    if not resolved.is_relative_to(root):
        raise ValueError(f"Path escapes base directory: {filepath!r}")
    return resolved


def extract_zip_safely(zip_path: Path, dest_dir: Path) -> None:
    """Extract `zip_path` into `dest_dir`, rejecting zip-slip entries.

    Reuses `resolve_asset_path`'s traversal/absolute-path/symlink-escape
    defenses against `dest_dir` instead of `ASSETS_DIR`. Raises `ValueError`
    if the zip is malformed or any entry's path is unsafe - callers own
    translating that into their own domain-specific error type.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"not a valid zip file: {exc}") from exc
    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            try:
                target = resolve_asset_path(info.filename, base_dir=dest_dir)
            except ValueError as exc:
                raise ValueError(f"unsafe path in zip: {info.filename!r} ({exc})") from exc
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def write_base64_image(dest: Path, b64: str) -> None:
    """Decode a base64 image and write its bytes to `dest`."""
    data = base64.b64decode(b64)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)


def write_temp_image(b64: str) -> Path:
    """Decode a base64 image and write it to a fresh temp file in `ASSETS_DIR`.

    The temp file lives inside `config.ASSETS_DIR` (in a `.tmp` subdir) so it is
    on the same filesystem as final asset destinations, enabling atomic
    `os.replace` when the image is switched in. Raises `ValueError` on invalid
    base64. The caller owns cleanup of the returned path.
    """
    data = base64.b64decode(b64, validate=True)
    tmp_dir = Path(config.ASSETS_DIR) / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=str(tmp_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except Exception:
        Path(name).unlink(missing_ok=True)
        raise
    return Path(name)


def stage_source_file(src: Path) -> Path:
    """Copy `src`'s bytes into a fresh temp file in `ASSETS_DIR/.tmp`.

    Mirrors `write_temp_image`, but the source is an already-extracted file on
    disk rather than base64 text. The temp file lives inside `ASSETS_DIR` so it
    is on the same filesystem as final asset destinations, enabling atomic
    `os.replace` when it's moved into place. Caller owns cleanup of the
    returned path.
    """
    tmp_dir = Path(config.ASSETS_DIR) / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=str(tmp_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
            shutil.copyfileobj(inp, out)
    except Exception:
        Path(name).unlink(missing_ok=True)
        raise
    return Path(name)


def move_asset(src: Path, dest: Path) -> None:
    """Move `src` to `dest`, creating `dest.parent` and overwriting `dest`.

    Uses `os.replace`, which is atomic on the same filesystem. No-op if
    `src == dest`.
    """
    if src == dest:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.replace(src, dest)


def read_image_dimensions(path: Path) -> tuple[int, int]:
    """Return `(size_x, size_y)` = `(width, height)` of the image at `path`.

    `cv2.imread` yields an array shaped `(height, width, channels)`. Raises
    `ValueError` if the image cannot be decoded.
    """
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Could not decode image: {path}")
    height = image.shape[0]
    width = image.shape[1]
    return (width, height)


_SIGNATURE_TO_EXT: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
    (b"II*\x00", "tiff"),
    (b"MM\x00*", "tiff"),
]


def detect_image_extension(path: Path) -> str:
    """Return a canonical lowercase extension (no dot), derived from the file's
    magic-byte signature - never from a caller-supplied filename. Raises
    `ValueError` if the signature isn't one of the known image formats.

    This is header inspection, not decoding, so it doesn't need an imaging
    library; `read_image_dimensions` (cv2-based) remains the decodability
    check for callers that also need one.
    """
    with path.open("rb") as fh:
        header = fh.read(12)
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    for signature, ext in _SIGNATURE_TO_EXT:
        if header.startswith(signature):
            return ext
    raise ValueError(f"Unrecognized image signature: {header!r}")

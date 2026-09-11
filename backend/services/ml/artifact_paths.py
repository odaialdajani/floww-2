"""Resolve Git's relative-link text on Windows without copying model binaries."""
from pathlib import Path


def resolve_artifact_path(value):
    path = Path(value).absolute()
    directory = path.parent.resolve()
    seen = set()
    for _ in range(8):
        if path in seen:
            raise ValueError("Model artifact link cycle")
        seen.add(path)
        if path.is_symlink() or path.stat().st_size > 1024:
            return path
        try:
            text = path.read_text(encoding="utf-8").strip()
        except UnicodeError:
            return path
        if not text.endswith(".joblib") or any(c in text for c in ("\n", "\r", "\0")):
            return path
        target = Path(text)
        if target.is_absolute() or target.drive:
            raise ValueError("Model artifact link leaves its directory")
        target = (path.parent / target).resolve()
        if not target.is_relative_to(directory):
            raise ValueError("Model artifact link leaves its directory")
        path = target
    raise ValueError("Model artifact link cycle or excessive depth")

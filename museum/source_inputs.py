"""Resolve source assets supplied to the offline catalog builders."""
import os
from pathlib import Path


def required_source(variable: str, *, directory: bool = False) -> Path:
    value = os.environ.get(variable)
    if not value:
        raise ValueError(f"Set {variable} to the source asset path")
    path = Path(value).expanduser().resolve()
    if not (path.is_dir() if directory else path.is_file()):
        raise FileNotFoundError(f"{variable}: {path}")
    return path

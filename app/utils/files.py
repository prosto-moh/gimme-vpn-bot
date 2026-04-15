from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import fcntl
import json
import os
import tempfile


class FileStateError(RuntimeError):
    pass


@contextmanager
def exclusive_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def read_text_checked(path: Path) -> str:
    if not path.exists():
        raise FileStateError(f"File does not exist: {path}")
    return path.read_text(encoding="utf-8")


def read_json_array(path: Path) -> list[dict]:
    raw = read_text_checked(path)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FileStateError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, list):
        raise FileStateError(f"{path} must contain a JSON array.")
    if not all(isinstance(item, dict) for item in data):
        raise FileStateError(f"{path} must contain an array of JSON objects.")
    return data


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as temp_file:
        temp_file.write(content)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_name = temp_file.name
    os.replace(temp_name, path)


def atomic_write_json(path: Path, payload: list[dict]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


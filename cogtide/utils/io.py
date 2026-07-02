"""UTF-8 disciplined file I/O helpers.

All file reads/writes in this project go through these helpers so the
cross-platform UTF-8 invariant from the spec section 4 is enforced in one
place.

On Windows, Google Drive (and similar cloud-sync filesystems) can
trigger transient errors like WinError 433 ("a device which does not
exist was specified") when the sync engine momentarily makes a
directory or file unavailable. The write helpers retry up to 3 times
with a short sleep to ride through these transient failures.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

# Retry budget for transient filesystem errors on Windows (Google Drive,
# OneDrive, etc.). On Linux/macOS this almost never fires.
_WRITE_RETRIES = 3
_WRITE_RETRY_WAIT = 0.5  # seconds between retries


def _mkdir_with_retry(p: Path) -> None:
    """Create parent directories, retrying on transient Windows errors."""
    for attempt in range(1, _WRITE_RETRIES + 1):
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            return
        except OSError as e:
            if attempt == _WRITE_RETRIES:
                raise
            print(
                f"  [io] mkdir retry {attempt}/{_WRITE_RETRIES} for "
                f"{p.parent}: {e}",
                file=sys.stderr,
            )
            time.sleep(_WRITE_RETRY_WAIT)


def read_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_text(path: Path | str, content: str) -> Path:
    p = Path(path)
    for attempt in range(1, _WRITE_RETRIES + 1):
        try:
            _mkdir_with_retry(p)
            p.write_text(content, encoding="utf-8")
            return p
        except OSError as e:
            if attempt == _WRITE_RETRIES:
                raise
            print(
                f"  [io] write retry {attempt}/{_WRITE_RETRIES} for "
                f"{p}: {e}",
                file=sys.stderr,
            )
            time.sleep(_WRITE_RETRY_WAIT)
    return p  # unreachable, but keeps mypy happy


def read_json(path: Path | str) -> Any:
    return json.loads(read_text(path))


def write_json(path: Path | str, data: Any) -> Path:
    return write_text(path, json.dumps(data, indent=2, ensure_ascii=False))


def append_json_lines(path: Path | str, item: Any) -> Path:
    p = Path(path)
    for attempt in range(1, _WRITE_RETRIES + 1):
        try:
            _mkdir_with_retry(p)
            with open(p, "a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
            return p
        except OSError as e:
            if attempt == _WRITE_RETRIES:
                raise
            print(
                f"  [io] append retry {attempt}/{_WRITE_RETRIES} for "
                f"{p}: {e}",
                file=sys.stderr,
            )
            time.sleep(_WRITE_RETRY_WAIT)
    return p  # unreachable

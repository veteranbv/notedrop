"""Small POSIX file operations shared by the mailbox and local receipts."""

import json
import os
import secrets
import stat
from contextlib import contextmanager
from pathlib import Path


class Error(Exception):
    """An actionable operational or protocol error."""


def component(name: str) -> str:
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        raise Error(f"Invalid path component: {name!r}")
    return name


@contextmanager
def directory(root: Path, *parts: str, create: bool = False):
    """Walk beneath an explicitly configured root without following symlinks."""
    if create:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open(root, flags)
    try:
        for part in parts:
            component(part)
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def read_bytes(fd: int, name: str, limit: int) -> bytes:
    handle = os.open(component(name), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(handle, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise Error(f"Not a regular file: {name!r}")
        if info.st_size > limit:
            raise Error(f"File exceeds {limit} bytes: {name!r}")
        content = stream.read(limit + 1)
        if len(content) > limit:
            raise Error(f"File exceeds {limit} bytes: {name!r}")
        return content


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Error(f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise Error(f"Invalid JSON constant: {value}")


def read_json(fd: int, name: str, limit: int = 512 * 1024):
    try:
        return json.loads(
            read_bytes(fd, name, limit).decode("utf-8"),
            object_pairs_hook=_unique_keys,
            parse_constant=_invalid_constant,
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise Error(f"Invalid UTF-8 JSON in {name!r}: {exc}") from exc


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def publish(fd: int, name: str, content: bytes) -> None:
    """Flush a private file, then atomically add its final name without replacing."""
    component(name)
    temp = f".{secrets.token_hex(16)}.tmp"
    handle = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    published = False
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        published = True
        os.fsync(fd)
    except FileExistsError:
        raise
    except OSError as exc:
        if published:
            raise Error(
                f"Published {name!r}, but durability confirmation failed; "
                f"inspect it before retrying: {exc}"
            ) from exc
        raise Error(
            f"Could not safely publish {name!r}; this filesystem must "
            f"support hard links and fsync: {exc}"
        ) from exc
    finally:
        try:
            os.unlink(temp, dir_fd=fd)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise Error(
                f"Temporary file cleanup failed for {name!r}; "
                f"published={published}. Inspect before retrying: {exc}"
            ) from exc

"""Bounded descriptor reads; never follow symlinks or consume special files."""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import stat

from ..schema import ContractError

LIMIT = 131072


def open_directory(path: Path) -> int:
    if '..' in path.parts:
        raise ContractError('parent traversal')
    path = Path(os.path.abspath(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_regular(path: Path, maximum: int = LIMIT) -> tuple[bytes, int]:
    fd = open_directory(path.parent)
    try:
        item = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=fd)
        try:
            metadata = os.fstat(item)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
                raise ContractError('not a bounded regular file')
            chunks = []
            remaining = maximum + 1
            while remaining:
                chunk = os.read(item, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b''.join(chunks)
            if len(raw) > maximum:
                raise ContractError('file exceeds limit')
            return raw, stat.S_IMODE(metadata.st_mode)
        finally:
            os.close(item)
    finally:
        os.close(fd)


def finite_tree(path: Path) -> set[str]:
    """Read names only, at most128 entries, with retained no-follow directory descriptors."""
    queue = [(open_directory(path), '')]
    result = set()
    seen = 0
    try:
        while queue:
            fd, prefix = queue.pop()
            try:
                with os.scandir(fd) as entries:
                    for entry in entries:
                        seen += 1
                        if seen > 128:
                            raise ContractError('bundle inventory exceeds finite limit')
                        name = prefix + entry.name
                        metadata = entry.stat(follow_symlinks=False)
                        if stat.S_ISDIR(metadata.st_mode):
                            queue.append((os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd), name + '/'))
                        elif stat.S_ISREG(metadata.st_mode):
                            result.add(str(PurePosixPath(name)))
                        else:
                            raise ContractError('nonregular or symlink artifact')
            finally:
                os.close(fd)
        return result
    finally:
        for fd, _ in queue:
            os.close(fd)

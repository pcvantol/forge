"""Finite private proposal bytes, using the qualified no-follow directory walk."""
import json
import os
from pathlib import Path
import secrets
import stat
from .project_bootstrap.assets.safe_io import open_directory
from .project_bootstrap.schema import canonical, load_json

MAX_STORE = 16 * 1024 * 1024


def directory(path):
    fd = open_directory(path)
    info = os.fstat(fd)
    if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.geteuid():
        os.close(fd)
        raise ValueError('private owned proposal directory required')
    return fd


def read(path, limit=MAX_STORE):
    path = Path(path); parent = directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.geteuid() or info.st_size > limit:
                raise ValueError('private bounded proposal file required')
            raw = stream.read(limit + 1)
            if len(raw) > limit: raise ValueError('proposal capacity exceeded')
            return load_json(raw)
    finally: os.close(parent)


def write(path, value, *, create=False):
    raw = canonical(value)
    if len(raw) > MAX_STORE: raise ValueError('proposal storage capacity exceeded')
    path = Path(path); parent = directory(path.parent); temporary = '.proposal-' + secrets.token_hex(16)
    try:
        try:
            info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            if not create: raise
        else:
            if create or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.geteuid():
                raise ValueError('proposal destination unavailable')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        current = directory(path.parent)
        try:
            if (os.fstat(current).st_dev, os.fstat(current).st_ino) != (os.fstat(parent).st_dev, os.fstat(parent).st_ino):
                raise ValueError('proposal directory changed')
        finally: os.close(current)
        if create:
            os.link(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        else:
            os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        try: os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError: pass
        os.close(parent)

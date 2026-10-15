"""Owned finite subprocess capture with primary/secondary outcome separation."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import threading

MAXIMUM_LOG = 65536
COMMAND_TIMEOUT = 30


def retain(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(raw)


def capture(args: list[str], *, case: str, output: Path, cwd: Path, env: dict[str, str], expected: int = 0, timeout: float | None = None) -> tuple[dict, bytes, bytes]:
    process = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, start_new_session=True)
    buffers = [bytearray(), bytearray()]
    truncated = [False, False]
    read_errors = []
    def drain(pipe, index):
        try:
            while True:
                raw = pipe.read(4096)
                if not raw:
                    break
                available = MAXIMUM_LOG - len(buffers[index])
                buffers[index].extend(raw[:available])
                if len(raw) > available:
                    truncated[index] = True
        except OSError as error:
            read_errors.append(type(error).__name__)
        finally:
            pipe.close()
    workers = [threading.Thread(target=drain,args=(process.stdout,0)),
               threading.Thread(target=drain,args=(process.stderr,1))]
    for worker in workers:
        worker.start()
    primary = None
    try:
        try:
            process.wait(timeout=COMMAND_TIMEOUT if timeout is None else min(COMMAND_TIMEOUT, timeout))
        except subprocess.TimeoutExpired:
            primary = {'category':'COMMAND_TIMEOUT','observed_exit':None}
            try:
                os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        if primary is None and process.returncode != expected:
            primary = {'category':'COMMAND_NONZERO' if process.returncode else 'UNEXPECTED_SUCCESS',
                       'observed_exit':process.returncode}
    finally:
        # The process group is ours even when its session leader has already exited.
        # Stop inherited-pipe descendants before joining readers; leader-only wait is insufficient.
        try:
            os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:
            pass
        if process.poll() is None:
            process.wait(timeout=5)
        for worker in workers:
            worker.join(timeout=5)
    report = {'case':case,'expected_exit':expected,'actual_exit':process.returncode,
              'primary_failure':primary,'secondary_failures':[],
              'capture_complete':not any(truncated) and not read_errors and not any(w.is_alive() for w in workers),
              'owned_process_waited':process.poll() is not None,
              'owned_process_group_stop_requested':True,
              'reader_threads_joined':not any(w.is_alive() for w in workers),
              'log_bytes':[len(b) for b in buffers],'truncated':any(truncated)}
    if read_errors:
        report['secondary_failures'].append({'stage':'capture','category':'READ_ERROR'})
    for index, raw in enumerate(buffers):
        try:
            retain(output / f'private-{case}-{index}.log',bytes(raw))
        except OSError as error:
            report['secondary_failures'].append({'stage':'private-retention','category':type(error).__name__})
            report['capture_complete']=False
    return report,bytes(buffers[0]),bytes(buffers[1])

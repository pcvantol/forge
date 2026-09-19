"""One foreground controller for one canonically admitted Mission."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import signal
from threading import Event
import time
from typing import Iterator
from uuid import uuid4

from forge.runtime.dynamic_mission import InstalledDynamicMissionRuntime
from forge.runtime.service import RuntimeServiceBusy
from forge.state import MissionExecutionStatus

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]


_RUNNING = frozenset({
    MissionExecutionStatus.CREATED, MissionExecutionStatus.READY,
    MissionExecutionStatus.ACTIVE, MissionExecutionStatus.WAITING_FOR_EXECUTION,
    MissionExecutionStatus.WAITING_FOR_EVIDENCE, MissionExecutionStatus.READY_TO_CONTINUE,
})
_STOPPED = frozenset({
    MissionExecutionStatus.BLOCKED, MissionExecutionStatus.FAILED,
    MissionExecutionStatus.COMPLETED, MissionExecutionStatus.ARCHIVED,
})


def _write(path: Path, document: dict[str, object]) -> None:
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class MissionController:
    """Keep the product process alive until its selected Mission stops.

    The long lease excludes a second controller while each runtime tick still
    takes the existing short mutation lease. No nested mutation lock is taken.
    A stop request is advisory to this process and never rewrites EP status.
    """

    def __init__(self, runtime: InstalledDynamicMissionRuntime, mission_id: str,
                 *, poll_seconds: float = 1.0, maximum_wait_seconds: float = 3600.0):
        if (not mission_id or not math.isfinite(poll_seconds) or poll_seconds <= 0
                or not math.isfinite(maximum_wait_seconds) or maximum_wait_seconds <= 0):
            raise ValueError("controller requires a selected Mission and positive wait bounds")
        self.runtime, self.mission_id = runtime, mission_id
        self.poll_seconds, self.maximum_wait_seconds = poll_seconds, maximum_wait_seconds
        self._stop = Event()
        root = Path(runtime.database.path).parent
        self._lease = root / "forge-mission-controller.lock"
        self._control = root / "forge-mission-controller.json"
        self._request = root / "forge-mission-stop.json"

    @contextmanager
    def _acquire(self) -> Iterator[str]:
        if fcntl is None:
            raise RuntimeServiceBusy("foreground controller locking is unavailable")
        token = uuid4().hex
        with self._lease.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeServiceBusy("another foreground Mission controller is active") from error
            self._request.unlink(missing_ok=True)
            _write(self._control, {"mission_id": self.mission_id, "token": token, "pid": os.getpid()})
            try:
                yield token
            finally:
                self._control.unlink(missing_ok=True)
                self._request.unlink(missing_ok=True)
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _requested(self, token: str) -> bool:
        try:
            request = json.loads(self._request.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError, OSError):
            return False
        return request == {"mission_id": self.mission_id, "token": token, "stop": True}

    def run(self, *, initial_truth=None) -> dict[str, object]:
        with self._acquire() as token:
            operators = self.runtime.repository.operators
            operator_context = operators.context()
            def authorized() -> bool:
                return operators.authorize(operator_context)
            self.runtime._keep_running = lambda: (not self._stop.is_set() and not self._requested(token)
                                                  and authorized())
            previous_int = signal.getsignal(signal.SIGINT)
            previous_term = signal.getsignal(signal.SIGTERM)
            signal.signal(signal.SIGINT, lambda *_: self._stop.set())
            signal.signal(signal.SIGTERM, lambda *_: self._stop.set())
            try:
                state = self.runtime.states.get(self.mission_id)
                if not self.runtime._keep_running():
                    return self._report(self.runtime._result(state),
                                        "authority_revoked" if not authorized() else "operator_stop")
                if state.status is MissionExecutionStatus.APPROVED_PLANNABLE:
                    if initial_truth is None:
                        raise ValueError("initial Repository Truth is required for first start")
                    result = self.runtime.start(self.mission_id, initial_truth)
                else:
                    if initial_truth is not None:
                        raise ValueError("Repository Truth cannot be replaced on reopen")
                    result = self.runtime.resume(self.mission_id) if state.status in _RUNNING else self.runtime._result(state)
                deadline = time.monotonic() + self.maximum_wait_seconds
                while True:
                    state = self.runtime.states.get(self.mission_id)
                    if state.status in _STOPPED:
                        return self._report(result, "terminal")
                    if self._stop.is_set() or self._requested(token):
                        return self._report(result, "operator_stop")
                    if not authorized():
                        return self._report(result, "authority_revoked")
                    if state.status not in _RUNNING:
                        return self._report(result, "paused_or_external_gate")
                    if time.monotonic() >= deadline:
                        return self._report(result, "wait_bound_reached")
                    self._stop.wait(min(self.poll_seconds, max(0, deadline - time.monotonic())))
                    if self._stop.is_set() or self._requested(token):
                        return self._report(result, "operator_stop")
                    if not authorized():
                        return self._report(result, "authority_revoked")
                    result = self.runtime.resume(self.mission_id)
            finally:
                self.runtime._keep_running = lambda: True
                signal.signal(signal.SIGINT, previous_int)
                signal.signal(signal.SIGTERM, previous_term)

    def _report(self, result, reason: str) -> dict[str, object]:
        state = self.runtime.states.get(self.mission_id)
        return {**asdict(result), "status": state.status.value, "stop_reason": reason,
                "waiting_reason": state.waiting_reason,
                "completion": state.completion, "revision": state.revision}


@contextmanager
def require_no_controller(database_path: Path) -> Iterator[None]:
    """Fence admission and governance mutations against a foreground run."""
    if fcntl is None:
        raise RuntimeServiceBusy("foreground controller locking is unavailable")
    lease = database_path.parent / "forge-mission-controller.lock"
    with lease.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeServiceBusy("a foreground Mission controller is active") from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def request_stop(database_path: Path, mission_id: str) -> bool:
    """Request stop of the currently bound process without mutating Mission state."""
    root = database_path.parent
    lease = root / "forge-mission-controller.lock"
    control = root / "forge-mission-controller.json"
    if fcntl is None or not lease.is_file() or not control.is_file():
        return False
    with lease.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                selected = json.loads(control.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                return False
            if selected.get("mission_id") != mission_id or not isinstance(selected.get("token"), str):
                return False
            _write(root / "forge-mission-stop.json",
                   {"mission_id": mission_id, "token": selected["token"], "stop": True})
            return True
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return False

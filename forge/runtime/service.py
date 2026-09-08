"""Supervised Forge Runtime Service over the canonical application loop."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Callable, Iterator, Protocol

try:  # macOS/Linux runtime product path
    import fcntl
except ImportError:  # pragma: no cover - fail closed where no lock exists
    fcntl = None  # type: ignore[assignment]

from forge.state import MissionExecutionStatus, MissionStateStore


class RuntimeLoop(Protocol):
    def run(self): ...
    def resume(self, mission_id: str): ...


class RuntimeServiceBusy(RuntimeError):
    """Another service or mutating CLI call owns this runtime instance."""


class RuntimeServiceLock:
    """A process-wide lease shared by service and mutating CLI composition.

    It is deliberately a filesystem lock beside the canonical runtime database,
    not a second database row.  Consumers can wrap a CLI mutation with this
    same lease and cannot race a dispatching service tick.
    """

    def __init__(self, runtime_database_path: Path | str) -> None:
        self.path = Path(runtime_database_path).with_name("forge-runtime-mutation.lock")

    @contextmanager
    def acquire(self) -> Iterator[None]:
        if fcntl is None:
            raise RuntimeServiceBusy("runtime instance locking is unavailable")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeServiceBusy("canonical runtime is busy") from error
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@dataclass(frozen=True)
class RuntimeServiceTick:
    resumed_mission_ids: tuple[str, ...]
    dispatched_mission_id: str | None
    progressed: bool


class ForgeRuntimeService:
    """Supervise the qualified loop without becoming an Execution Host.

    Every tick takes the same canonical-instance lease available to mutating
    CLI composition.  It resumes one persisted Mission before admitting new
    work, preserving single-flight dispatch semantics across restarts.
    """

    def __init__(self, loop: RuntimeLoop, states: MissionStateStore, *, runtime_database_path: Path | str,
                 wait: Callable[[float], None] = sleep, minimum_backoff: float = 0.25,
                 maximum_backoff: float = 5.0) -> None:
        if minimum_backoff <= 0 or maximum_backoff < minimum_backoff:
            raise ValueError("runtime service backoff bounds are invalid")
        self._loop, self._states = loop, states
        self._lock = RuntimeServiceLock(runtime_database_path)
        self._wait, self._minimum_backoff, self._maximum_backoff = wait, minimum_backoff, maximum_backoff

    @property
    def mutation_lock(self) -> RuntimeServiceLock:
        return self._lock

    def tick(self) -> RuntimeServiceTick:
        with self._lock.acquire():
            resumable = {MissionExecutionStatus.READY, MissionExecutionStatus.ACTIVE,
                         MissionExecutionStatus.WAITING_FOR_EXECUTION, MissionExecutionStatus.WAITING_FOR_EVIDENCE}
            for state in self._states.resumable():
                if state.status in resumable:
                    resumed = self._loop.resume(state.mission_id)
                    revision = getattr(resumed, "revision", state.revision)
                    return RuntimeServiceTick((state.mission_id,), None, revision != state.revision)
            result = self._loop.run()
            return RuntimeServiceTick((), None if result is None else result.mission_id, result is not None)

    def serve(self, *, keep_running: Callable[[], bool]) -> None:
        """Run with bounded interruptible backoff; caller controls pause/stop."""
        delay = self._minimum_backoff
        while keep_running():
            try:
                tick = self.tick()
            except RuntimeServiceBusy:
                tick = RuntimeServiceTick((), None, False)
            if tick.progressed:
                delay = self._minimum_backoff
                continue
            # Do not sleep through a requested pause/shutdown.  The bounded
            # delay also prevents a WAITING_FOR_EVIDENCE poll from busy-looping.
            if not keep_running():
                break
            self._wait(delay)
            delay = min(self._maximum_backoff, delay * 2)

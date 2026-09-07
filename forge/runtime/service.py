"""Minimal supervised Forge Runtime Service using the qualified loop unchanged."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from forge.state import MissionExecutionStatus, MissionStateStore


class RuntimeLoop(Protocol):
    """The qualified loop surface reused by the service."""

    def run(self): ...

    def resume(self, mission_id: str): ...


@dataclass(frozen=True)
class RuntimeServiceTick:
    """Read-time result; Mission State remains the authority."""

    resumed_mission_ids: tuple[str, ...]
    dispatched_mission_id: str | None


class ForgeRuntimeService:
    """Supervise the existing ExecutionLoop without becoming an Execution Host.

    A tick resumes one persisted Mission before asking the Dispatcher for new
    work. This keeps the lane single-flight and preserves the CLI's semantics.
    """

    def __init__(self, loop: RuntimeLoop, states: MissionStateStore) -> None:
        self._loop, self._states = loop, states

    def tick(self) -> RuntimeServiceTick:
        resumable = {MissionExecutionStatus.READY, MissionExecutionStatus.ACTIVE,
                     MissionExecutionStatus.WAITING_FOR_EXECUTION, MissionExecutionStatus.WAITING_FOR_EVIDENCE}
        for state in self._states.resumable():
            if state.status in resumable:
                self._loop.resume(state.mission_id)
                return RuntimeServiceTick((state.mission_id,), None)
        result = self._loop.run()
        return RuntimeServiceTick((), None if result is None else result.mission_id)

    def serve(self, *, keep_running: Callable[[], bool]) -> None:
        """Caller-owned service loop: no hidden daemon or second state store."""
        while keep_running():
            self.tick()

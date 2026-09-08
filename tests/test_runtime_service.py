from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from forge.runtime.service import ForgeRuntimeService, RuntimeServiceBusy, RuntimeServiceLock
from forge.state import MissionExecutionStatus


@dataclass
class _State:
    mission_id: str
    status: MissionExecutionStatus
    revision: int


class _States:
    def __init__(self, state: _State | None) -> None: self.state = state
    def resumable(self): return () if self.state is None else (self.state,)


class _Loop:
    def __init__(self, state: _State, *, progresses: bool) -> None: self.state, self.progresses, self.calls = state, progresses, []
    def resume(self, mission_id):
        self.calls.append(mission_id)
        return _State(mission_id, self.state.status, self.state.revision + int(self.progresses))
    def run(self): return None


class RuntimeServiceTests(unittest.TestCase):
    def test_waiting_evidence_uses_bounded_interruptible_backoff(self) -> None:
        with TemporaryDirectory() as root:
            state = _State("mission", MissionExecutionStatus.WAITING_FOR_EVIDENCE, 4)
            waits: list[float] = []
            service = ForgeRuntimeService(_Loop(state, progresses=False), _States(state),
                runtime_database_path=Path(root) / "runtime.db", wait=waits.append, minimum_backoff=0.1, maximum_backoff=0.2)
            calls = iter((True, True, True, False))
            service.serve(keep_running=lambda: next(calls))
            self.assertEqual(waits, [0.1])

    def test_service_and_mutating_cli_share_one_runtime_lease(self) -> None:
        with TemporaryDirectory() as root:
            path = Path(root) / "runtime.db"
            lock = RuntimeServiceLock(path)
            with lock.acquire():
                with self.assertRaises(RuntimeServiceBusy):
                    with RuntimeServiceLock(path).acquire():
                        pass


if __name__ == "__main__":
    unittest.main()

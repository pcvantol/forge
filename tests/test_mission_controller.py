"""Foreground control owns one selected Mission through its real state changes."""
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from forge.runtime.mission_controller import MissionController, request_stop
from forge.runtime.service import RuntimeServiceBusy
from forge.state import MissionExecutionStatus


@dataclass(frozen=True)
class _Result:
    mission_id: str
    runtime_id: str
    status: str
    action_ids: tuple[str, ...]
    current_action_id: str | None
    planning_invocations: int


class _States:
    def __init__(self):
        self.status = MissionExecutionStatus.APPROVED_PLANNABLE
        self.revision = 1

    def get(self, mission_id):
        if mission_id != "MISSION-0042":
            raise ValueError("wrong Mission")
        return SimpleNamespace(status=self.status, revision=self.revision,
                               waiting_reason=None, completion=None)


class _Runtime:
    def __init__(self, path: Path):
        self.database = SimpleNamespace(path=path)
        self.authorized = True
        self.repository = SimpleNamespace(operators=SimpleNamespace(
            context=lambda: "operator-binding-v1", authorize=lambda context: self.authorized))
        self.states = _States()
        self.started = 0
        self.resumed = 0

    def _result(self, state):
        return _Result("MISSION-0042", "runtime", state.status.value,
                       (), None, self.resumed)

    def start(self, mission_id, truth):
        self.started += 1
        self.states.status = MissionExecutionStatus.WAITING_FOR_EVIDENCE
        self.states.revision += 1
        return self._result(self.states.get(mission_id))

    def resume(self, mission_id):
        self.resumed += 1
        self.states.status = MissionExecutionStatus.COMPLETED
        self.states.revision += 1
        return self._result(self.states.get(mission_id))


class MissionControllerTests(unittest.TestCase):
    def test_one_start_drives_waiting_mission_to_completion(self):
        with TemporaryDirectory() as directory:
            runtime = _Runtime(Path(directory) / "forge.db")
            report = MissionController(runtime, "MISSION-0042", poll_seconds=.001).run(initial_truth=object())
            self.assertEqual((runtime.started, runtime.resumed), (1, 1))
            self.assertEqual((report["status"], report["stop_reason"]), ("COMPLETED", "terminal"))
            self.assertFalse((Path(directory) / "forge-mission-controller.json").exists())

    def test_reopen_continues_ready_to_continue_state(self):
        with TemporaryDirectory() as directory:
            runtime = _Runtime(Path(directory) / "forge.db")
            runtime.states.status = MissionExecutionStatus.READY_TO_CONTINUE
            report = MissionController(runtime, "MISSION-0042", poll_seconds=.001).run()
            self.assertEqual((runtime.started, runtime.resumed), (0, 1))
            self.assertEqual(report["status"], "COMPLETED")

    def test_second_controller_is_excluded_for_full_process_lifetime(self):
        with TemporaryDirectory() as directory:
            runtime = _Runtime(Path(directory) / "forge.db")
            first = MissionController(runtime, "MISSION-0042")
            second = MissionController(runtime, "MISSION-0042")
            with first._acquire():
                with self.assertRaises(RuntimeServiceBusy):
                    with second._acquire():
                        pass
                self.assertTrue(request_stop(runtime.database.path, "MISSION-0042"))
                self.assertFalse(request_stop(runtime.database.path, "MISSION-0043"))
            self.assertFalse(request_stop(runtime.database.path, "MISSION-0042"))

    def test_stop_during_first_tick_preserves_waiting_ep_state(self):
        with TemporaryDirectory() as directory:
            runtime = _Runtime(Path(directory) / "forge.db")
            controller = MissionController(runtime, "MISSION-0042", poll_seconds=.001)
            original_start = runtime.start

            def interrupted_start(mission_id, truth):
                result = original_start(mission_id, truth)
                controller._stop.set()
                return result

            runtime.start = interrupted_start
            report = controller.run(initial_truth=object())
            self.assertEqual(report["stop_reason"], "operator_stop")
            self.assertEqual(report["status"], "WAITING_FOR_EVIDENCE")
            self.assertEqual(runtime.resumed, 0)

    def test_revoked_operator_cannot_continue_after_first_tick(self):
        with TemporaryDirectory() as directory:
            runtime = _Runtime(Path(directory) / "forge.db")
            original_start = runtime.start

            def revoked_after_submission(mission_id, truth):
                result = original_start(mission_id, truth)
                runtime.authorized = False
                return result

            runtime.start = revoked_after_submission
            report = MissionController(runtime, "MISSION-0042", poll_seconds=.001).run(initial_truth=object())
            self.assertEqual(report["stop_reason"], "authority_revoked")
            self.assertEqual(report["status"], "WAITING_FOR_EVIDENCE")
            self.assertEqual(runtime.resumed, 0)


if __name__ == "__main__":
    unittest.main()

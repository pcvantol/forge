"""PA-F0 peer fixture is a strict compatibility vector, never an execution grant."""
from __future__ import annotations

from copy import deepcopy
from importlib.resources import files
import json
import unittest

from forge.parallel_action_contract import ParallelActionContractError, validate_peer_graph


def fixture() -> dict:
    return json.loads(files("forge").joinpath("api/parallel-action-peer-graph-v1.json").read_text())


class ParallelActionPeerContractTests(unittest.TestCase):
    def test_packaged_two_target_fan_out_join_fixture_is_valid_and_authority_free(self) -> None:
        result = validate_peer_graph(fixture())
        self.assertEqual([item["action_id"] for item in result["actions"]],
                         ["ACTION-A", "ACTION-B", "ACTION-Q"])
        self.assertEqual([item["target"]["repository_id"] for item in result["actions"][:2]],
                         ["repository-a", "repository-b"])
        self.assertEqual([item["predecessor_action_id"] for item in result["actions"][2]["dependencies"]],
                         ["ACTION-A", "ACTION-B"])
        self.assertFalse(result["dispatch_authorized"])

    def test_wrong_target_duplicate_missing_or_cyclic_edge_fails_closed(self) -> None:
        cases = []
        wrong_target = fixture()
        wrong_target["actions"][2]["dependencies"][1]["required_evidence"]["repository_id"] = "repository-a"
        cases.append(wrong_target)
        duplicate = fixture()
        duplicate["actions"][1]["action_id"] = "ACTION-A"
        cases.append(duplicate)
        missing = fixture()
        missing["actions"][2]["dependencies"][0]["predecessor_action_id"] = "ACTION-MISSING"
        cases.append(missing)
        cyclic = fixture()
        cyclic["actions"][0]["dependencies"] = [deepcopy(cyclic["actions"][2]["dependencies"][0])]
        cyclic["actions"][0]["dependencies"][0]["predecessor_action_id"] = "ACTION-Q"
        cases.append(cyclic)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ParallelActionContractError):
                validate_peer_graph(value)

    def test_bad_envelope_target_and_evidence_are_rejected(self) -> None:
        cases = []
        wrong_version = fixture()
        wrong_version["contract_version"] = "parallel-action-graph/v2"
        cases.append(wrong_version)
        invented_grant = fixture()
        invented_grant["dispatch_authorized"] = True
        cases.append(invented_grant)
        bad_target = fixture()
        bad_target["actions"][0]["target"]["repository_id"] = "../other"
        cases.append(bad_target)
        bad_digest = fixture()
        bad_digest["actions"][2]["dependencies"][0]["required_evidence"]["content_digest"] = "unknown"
        cases.append(bad_digest)
        bad_kind = fixture()
        bad_kind["actions"][2]["dependencies"][0]["required_evidence"]["kind"] = []
        cases.append(bad_kind)
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ParallelActionContractError):
                validate_peer_graph(value)

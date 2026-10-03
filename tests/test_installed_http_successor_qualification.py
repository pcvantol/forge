"""Guard the installed qualifier's observation of rejected EP HTTP traffic."""

from __future__ import annotations

import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from forge.ep_simulator import EpSimulatorServer, EpSimulatorState
from scripts.qualification.qualify_installed_http_successor import _count_ep_http_requests


class InstalledHttpSuccessorQualificationTests(unittest.TestCase):
    def test_listener_counts_unauthorized_get_and_post_without_simulator_audit(self) -> None:
        state = EpSimulatorState(
            project_id="test-project", repository_id="test-repository",
            repository_identity="pcvantol/forge", consumer_id="test-consumer",
            instance_id="test-instance", bearer_token="synthetic-token",
        )
        server = EpSimulatorServer(state)
        requests = _count_ep_http_requests(server)
        with server:
            for method in ("GET", "POST"):
                with self.subTest(method=method):
                    request = Request(server.base_url + "/v1/producer-compatibility", method=method)
                    with self.assertRaises(HTTPError) as error:
                        urlopen(request, timeout=5)
                    self.assertEqual(error.exception.code, 401)
                    error.exception.close()
        self.assertEqual(requests, ["GET", "POST"])
        self.assertEqual(state.audit, [])
        self.assertEqual(state.submission_ids(), ())

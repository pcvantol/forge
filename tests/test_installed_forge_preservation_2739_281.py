"""Exact historical maintenance admission; no installed product bytes change."""
from types import SimpleNamespace
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from test_installed_forge_update import update


class PublishedPreservationTransitionTests(unittest.TestCase):
    def request(self, root):
        return update.UpdateRequest(
            operation_id="bounded-preservation", version="2.8.1",
            wheel=str(root / "forge_autonomy-2.8.1-py3-none-any.whl"),
            qualification_receipt=str(root / "release-complete.json"),
            controller_source="30d35b5ae56aaf898c13250b6adb5b788155bbc7",
            controller_sha256=update.file_digest(Path(update.__file__).resolve()),
            data_root=str(root / "data"), runtime_root=str(root / "maintenance"),
            runtime_id="selected-runtime", installation_id="selected-installation",
            peer_configuration_digest="sha256:" + "a" * 64,
            resolver=str(root / "forge"), resolver_sha256="sha256:" + "b" * 64,
            existing_interpreter=str(root / "original/bin/python"), existing_version="2.7.39",
            base_python=str(root / "python"),
            installed_wheel=str(root / "forge_autonomy-2.7.39-py3-none-any.whl"),
            **update.PRESERVATION_ARTIFACT_BINDING)

    def test_selected_external_transition_has_exact_schema_bounds(self):
        request = SimpleNamespace(existing_version="2.7.39", version="2.8.1")
        self.assertEqual(update.transition_schemas(request), (40, 45))

    def test_neighboring_historical_versions_are_not_selected(self):
        for source, target in (("2.7.38", "2.8.1"), ("2.7.39", "2.8.0"),
                               ("2.7.39", "2.10.0"), ("2.8.0", "2.8.1")):
            with self.subTest(source=source, target=target):
                with self.assertRaises(update.InstalledForgeUpdateError):
                    update.transition_schemas(SimpleNamespace(existing_version=source, version=target))

    def test_exact_artifact_source_release_and_controller_bounds_fail_before_effects(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            request = self.request(root)
            request.validate_structure()
            for field, value in update.PRESERVATION_ARTIFACT_BINDING.items():
                with self.subTest(field=field):
                    wrong = value[:-1] + ("0" if value[-1] != "0" else "1")
                    with self.assertRaises(update.InstalledForgeUpdateError):
                        replace(request, **{field: wrong}).validate_structure()
            for changes in ({"installed_wheel": ""}, {"existing_version": "2.7.38"},
                            {"controller_source": "x" * 40},
                            {"controller_sha256": "sha256:" + "0" * 64}):
                with self.subTest(changes=changes):
                    with self.assertRaises(update.InstalledForgeUpdateError):
                        replace(request, **changes).validate_structure()
            self.assertEqual(list(root.iterdir()), [])

    def test_fresh_exact_assessment_is_required_and_new_input_is_durably_bound(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            request = self.request(root)
            with self.assertRaisesRegex(update.InstalledForgeUpdateError, "assessment"):
                request.validate()
            selected = replace(request, assessment_digest="sha256:" + "c" * 64)
            selected.validate()
            self.assertNotEqual(selected.digest, request.digest)
            self.assertNotEqual(request.assessment_request_digest,
                                replace(request, installed_wheel=str(root / "different-original.whl")).assessment_request_digest)
            self.assertEqual(list(root.iterdir()), [])

    def test_legacy_serialization_omits_new_optional_input(self):
        with TemporaryDirectory() as temporary:
            selected = self.request(Path(temporary).resolve())
            old = replace(selected, existing_version="2.7.38", version="2.7.39", installed_wheel="")
            self.assertNotIn("installed_wheel", old.payload)
            self.assertNotIn("installed_wheel", old.assessment_binding)
            self.assertIn("installed_wheel", selected.payload)

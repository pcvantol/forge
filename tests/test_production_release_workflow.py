"""Guard the durable release-state ordering expected by production delivery."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


RELEASE_OPERATION = Path(__file__).parents[1] / "scripts" / "release_operation.py"
SPEC = importlib.util.spec_from_file_location("forge_release_operation_for_workflow", RELEASE_OPERATION)
assert SPEC and SPEC.loader
release_operation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = release_operation
SPEC.loader.exec_module(release_operation)


class ProductionReleaseWorkflowTests(unittest.TestCase):
    version = "2.3.0"
    source = "a" * 40
    policy = "forge-bootstrap-release-cadence-v2"

    def test_prepublication_operation_binds_exact_artifacts_and_terminal_states(self) -> None:
        workflow = Path(".github/workflows/forge-production-release.yml").read_text(encoding="utf-8")

        qualified_job = workflow.index("  build-and-qualify:")
        published_job = workflow.index("  registry-readback-and-published-evidence:")
        complete_job = workflow.index("  record-release-complete:")
        self.assertLess(qualified_job, published_job)
        self.assertLess(published_job, complete_job)
        self.assertIn("concurrency:", workflow)
        self.assertIn("--prepare-qualified", workflow)
        self.assertIn("--validate-qualified", workflow)
        self.assertIn("--mark-published", workflow)
        self.assertIn("--mark-cleanup-pending", workflow)
        self.assertIn("--complete", workflow)
        self.assertIn("forge-release-$VERSION-$SOURCE_SHA", workflow)
        self.assertIn('gh release create "$TAG" "$QUALIFIED" --draft --target "$SOURCE_SHA"', workflow)
        self.assertIn("Existing PyPI publication has no durable original release receipt", workflow)
        self.assertIn("forge-release-published-$VERSION-$SOURCE_SHA.json", workflow)
        self.assertIn("needs: [release-context, build-and-qualify, publish-pypi, registry-readback-and-published-evidence]", workflow)
        self.assertIn("gh release download \"$TAG\" --pattern \"$PUBLISHED_RECEIPT\" --dir published-readback", workflow)
        self.assertIn("CLEANUP_PENDING", workflow)
        self.assertIn("forge-pending-readback", workflow)
        self.assertIn("durable cleanup-pending receipt does not match PUBLISHED release identity", workflow)
        self.assertIn("Unexpected PyPI identity lookup status", workflow)
        self.assertIn('for artifact in "$wheel" "$sdist"; do', workflow)
        self.assertIn("registry-readback-digests.json", workflow)
        self.assertLess(
            workflow.index('for target in published-readback published-input/dist "$PENDING_READBACK"; do'),
            workflow.index("--complete"),
        )
        self.assertLess(workflow.index("durable cleanup-pending receipt"), workflow.index("--complete"))
        self.assertIn("--wheel-digest \"$WHEEL_DIGEST\"", workflow)
        self.assertIn('PENDING_READBACK="$(mktemp -d "$RUNNER_TEMP/forge-pending-readback-XXXXXX")"', workflow)
        self.assertIn('PENDING_CONFIRMATION="$(mktemp -d "$RUNNER_TEMP/forge-pending-confirmation-XXXXXX")"', workflow)
        self.assertIn('pending.qualification != published.qualification', workflow)
        self.assertIn("store.replace(current, pending)", workflow)
        self.assertNotIn("Path(published_path).write_bytes", workflow)
        self.assertIn('cmp "$PENDING_READBACK/$PENDING" "published-input/release-evidence/operations/$OPERATION_ID.json"', workflow)
        self.assertIn('test -e "$1" || test -L "$1"', workflow)
        self.assertIn('! rm -rf -- "$target" || target_exists "$target"', workflow)
        self.assertIn('if test "$pending_receipt_present" = 1; then', workflow)

    @staticmethod
    def _cleanup_step() -> str:
        workflow = Path(".github/workflows/forge-production-release.yml").read_text(encoding="utf-8")
        start = workflow.index("      - name: Complete cleanup after durable PUBLISHED evidence")
        script_start = workflow.index("        run: |\n", start) + len("        run: |\n")
        script_end = workflow.index("      - uses: actions/upload-artifact", script_start)
        return textwrap.dedent(workflow[script_start:script_end])

    def _fixture(
        self,
        root: Path,
        *,
        persisted_pending: bool,
        tampered_pending_qualification: bool = False,
    ) -> dict[str, object]:
        work = root / "work directory"
        work.mkdir()
        (work / "scripts").mkdir()
        shutil.copy2(RELEASE_OPERATION, work / "scripts" / "release_operation.py")

        dist = work / "published-input" / "dist"
        dist.mkdir(parents=True)
        wheel = dist / f"forge_autonomy-{self.version}-py3-none-any.whl"
        sdist = dist / f"forge_autonomy-{self.version}.tar.gz"
        wheel.write_bytes(b"qualified Forge wheel")
        sdist.write_bytes(b"qualified Forge source distribution")
        operation_id = f"forge-release-{self.version}-{self.source}"
        expected = release_operation.ReleaseOperation.create(
            operation_id=operation_id,
            version=self.version,
            policy_revision=self.policy,
            source_revision=self.source,
            artifacts={
                "wheel": release_operation.ReleaseOperationStore.artifact_digest(wheel),
                "sdist": release_operation.ReleaseOperationStore.artifact_digest(sdist),
            },
        )
        evidence_root = work / "published-input" / "release-evidence"
        qualification = {"exact_main_sha": self.source, "qualification": "PASS"}
        publication = {"readback": "PASS", "registry": "pypi"}
        release_operation.prepare_qualified(
            release_operation.ReleaseOperationStore(evidence_root), expected, qualification
        )
        release_operation.mark_published(
            release_operation.ReleaseOperationStore(evidence_root), expected, publication
        )
        journal = evidence_root / "operations" / f"{operation_id}.json"
        published_bytes = journal.read_bytes()

        assets = root / "fake release assets"
        assets.mkdir()
        published_name = f"forge-release-published-{self.version}-{self.source}.json"
        pending_name = f"forge-cleanup-pending-{self.version}-{self.source}.json"
        (assets / published_name).write_bytes(published_bytes)
        if persisted_pending:
            release_operation.mark_cleanup_pending(
                release_operation.ReleaseOperationStore(evidence_root),
                expected,
                {
                    "error": "original cleanup failure",
                    "result": "CLEANUP_PENDING",
                    "targets": ["published-readback", "published-input/dist"],
                },
            )
            (assets / pending_name).write_bytes(journal.read_bytes())
            journal.write_bytes(published_bytes)
            journal.chmod(0o400)
            if tampered_pending_qualification:
                pending_values = json.loads((assets / pending_name).read_text(encoding="utf-8"))
                pending_values["qualification"] = {**qualification, "qualification": "TAMPERED"}
                (assets / pending_name).write_text(
                    json.dumps(pending_values, sort_keys=True, separators=(",", ":")) + "\n",
                    encoding="utf-8",
                )

        fake_bin = root / "fake bin"
        fake_bin.mkdir()
        (fake_bin / "gh").write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail
                test "$1" = release
                action="$2"
                shift 2
                case "$action" in
                  download)
                    tag="$1"
                    shift
                    pattern=""
                    directory=""
                    while test "$#" -gt 0; do
                      case "$1" in
                        --pattern) pattern="$2"; shift 2 ;;
                        --dir) directory="$2"; shift 2 ;;
                        *) shift ;;
                      esac
                    done
                    test -n "$tag"
                    test -n "$pattern"
                    test -n "$directory"
                    test -f "$FAKE_GH_ASSETS/$pattern" || exit 1
                    cp -- "$FAKE_GH_ASSETS/$pattern" "$directory/$pattern"
                    ;;
                  upload)
                    tag="$1"
                    artifact="$2"
                    test -n "$tag"
                    printf '%s\\n' "$(basename "$artifact")" >> "$FAKE_GH_UPLOAD_LOG"
                    cp -- "$artifact" "$FAKE_GH_ASSETS/$(basename "$artifact")"
                    ;;
                  view)
                    echo false
                    ;;
                  edit)
                    exit 0
                    ;;
                  *)
                    exit 64
                    ;;
                esac
                """
            ),
            encoding="utf-8",
        )
        (fake_bin / "rm").write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail
                target=""
                for argument in "$@"; do
                  target="$argument"
                done
                if test "$target" = published-readback; then
                  /bin/rm -rf -- "$target"
                  ln -s missing-cleanup-target "$target"
                  exit 0
                fi
                exec /bin/rm "$@"
                """
            ),
            encoding="utf-8",
        )
        (fake_bin / "gh").chmod(0o700)
        (fake_bin / "rm").chmod(0o700)
        runner_temp = root / "runner temp"
        runner_temp.mkdir()
        return {
            "assets": assets,
            "journal": journal,
            "operation_id": operation_id,
            "pending_name": pending_name,
            "runner_temp": runner_temp,
            "upload_log": root / "uploads.log",
            "work": work,
            "environment": {
                **os.environ,
                "FAKE_GH_ASSETS": str(assets),
                "FAKE_GH_UPLOAD_LOG": str(root / "uploads.log"),
                "GH_TOKEN": "test-token",
                "OPERATION_ID": operation_id,
                "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                "RUNNER_TEMP": str(runner_temp),
                "SOURCE_SHA": self.source,
                "VERSION": self.version,
            },
        }

    def _run_cleanup_step(self, fixture: dict[str, object]) -> subprocess.CompletedProcess:
        work = fixture["work"]
        assert isinstance(work, Path)
        script = work / "cleanup-step.sh"
        script.write_text(self._cleanup_step(), encoding="utf-8")
        script.chmod(0o700)
        environment = fixture["environment"]
        assert isinstance(environment, dict)
        return subprocess.run(
            ["bash", str(script)],
            cwd=work,
            capture_output=True,
            check=False,
            env=environment,
            text=True,
            timeout=30,
        )

    def test_first_cleanup_failure_uploads_pending_after_dangling_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary), persisted_pending=False)
            result = self._run_cleanup_step(fixture)
            self.assertEqual(1, result.returncode, msg=result.stdout + result.stderr)
            assets = fixture["assets"]
            pending_name = fixture["pending_name"]
            upload_log = fixture["upload_log"]
            work = fixture["work"]
            assert isinstance(assets, Path)
            assert isinstance(pending_name, str)
            assert isinstance(upload_log, Path)
            assert isinstance(work, Path)
            pending = json.loads((assets / pending_name).read_text(encoding="utf-8"))
            self.assertEqual("CLEANUP_PENDING", pending["state"])
            journal = fixture["journal"]
            assert isinstance(journal, Path)
            self.assertEqual("CLEANUP_PENDING", json.loads(journal.read_text(encoding="utf-8"))["state"])
            self.assertIn(pending_name, upload_log.read_text(encoding="utf-8"))
            self.assertTrue((work / "published-readback").is_symlink())
            self.assertFalse((work / "published-input" / "dist").exists())

    def test_repeat_cleanup_failure_hydrates_and_retains_existing_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(Path(temporary), persisted_pending=True)
            assets = fixture["assets"]
            pending_name = fixture["pending_name"]
            journal = fixture["journal"]
            upload_log = fixture["upload_log"]
            assert isinstance(assets, Path)
            assert isinstance(pending_name, str)
            assert isinstance(journal, Path)
            assert isinstance(upload_log, Path)
            original_pending = (assets / pending_name).read_bytes()

            result = self._run_cleanup_step(fixture)

            self.assertEqual(1, result.returncode, msg=result.stdout + result.stderr)
            self.assertIn("Existing durable CLEANUP_PENDING receipt retained", result.stderr)
            self.assertEqual(original_pending, (assets / pending_name).read_bytes())
            self.assertFalse(upload_log.exists())
            self.assertEqual(
                "CLEANUP_PENDING",
                json.loads(journal.read_text(encoding="utf-8"))["state"],
            )

    def test_pending_hydration_rejects_a_canonical_receipt_with_changed_qualification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._fixture(
                Path(temporary),
                persisted_pending=True,
                tampered_pending_qualification=True,
            )
            result = self._run_cleanup_step(fixture)
            journal = fixture["journal"]
            assert isinstance(journal, Path)

            self.assertNotEqual(0, result.returncode)
            self.assertIn("durable cleanup-pending receipt does not match PUBLISHED release identity", result.stderr)
            self.assertEqual("PUBLISHED", json.loads(journal.read_text(encoding="utf-8"))["state"])


if __name__ == "__main__":
    unittest.main()

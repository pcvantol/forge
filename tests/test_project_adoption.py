"""Semantic preview controls over explicit synthetic document evidence."""
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from forge.project_adoption import service, cli
from forge.project_bootstrap import service as bootstrap
from forge.project_bootstrap.schema import ContractError, canonical

VISION = "docs/product/VISION.md"
ARCH = "docs/architecture/ARCHITECTURE.md"


def supplied(role="authority"):
    value = json.loads(Path("examples/project-bootstrap/" + role + "-input.json").read_text())
    result = {"contract_version": "pb-adoption-preview/1.0", "bootstrap_input": value,
              "inventory": {"contract_version": "supplied-document-inventory/1.0",
              "origin": {"kind": "SUPPLIED_OBSERVATION", "qualification": "SUPPLIED_UNVERIFIED", "repository_id": value["identity"]["repository_id"], "revision": "synthetic-r1", "declared_current_revision": "synthetic-r1", "reference": "synthetic-evidence-1"},
              "coverage": {"scope": "PARTIAL_SUPPLIED", "covered_paths": [], "excluded_paths": []},
              "context": {"worktree_state": "CLEAN_SUPPLIED", "staged_paths": [], "dirty_paths": [], "untracked_paths": [], "ignored_paths": [], "product_code": "PRESENT_SUPPLIED"}, "documents": []},
              "inventory_digest": "", "requested_artifacts": [VISION, ARCH], "mappings": []}
    return bind(result)


def bind(value):
    value["inventory_digest"] = bootstrap.digest(canonical(value["inventory"]))
    return value


def document(value, path, content=None, status="PRESENT", **extra):
    item = {"path": path, "status": status, **extra}
    if status == "PRESENT":
        item.update(content=content, sha256=bootstrap.digest(content.encode()), mode=0o644)
    value["inventory"]["documents"].append(item)
    value["inventory"]["coverage"]["covered_paths"].append(path)
    return bind(value)


class AdoptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="forge-adoption-", dir=str(Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_missing_and_typed_unknown_never_add(self):
        for status in [None, "UNKNOWN", "REFUSED", "NOT_EXAMINED"]:
            value = supplied()
            if status:
                document(value, ARCH, status=status)
            result = service.preview(value)
            row = next(x for x in result["entries"] if x["artifact_path"] == ARCH)
            self.assertEqual(row["operation"], "INSUFFICIENT_INFORMATION")
            self.assertEqual(row["after"], {})
            self.assertEqual(result["repository_quality"], "NOT_ASSESSED")

    def test_explicit_absence_adds_real_baseline_document(self):
        value = document(supplied(), ARCH, status="ABSENT")
        row = next(x for x in service.preview(value)["entries"] if x["artifact_path"] == ARCH)
        self.assertEqual(row["operation"], "PROPOSE_ADDITION")
        self.assertEqual(row["after"]["content"].encode(), bootstrap.render(value["bootstrap_input"])[ARCH])
        self.assertEqual(row["before"], {"status": "ABSENT"})
        self.assertIn("OWNER_REVIEW_REQUIRED_NO_EFFECT_AUTHORITY", row["decisions"])

    def test_mapping_preserves_dutch_vision_without_duplicate(self):
        value = document(supplied(), "docs/RICHTING.md", "# Visie\nBestaande Nederlandse richting.\n", artifact_hint="PB-A13", semantic_owner="Business", update_class="PROJECT_OWNED")
        document(value, VISION, status="ABSENT")
        value["mappings"] = [{"artifact_path": VISION, "source_path": "docs/RICHTING.md", "choice": "LINK_EXISTING"}]
        result = service.preview(value)
        row = next(x for x in result["entries"] if x["artifact_path"] == VISION)
        self.assertEqual(row["operation"], "LINK_EXISTING")
        self.assertEqual(row["after"], {})
        self.assertTrue(row["mapping_only"])
        self.assertEqual(row["mapping_source"]["content"], "# Visie\nBestaande Nederlandse richting.\n")
        self.assertEqual(row["before"]["status"], "ABSENT")
        self.assertEqual(row["diff"], "")
        self.assertEqual(row["semantic_owner"], "Business")
        self.assertIn(b"Use the supplied existing document", service.readable(result))
        self.assertIn(b"not live EP inspection", service.readable(result))

    def test_ambiguous_and_unmapped_equivalent_require_choice(self):
        for number in [1, 2]:
            value = document(supplied(), VISION, status="ABSENT")
            for n in range(number):
                document(value, f"docs/vision-{n}.md", "Existing direction", artifact_hint="PB-A13")
            row = next(x for x in service.preview(value)["entries"] if x["artifact_path"] == VISION)
            self.assertEqual(row["operation"], "CONFLICT")
            self.assertEqual(row["after"], {})

    def test_present_same_or_different_is_kept_by_default(self):
        for content in ["Actual old architecture\n", bootstrap.render(supplied()["bootstrap_input"])[ARCH].decode()]:
            value = document(supplied(), ARCH, content)
            row = next(x for x in service.preview(value)["entries"] if x["artifact_path"] == ARCH)
            self.assertEqual(row["operation"], "KEEP")
            self.assertEqual(row["after"]["content"], content)

    def test_explicit_replacement_has_exact_before_after_and_diff(self):
        value = document(supplied(), ARCH, "# Existing\nOwner has not approved replacement.\n", update_class="PROJECT_OWNED", semantic_owner="Architecture")
        value["mappings"] = [{"artifact_path": ARCH, "source_path": ARCH, "choice": "PROPOSE_REPLACEMENT"}]
        row = next(x for x in service.preview(value)["entries"] if x["artifact_path"] == ARCH)
        self.assertEqual(row["operation"], "PROPOSE_CHANGE")
        self.assertIn("-Owner has not approved replacement.", row["diff"])
        self.assertEqual(row["after"]["sha256"], bootstrap.digest(row["after"]["content"].encode()))
        self.assertEqual(row["before"]["sha256"], bootstrap.digest(row["before"]["content"].encode()))

    def test_existing_pin_and_derived_content_are_never_replaced(self):
        for kind in ["PINNED_BASELINE", "DERIVED_PROJECTION", "APPEND_ONLY_EVIDENCE_REFERENCE"]:
            value = document(supplied(), ARCH, "Existing pinned bytes", update_class=kind)
            value["mappings"] = [{"artifact_path": ARCH, "source_path": ARCH, "choice": "PROPOSE_REPLACEMENT"}]
            row = next(x for x in service.preview(value)["entries"] if x["artifact_path"] == ARCH)
            self.assertEqual(row["operation"], "CONFLICT")
            self.assertEqual(row["after"], {})

    def test_coverage_exclusion_stale_source_and_identity_conflict(self):
        for reason in ["uncovered", "excluded", "stale", "wrongidentity"]:
            value = document(supplied(), ARCH, status="ABSENT")
            if reason == "uncovered": value["inventory"]["coverage"]["covered_paths"] = []
            if reason == "excluded": value["inventory"]["coverage"]["excluded_paths"] = [ARCH]
            if reason == "stale": value["inventory"]["origin"]["declared_current_revision"] = "newer-r2"
            if reason == "wrongidentity": value["inventory"]["origin"]["repository_id"] = "other-repo"
            row = next(x for x in service.preview(bind(value))["entries"] if x["artifact_path"] == ARCH)
            self.assertIn(row["operation"], ["CONFLICT", "INSUFFICIENT_INFORMATION"])
            self.assertEqual(row["after"], {})

    def test_dirty_context_and_missing_present_bytes_remain_open(self):
        value = document(supplied(), ARCH, "Existing bytes")
        del value["inventory"]["documents"][0]["content"]
        value["inventory"]["context"]["worktree_state"] = "DIRTY_SUPPLIED"
        value["inventory"]["context"]["staged_paths"] = ["src/app.py"]
        result = service.preview(bind(value))
        self.assertIn("UNCOMMITTED_OR_UNKNOWN_WORKTREE_PRESERVED", result["decisions"])
        self.assertEqual(next(x for x in result["entries"] if x["artifact_path"] == ARCH)["reason"], "SOURCE_BYTES_NOT_SUPPLIED")

    def test_b8r_conflict_and_fixed_path(self):
        value = supplied();value["requested_artifacts"] = [service.FIXED_PATH]
        document(value, service.FIXED_PATH, '{"schema_version":"1.0","project":{"id":"wrong"},"repository":{}}')
        self.assertEqual(service.preview(value)["entries"][0]["reason"], "EXISTING_IDENTITY_CONFLICT")
        value["mappings"] = [{"artifact_path": service.FIXED_PATH, "source_path": "elsewhere.json", "choice": "LINK_EXISTING"}]
        with self.assertRaises(ContractError): service.preview(value)

    def test_existing_code_never_gets_false_r50_quality_claim(self):
        value = supplied();value["requested_artifacts"] = ["docs/engineering/VALIDATION.md", "engineering/project-contract.json"]
        for path in value["requested_artifacts"]: document(value, path, status="ABSENT")
        for row in service.preview(value)["entries"]:
            self.assertEqual(row["operation"], "CONFLICT")
            self.assertNotIn("content", row["after"])

    def test_child_and_unsupported_role_artifact(self):
        value = supplied("child");value["requested_artifacts"] = ["README.md"]
        document(value, "README.md", status="ABSENT")
        document(value, "scripts/validate.sh", "# Existing repository validation; not executed by preview.\n")
        self.assertEqual(service.preview(value)["entries"][0]["operation"], "PROPOSE_ADDITION")
        value["requested_artifacts"] = [VISION]
        with self.assertRaises(ContractError): service.preview(value)

    def test_input_rejects_invalid_hash_status_alias_mapping_and_limits(self):
        initial = document(supplied(), ARCH, "Controlled bytes")
        for mutation in [lambda x: x.update(extra=True), lambda x: x.update(inventory_digest="0"*64),
                         lambda x: x["inventory"]["documents"][0].update(sha256="0"*64),
                         lambda x: x["inventory"]["documents"][0].update(status="ABSENT"),
                         lambda x: x["inventory"]["documents"][0].pop("mode"),
                         lambda x: x["inventory"]["documents"].append(deepcopy(x["inventory"]["documents"][0])),
                         lambda x: x["requested_artifacts"].append("../escape"),
                         lambda x: x["requested_artifacts"].append("/absolute"),
                         lambda x: x["requested_artifacts"].append("dóc.md"),
                         lambda x: x["requested_artifacts"].append(ARCH.upper()),
                         lambda x: x.update(mappings=[{"artifact_path":"not-requested.md","source_path":ARCH,"choice":"LINK_EXISTING"}])]:
            value = deepcopy(initial);mutation(value)
            if value["inventory_digest"] != "0"*64: bind(value)
            with self.assertRaises((ContractError, ValueError)): service.preview(value)
        with self.assertRaises(ContractError): service.check_input({})

    def test_determinism_and_changed_input_change_binding(self):
        value = document(supplied(), ARCH, status="ABSENT")
        before = deepcopy(value)
        self.assertEqual(service.payload(value), service.payload(deepcopy(value)))
        value["bootstrap_input"]["product"]["purpose"] = "Different explicit product purpose."
        self.assertNotEqual(service.preview(value)["proposal_digest"], service.preview(before)["proposal_digest"])
        self.assertEqual(before, document(supplied(), ARCH, status="ABSENT"))

    def test_actual_export_check_tamper_exclusive_and_source_preservation(self):
        value = document(supplied(), ARCH, status="ABSENT")
        original = canonical(value)
        target = self.root / "proposal"
        service.export(value, target)
        receipt = service.check_proposal(target)
        self.assertEqual(receipt["state"], "VALIDATED_PREVIEW_NOT_APPROVED")
        self.assertEqual(canonical(value), original)
        with self.assertRaises(FileExistsError): service.export(value, target)
        content = (target/"proposal.json").read_bytes();(target/"proposal.json").write_bytes(content+b' ')
        with self.assertRaises(ContractError): service.check_proposal(target)
        (target/"proposal.json").write_bytes(content)
        (target/"README.md").chmod(0o600)
        with self.assertRaises(ContractError): service.check_proposal(target)
        (target/"README.md").chmod(0o644);(target/"extra").write_text("unexpected")
        with self.assertRaises(ContractError): service.check_proposal(target)

    def test_no_follow_repository_ancestor_and_shared_export_limits(self):
        value = supplied();(self.root/"repo").mkdir();(self.root/"repo"/".git").mkdir()
        with self.assertRaises(ContractError): service.export(value, self.root/"repo"/"proposal")
        (self.root/"alias").symlink_to(self.root/"repo", target_is_directory=True)
        with self.assertRaises(OSError): service.export(value, self.root/"alias"/"proposal")
        for payload in [{}, {"../escape":b'x'}, {"bad":b'x'*131073}]:
            with self.assertRaises(ContractError): bootstrap.export_payload(payload, self.root/"output")
        with self.assertRaises(ContractError): bootstrap.export_payload({"ok":b'x'}, self.root/".."/"escape")

    def test_cross_path_replacement_rejects_and_link_target_conflict_is_visible(self):
        value = document(supplied(), "docs/RICHTING.md", "Selected source direction", artifact_hint="PB-A13")
        document(value, VISION, status="ABSENT")
        value["mappings"] = [{"artifact_path": VISION, "source_path": "docs/RICHTING.md", "choice": "PROPOSE_REPLACEMENT"}]
        with self.assertRaises(ContractError): service.preview(value)
        value["mappings"][0]["choice"] = "LINK_EXISTING"
        target = next(x for x in value["inventory"]["documents"] if x["path"] == VISION)
        target.update(status="PRESENT", content="Other conflicting direction", sha256=bootstrap.digest(b"Other conflicting direction"), mode=0o644)
        row = next(x for x in service.preview(bind(value))["entries"] if x["artifact_path"] == VISION)
        self.assertEqual(row["operation"], "CONFLICT")
        self.assertEqual(row["reason"], "CANONICAL_AND_MAPPING_DOCUMENT_CONFLICT")
        self.assertEqual(row["before"]["content"], "Other conflicting direction")

    def test_global_b8r_conflict_is_not_hidden_by_document_selection(self):
        value = document(supplied(), ARCH, status="ABSENT")
        document(value, service.FIXED_PATH, '{"schema_version":"1.0","project":{"id":"different"},"repository":{}}')
        result = service.preview(value)
        self.assertTrue(all(x["operation"] == "CONFLICT" and x["after"] == {} for x in result["entries"]))

    def test_context_absence_contradiction_and_unknown_ownership_are_not_changes(self):
        for name in ["staged_paths", "dirty_paths", "untracked_paths", "ignored_paths"]:
            value = document(supplied(), ARCH, status="ABSENT")
            value["inventory"]["context"][name] = [ARCH]
            row = next(x for x in service.preview(bind(value))["entries"] if x["artifact_path"] == ARCH)
            self.assertEqual(row["operation"], "CONFLICT")
        value = document(supplied(), ARCH, "Old owner bytes")
        value["mappings"] = [{"artifact_path": ARCH, "source_path": ARCH, "choice": "PROPOSE_REPLACEMENT"}]
        row = next(x for x in service.preview(value)["entries"] if x["artifact_path"] == ARCH)
        self.assertEqual(row["reason"], "EXISTING_OWNERSHIP_OR_UPDATE_CLASS_UNKNOWN")

    def test_no_r50_exact_tree_validator_or_secret_path_is_adopted(self):
        value = supplied();value["bootstrap_input"]["mode"] = "MANAGED";value["bootstrap_input"]["host_profile"] = "GITHUB_DOCUMENTS"
        value["requested_artifacts"] = ["scripts/validate.sh", ".github/workflows/validation.yml"]
        for path in value["requested_artifacts"]: document(value, path, status="ABSENT")
        self.assertTrue(all(x["operation"] == "CONFLICT" for x in service.preview(value)["entries"]))
        for secret_path in [".env", ".env.production", ".aws/credentials", ".ssh/id_ed25519", ".netrc"]:
            value = document(supplied(), secret_path, "PRIVATE_TOKEN=synthetic-sentinel")
            with self.assertRaises(ContractError): service.preview(value)

    def test_private_root_and_untrusted_stdout_controls(self):
        value = document(supplied(), ARCH, "PRIVATE_SENTINEL=abc\x1b]2;malicious-title\x07")
        result = service.preview(value)
        self.assertNotIn(b"PRIVATE_SENTINEL", service.readable(result))
        self.assertNotIn(b"\x1b", service.readable(result))
        target=self.root/"private-proposal";service.export(value,target);target.chmod(0o755)
        with self.assertRaises(ContractError): service.check_proposal(target)
        target.chmod(0o700);self.assertEqual(service.check_proposal(target)["state"],"VALIDATED_PREVIEW_NOT_APPROVED")
        value["inventory"]["origin"]["revision"] = "revision\x1b]2;title"
        with self.assertRaises(ContractError): service.preview(bind(value))

    def test_coherently_rehashed_unknown_to_absent_plan_is_detected(self):
        value=supplied();target=self.root/"unknown-proposal";service.export(value,target)
        plan=json.loads((target/"proposal.json").read_text());row=plan["entries"][0]
        row.update(operation="PROPOSE_ADDITION",before={"status":"ABSENT"},after={"content":"Forged document", "sha256":bootstrap.digest(b"Forged document"),"mode":0o644})
        plan.pop("proposal_digest");plan["proposal_digest"]=bootstrap.digest(canonical(plan))
        (target/"proposal.json").write_bytes(canonical(plan));(target/"README.md").write_bytes(service.readable(plan))
        with self.assertRaises(ContractError): service.check_proposal(target)

    def test_present_b8r_without_bytes_globally_keeps_identity_comparison_open(self):
        value=document(supplied(), ARCH, status="ABSENT")
        document(value, service.FIXED_PATH, "Supplied but unavailable declaration bytes")
        del value["inventory"]["documents"][-1]["content"]
        result=service.preview(bind(value))
        self.assertIn("EXISTING_IDENTITY_BYTES_NOT_SUPPLIED",result["decisions"])
        self.assertTrue(all(x["operation"]=="INSUFFICIENT_INFORMATION" and x["after"]=={} for x in result["entries"]))

    def test_generated_document_references_require_known_existing_inputs(self):
        for path in ["README.md", "BOOTSTRAP.md", "AGENTS.md"]:
            value=supplied();value["requested_artifacts"]=[path];document(value,path,status="ABSENT")
            row=service.preview(value)["entries"][0]
            self.assertEqual(row["operation"],"INSUFFICIENT_INFORMATION")
            self.assertEqual(row["reason"],"R50_DOCUMENT_REFERENCES_NOT_ESTABLISHED")
            self.assertEqual(row["after"],{})
        value=supplied();value["requested_artifacts"]=["README.md"];document(value,"README.md",status="ABSENT")
        document(value,"scripts/validate.sh","Existing custom command bytes")
        row=service.preview(value)["entries"][0]
        self.assertEqual(row["operation"],"PROPOSE_ADDITION")
        self.assertIn("SUPPLIED_COMMAND_OR_CONTRACT_NOT_EXECUTED_OR_QUALIFIED",row["decisions"])

    def test_reserved_casefold_paths_del_and_git_export_are_rejected(self):
        for path in [".GIT/config", "docs/bad\x7f.md"]:
            value=document(supplied(),path,"Untrusted document")
            with self.assertRaises(ContractError):service.preview(value)
        for name in [".git",".GIT"]:
            with self.assertRaises(ContractError):service.export(supplied(),self.root/name)
            self.assertFalse((self.root/name).exists())

    def test_private_export_reopen_replacement_before_any_content_write(self):
        target=self.root/"race-proposal"
        real_open=os.open
        def replaced(name,flags,*args,**kwargs):
            if name==target.name and flags & os.O_DIRECTORY and kwargs.get("dir_fd") is not None:
                fd=kwargs["dir_fd"]
                os.rename(target.name,"retained-original",src_dir_fd=fd,dst_dir_fd=fd)
                os.mkdir(target.name,mode=0o755,dir_fd=fd)
            return real_open(name,flags,*args,**kwargs)
        with patch.object(bootstrap.os,"open",side_effect=replaced):
            with self.assertRaises(ContractError):service.export(supplied(),target)
        self.assertEqual(list(target.iterdir()),[])
        self.assertEqual(list((self.root/"retained-original").iterdir()),[])
        parent=self.root/"unprotected";parent.mkdir(mode=0o777);parent.chmod(0o777)
        with self.assertRaises(ContractError):service.export(supplied(),parent/"proposal")
        self.assertFalse((parent/"proposal").exists())

    def test_cli_real_commands_and_bounded_error_projection(self):
        value = document(supplied(), ARCH, status="ABSENT")
        path=self.root/"input.json";path.write_bytes(canonical(value));target=self.root/"proposal"
        for args in [["validate-input","--input",str(path)], ["preview","--input",str(path)], ["preview","--input",str(path),"--export",str(target)], ["check-proposal","--proposal",str(target)]]:
            with patch('sys.stdout',new_callable=io.StringIO) as output:
                self.assertEqual(cli.main(args),0)
                self.assertNotIn(str(path),output.getvalue())
        path.write_text('{"duplicate":1,"duplicate":2}')
        with patch('sys.stdout',new_callable=io.StringIO) as output:
            self.assertEqual(cli.main(["preview","--input",str(path)]),1)
            self.assertEqual(json.loads(output.getvalue())["error"],"INPUT_OR_PROPOSAL_REJECTED")

    def test_cross_group_casefold_aliases_are_rejected(self):
        for group in ["staged_paths", "dirty_paths", "untracked_paths", "ignored_paths", "covered_paths", "excluded_paths", "documents", "mapping_source"]:
            with self.subTest(group=group):
                value = document(supplied(), ARCH, status="ABSENT")
                if group in ["covered_paths", "excluded_paths"]:
                    value["inventory"]["coverage"][group].append(ARCH.upper())
                elif group == "documents":
                    value["inventory"]["documents"][0]["path"] = ARCH.upper()
                elif group == "mapping_source":
                    value["mappings"] = [{"artifact_path":ARCH,"source_path":ARCH.upper(),"choice":"LINK_EXISTING"}]
                else:
                    value["inventory"]["context"][group] = [ARCH.upper()]
                with self.assertRaises(ContractError):
                    service.preview(bind(value))

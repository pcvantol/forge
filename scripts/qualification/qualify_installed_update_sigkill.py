#!/usr/bin/env python3
"""Run one bounded, exact-artifact Forge update process-crash cell.

The supervisor signals only the controller process it created.  The caller
supplies an unused disposable root and the immutable published artifacts.
This script is not an installer or a physical-reboot qualification.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time


OLD = {
    "2.7.35": ("ff4c0d45f51161376104250cd6efcfb6f045b8ac", "79e7d7ef36da7c73c31981c39f4a1d90b0204965438779014fc129b79a2da2d0"),
    "2.7.36": ("ed1e623ef3cedd8c4f720510e0052409b2d5ab1f", "c10e9584649538f2f1547bb09fd3982cc3495dcf34ef807d66463661fdd5cd68"),
    "2.7.37": ("a78523603d6ea081d07875ea6b557e73b5d4fe63", "b8165e59935a1edf22590cf6378fab3c5b1014aded88eec1e1a294bfa1b94938"),
}
TARGET_SOURCE = "0a3d6e35b01da93bb5a674ae7795558655c16c7d"
TARGET_DIGEST = "e9a5609969b8e49476f44e99a6cf72b8edf60280a77e010effe55a3bc1b33af8"
CONTROLLER_SOURCE = "bf7ae99c67e32fd2047965f19ece30a35071e868"
CONTROLLER_DIGEST = "9c43e1c3dcb411fb5f81a6a70d99b0c28b6bb2c79117f70703a50037e2e78183"
RECEIPT_DIGEST = "7f8f4646a369ea565e52f8420df665acb64d032e5004e1b45ef7dc8427548c49"
PHASES = ("PREPARED", "STAGED", "ADOPTED", "BACKED_UP", "MIGRATION_QUALIFIED", "FENCED", "MIGRATED", "ACTIVATING", "ACTIVATED", "COMPLETE")
SIDE_EFFECTS = ("CANDIDATE_SLOT_UNRECEIPTED", "ADOPTION_UNJOURNALED", "BACKUP_UNJOURNALED",
                "QUALIFICATION_COPY_UNRECEIPTED", "FENCE_UNJOURNALED", "DB_SWAP_UNJOURNALED",
                "ACTIVATION_SWITCH_UNJOURNALED", "RECEIPT_UNJOURNALED", "STAGING_OWNER_TEMP")
ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "PYTHONNOUSERSITE": "1", "PYTHONSAFEPATH": "1"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("disposable sibling gained a symlink")
        rows.append((path.relative_to(root).as_posix(), digest(path) if path.is_file() else "DIRECTORY"))
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def run(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=root, env=ENV, capture_output=True, text=True, check=False)


def require(command: list[str], root: Path) -> str:
    result = run(command, root)
    if result.returncode:
        raise RuntimeError("disposable setup failed: " + result.stderr[-300:])
    return result.stdout


def phase_readback(state_path: Path, resolver: Path, runtime: Path, data_root: Path,
                   operation_id: str) -> dict[str, object]:
    try:
        state = json.loads(state_path.read_text())
    except (OSError, ValueError):
        state = {}
    receipt = state_path.with_name("receipt.json")
    resolved = resolver.resolve() if resolver.exists() else None
    if resolved is None:
        resolver_binding = "MISSING"
    elif resolved.is_relative_to(runtime / "fenced"):
        resolver_binding = "FENCED"
    elif resolved.is_relative_to(runtime / "legacy"):
        resolver_binding = "LEGACY_MANAGED"
    elif resolved.is_relative_to(runtime / "slots"):
        resolver_binding = "CANDIDATE_SLOT"
    else:
        resolver_binding = "EXISTING_INTERPRETER"
    return {
        "phase": state.get("phase"),
        "history_length": len(state.get("history", [])),
        "safety_disposition": state.get("safety_disposition"),
        "slot_count": len([path for path in (runtime / "slots").iterdir() if path.is_dir()]) if (runtime / "slots").exists() else 0,
        "slot_receipt_exists": any((runtime / "slots").glob("*/forge-installation-slot.json")) if (runtime / "slots").exists() else False,
        "staging_owner_exists": any((runtime / "slots").glob("*/forge-installation-staging.json")) if (runtime / "slots").exists() else False,
        "staging_temporary_exists": any((runtime / "slots").glob("*/.forge-installation-staging.json.tmp-*")) if (runtime / "slots").exists() else False,
        "backup_count": len(list((data_root / "backups" / "installation").iterdir())) if (data_root / "backups" / "installation").exists() else 0,
        "qualification_copy_exists": (state_path.parent / "qualification-copy" / "forge.db").exists(),
        "resolver_binding": resolver_binding,
        "receipt_exists": receipt.exists(),
        "database_exists": (data_root / "forge.db").exists(),
        "operation_id": operation_id,
    }


def boundary_hit(phase: str, current: dict[str, object], data_root: Path) -> bool:
    journal = current["phase"]
    if phase in PHASES:
        return journal == phase
    if phase == "CANDIDATE_SLOT_UNRECEIPTED":
        return journal == "PREPARED" and current["slot_count"] >= 1 and not current["slot_receipt_exists"]
    if phase == "STAGING_OWNER_TEMP":
        return journal == "PREPARED" and current["staging_temporary_exists"] and not current["slot_receipt_exists"]
    if phase == "ADOPTION_UNJOURNALED":
        return journal == "STAGED" and current["resolver_binding"] == "LEGACY_MANAGED"
    if phase == "BACKUP_UNJOURNALED":
        return journal == "ADOPTED" and current["backup_count"] == 1
    if phase == "QUALIFICATION_COPY_UNRECEIPTED":
        return journal == "BACKED_UP" and current["qualification_copy_exists"]
    if phase == "FENCE_UNJOURNALED":
        return journal == "MIGRATION_QUALIFIED" and current["resolver_binding"] == "FENCED"
    if phase == "DB_SWAP_UNJOURNALED" and journal == "FENCED":
        try:
            with sqlite3.connect(f"file:{data_root / 'forge.db'}?mode=ro&immutable=1", uri=True) as database:
                inventory = database.execute("SELECT value FROM runtime_metadata WHERE key='forge_version'").fetchone()
            return inventory is not None and inventory[0] == "2.7.38"
        except sqlite3.Error:
            return False
    if phase == "ACTIVATION_SWITCH_UNJOURNALED":
        return journal == "ACTIVATING" and current["resolver_binding"] == "CANDIDATE_SLOT"
    if phase == "RECEIPT_UNJOURNALED":
        return journal == "ACTIVATED" and current["receipt_exists"]
    return False


def qualify(root: Path, artifacts: Path, python: Path, baseline: str,
            phase: str, controller: Path, controller_source: str,
            controller_digest: str) -> dict[str, object]:
    if sys.version_info[:2] != (3, 14) or Path(sys.executable).resolve() != python.resolve():
        raise RuntimeError("supervisor must run on the supplied Python 3.14 interpreter")
    if root.exists():
        raise RuntimeError("disposable case root must be unused")
    if artifacts.is_relative_to(root) or root.is_relative_to(artifacts):
        raise RuntimeError("disposable root must be separate from published artifacts")
    old_source, old_hash = OLD[baseline]
    old = artifacts / f"forge_autonomy-{baseline}-py3-none-any.whl"
    target = artifacts / "forge_autonomy-2.7.38-py3-none-any.whl"
    receipts = list(artifacts.glob("forge-release-complete-2.7.38-*.json"))
    if len(receipts) != 1:
        raise RuntimeError("one exact release-complete receipt is required")
    receipt = receipts[0]
    for path, expected in ((old, old_hash), (target, TARGET_DIGEST),
                           (controller, controller_digest), (receipt, RECEIPT_DIGEST)):
        if not path.is_file() or digest(path) != expected:
            raise RuntimeError("published artifact digest mismatch: " + path.name)
    root.mkdir(parents=True, mode=0o700)
    runtime = root / "runtime"
    runtime.mkdir()
    spec = importlib.util.spec_from_file_location("exact_forge_controller", controller)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    instances = []
    for alias, port in (("alpha", "18767"), ("bravo", "18768")):
        venv = root / f"{alias}-venv"
        require([str(python), "-I", "-m", "venv", str(venv)], root)
        require([str(venv / "bin/python"), "-I", "-m", "pip", "install", "--isolated",
                 "--no-deps", "--no-index", str(old)], root)
        data_root = root / "instances" / f"temp-{alias}"
        data_root.parent.mkdir(exist_ok=True)
        initialized = json.loads(require([str(venv / "bin/forge"), "--data-root", str(data_root),
                                            "server", "init"], root))
        selected = data_root.with_name(initialized["instance_id"])
        data_root.rename(selected)
        require([str(venv / "bin/forge"), "--data-root", str(selected),
                 "execution-host", "configure", "--binding-id", f"ep-synthetic-{alias}",
                 "--endpoint", f"http://127.0.0.1:{port}", "--expected-instance-id", f"ep-synthetic-{alias}",
                 "--consumer-id", f"forge-synthetic-{alias}", "--host-id", f"local-synthetic-{alias}",
                 "--project-id", f"project-synthetic-{alias}", "--repository-id", f"repo-synthetic-{alias}",
                 "--repository-identity", f"repository-synthetic-{alias}",
                 "--credential-reference", "keychain://forge.ep/consumer",
                 "--operator-id", f"operator-synthetic-{alias}", "--allow-loopback-http"], root)
        (selected / "qualification-sentinel.txt").write_text(f"{alias}-sentinel\n")
        snapshot = module.database_snapshot(selected / "forge.db")
        instances.append((selected, venv, snapshot))
    (data_root, venv, snapshot), (sibling, _, _) = instances
    sibling_before = tree_digest(sibling)
    operation_id = f"forge-update-crash-{baseline.replace('.', '')}-{phase.lower()}"
    fields = {
        "operation_id": operation_id, "version": "2.7.38", "product_source": TARGET_SOURCE,
        "wheel": str(target), "wheel_sha256": "sha256:" + TARGET_DIGEST,
        "qualification_receipt": str(receipt), "qualification_receipt_sha256": "sha256:" + RECEIPT_DIGEST,
        "controller_source": controller_source, "controller_sha256": "sha256:" + controller_digest,
        "data_root": str(data_root), "runtime_root": str(runtime),
        "runtime_id": snapshot["metadata"]["runtime_id"],
        "installation_id": snapshot["metadata"]["installation_id"],
        "peer_configuration_digest": snapshot["peer"]["configuration_digest"],
        "resolver": str(venv / "bin/forge"),
        "resolver_sha256": module.file_digest(venv / "bin/forge"),
        "existing_interpreter": str(venv / "bin/python"), "existing_version": baseline,
        "base_python": str(python), "installed_source": old_source,
        "installed_artifact_digest": "sha256:" + old_hash,
    }
    args = [item for key, value in fields.items() for item in ("--" + key.replace("_", "-"), value)]
    command = [str(python), "-I", str(controller), *args]
    assessment = json.loads(require([*command, "--assess-only"], root))
    if assessment["state"] != "UPDATE_AVAILABLE":
        raise RuntimeError("exact update assessment denied")
    command += ["--assessment-digest", assessment["assessment_digest"]]
    state_path = data_root / "artifacts" / "installation" / operation_id / "operation.json"
    update_lock = runtime / "locks" / "installation-update.lock"
    update_lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with update_lock.open("a+b") as lock_stream:
        fcntl.flock(lock_stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        live_conflict_rejected = run(command, root).returncode != 0
        fcntl.flock(lock_stream, fcntl.LOCK_UN)
    if not live_conflict_rejected or state_path.exists():
        raise RuntimeError("normal controller accepted a competing live lock owner")
    before = phase_readback(state_path, venv / "bin/forge", runtime, data_root, operation_id)
    child = subprocess.Popen(command, cwd=root, env=ENV, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
    at_signal = None
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline and child.poll() is None:
        current = phase_readback(state_path, venv / "bin/forge", runtime, data_root, operation_id)
        if boundary_hit(phase, current, data_root) and child.poll() is None:
            at_signal = current
            try:
                if os.getpgid(child.pid) != child.pid:
                    raise RuntimeError("controller child is not its owned process-group leader")
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                at_signal = None
            break
        time.sleep(0)
    _, stderr = child.communicate(timeout=20)
    after_kill = phase_readback(state_path, venv / "bin/forge", runtime, data_root, operation_id)
    if child.returncode == -signal.SIGKILL:
        after_kill["inventory_version"] = module.database_snapshot(data_root / "forge.db")["metadata"]["forge_version"]
    descendants = 0
    for _ in range(100):
        processes = subprocess.run(["/bin/ps", "-axo", "pid=,pgid=,state="], capture_output=True, text=True)
        if processes.returncode:
            return {"result": "UNPROVEN", "reason": "descendant readback unavailable"}
        descendants = sum(1 for line in processes.stdout.splitlines()
                          if len(line.split()) == 3 and line.split()[1] == str(child.pid)
                          and not line.split()[2].startswith("Z"))
        if not descendants:
            break
        time.sleep(0.05)
    evidence: dict[str, object] = {
        "baseline": baseline, "target": "2.7.38", "requested_phase": phase,
        "old_wheel_sha256": old_hash, "target_wheel_sha256": TARGET_DIGEST,
        "controller_source": controller_source, "controller_sha256": controller_digest,
        "assessment": assessment["state"], "before": before,
        "at_signal": at_signal, "after_kill": after_kill,
        "signal_exit": "SIGKILL" if child.returncode == -signal.SIGKILL else "OTHER",
        "owned_descendants_alive": descendants,
        "live_conflict_rejected": live_conflict_rejected,
    }
    if (at_signal is None or child.returncode != -signal.SIGKILL or descendants
            or after_kill["phase"] != at_signal["phase"]):
        evidence.update(result="NOT_HIT", child_error=stderr[-200:])
        return evidence
    journal_phase = str(after_kill["phase"])
    expected_inventory = baseline if PHASES.index(journal_phase) < PHASES.index("MIGRATED") else "2.7.38"
    if phase == "DB_SWAP_UNJOURNALED":
        expected_inventory = "2.7.38"
    side_effects_valid = (
        after_kill["inventory_version"] == expected_inventory
        and (journal_phase == "PREPARED" or after_kill["slot_count"] == 1)
        and (PHASES.index(journal_phase) < PHASES.index("BACKED_UP") or after_kill["backup_count"] == 1)
        and (phase != "ADOPTED" or after_kill["resolver_binding"] == "CANDIDATE_SLOT")
        and (phase != "FENCED" or after_kill["safety_disposition"] == "LEGACY_COMMAND_FENCED")
        and (phase != "COMPLETE" or after_kill["receipt_exists"])
        and (phase in PHASES or boundary_hit(phase, after_kill, data_root))
    )
    if not side_effects_valid:
        evidence["result"] = "UNPROVEN"
        evidence["reason"] = "durable side effects do not prove requested boundary"
        return evidence
    changed = command.copy()
    changed[changed.index(TARGET_SOURCE)] = "0" * 40
    foreign_operation = command.copy()
    foreign_operation[foreign_operation.index(operation_id)] = "foreign-operation-id"
    foreign_instance = command.copy()
    foreign_instance[foreign_instance.index(fields["runtime_id"])] = "foreign-runtime-id"
    changed_rejected = run(changed, root).returncode != 0
    foreign_operation_rejected = run(foreign_operation, root).returncode != 0
    foreign_instance_rejected = run(foreign_instance, root).returncode != 0
    resumed = run(command, root)
    if resumed.returncode:
        evidence.update(result="GAP_PROVEN", resume_error=resumed.stderr[-200:])
        return evidence
    terminal = json.loads(resumed.stdout)
    terminal_bytes = state_path.with_name("receipt.json").read_bytes()
    replay = run(command, root)
    with sqlite3.connect(f"file:{data_root / 'forge.db'}?mode=ro", uri=True) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        foreign = db.execute("PRAGMA foreign_key_check").fetchall()
    replay_identical = (replay.returncode == 0 and json.loads(replay.stdout) == terminal
                        and state_path.with_name("receipt.json").read_bytes() == terminal_bytes)
    sibling_identical = tree_digest(sibling) == sibling_before
    receipted_slots = len(list((runtime / "slots").glob("*/forge-installation-slot.json")))
    success = (terminal.get("state") == "COMPLETE" and replay_identical and sibling_identical
               and changed_rejected and foreign_operation_rejected and foreign_instance_rejected
               and receipted_slots == 1
               and (data_root / "qualification-sentinel.txt").read_text() == "alpha-sentinel\n"
               and integrity == "ok" and not foreign)
    evidence.update(result="PASS" if success else "FAIL", terminal_state=terminal.get("state"),
                    changed_request_rejected=changed_rejected,
                    foreign_operation_rejected=foreign_operation_rejected,
                    foreign_instance_rejected=foreign_instance_rejected,
                    terminal_replay_identical=replay_identical,
                    sibling_byte_identical=sibling_identical, integrity_check=integrity,
                    foreign_key_count=len(foreign),
                    final_backup_count=len(list((data_root / "backups" / "installation").iterdir())),
                    final_slot_count=len([path for path in (runtime / "slots").iterdir() if path.is_dir()]),
                    final_receipted_slot_count=receipted_slots)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--baseline", choices=tuple(OLD), required=True)
    parser.add_argument("--phase", choices=PHASES + SIDE_EFFECTS, required=True)
    parser.add_argument("--controller", type=Path)
    parser.add_argument("--controller-source", default=CONTROLLER_SOURCE)
    parser.add_argument("--controller-sha256", default=CONTROLLER_DIGEST)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    artifacts = args.artifacts.resolve(strict=True)
    controller = (args.controller or artifacts / "update_installed_forge.py").resolve(strict=True)
    result = qualify(args.root.resolve(), artifacts,
                     args.python.resolve(strict=True), args.baseline, args.phase,
                     controller, args.controller_source, args.controller_sha256.removeprefix("sha256:"))
    args.evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

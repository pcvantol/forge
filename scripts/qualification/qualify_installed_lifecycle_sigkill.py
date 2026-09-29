#!/usr/bin/env python3
"""Qualify one exact-wheel Forge lifecycle SIGKILL boundary.

The child is the installed ``forge`` command in an unused disposable root.
The supervisor observes durable state/physical effects and signals only that
child.  Unhit boundaries remain NOT_HIT rather than inferred from timing.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time


TARGET_SOURCE = "0a3d6e35b01da93bb5a674ae7795558655c16c7d"
TARGET_SHA256 = "e9a5609969b8e49476f44e99a6cf72b8edf60280a77e010effe55a3bc1b33af8"
BOUNDARIES = {
    "preserve": ("PREPARED", "VERIFIED", "RECEIPT", "COMPLETE"),
    "restore": ("PREPARED", "VERIFIED", "RECEIPT", "COMPLETE"),
    "purge": ("PREPARED", "UNINSTALL_PREPARED", "UNINSTALL_VERIFIED", "UNINSTALL_DETACHED",
              "UNINSTALL_PARTIAL_DELETE", "UNINSTALL_REMOVED", "UNINSTALL_RECEIPT",
              "UNINSTALL_COMPLETE", "TOMBSTONE", "RECEIPT", "COMPLETE"),
}
ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "PYTHONNOUSERSITE": "1", "PYTHONSAFEPATH": "1"}


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RuntimeError("disposable sibling gained a symlink")
        rows.append((path.relative_to(root).as_posix(), file_digest(path) if path.is_file() else "DIRECTORY"))
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def run(command: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=root, env=ENV, capture_output=True, text=True, check=False)


def require(command: list[str], root: Path) -> str:
    result = run(command, root)
    if result.returncode:
        raise RuntimeError("disposable installed-wheel setup failed: " + result.stderr[-300:])
    return result.stdout


def read_state(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def observed_boundary(boundary: str, state: dict[str, object], receipt: Path,
                      tombstone: Path, quarantine: Path, files: int) -> dict[str, object] | None:
    phase = state.get("phase")
    if boundary in ("PREPARED", "VERIFIED", "COMPLETE"):
        return {"phase": phase} if phase == boundary else None
    if boundary.startswith("UNINSTALL_"):
        name = boundary.removeprefix("UNINSTALL_")
        if name in ("PREPARED", "VERIFIED", "DETACHED", "REMOVED", "COMPLETE"):
            return {"phase": phase} if phase == name else None
        if name == "RECEIPT" and receipt.exists() and phase != "COMPLETE":
            return {"phase": phase, "receipt_observed": True}
        if name == "PARTIAL_DELETE" and phase == "DETACHED":
            sentinel = quarantine / "crash-sentinel"
            if sentinel.is_dir():
                remaining = len(os.listdir(sentinel))
                if 0 < remaining < files:
                    return {"phase": phase, "files_before": files, "files_at_signal": remaining}
        return None
    if boundary == "TOMBSTONE" and tombstone.exists() and not receipt.exists():
        return {"phase": phase, "tombstone_observed": True}
    if boundary == "RECEIPT" and receipt.exists() and phase != "COMPLETE":
        return {"phase": phase, "receipt_observed": True}
    return None


def qualify(root: Path, wheel: Path, python: Path, operation: str,
            boundary: str, files: int) -> dict[str, object]:
    if sys.version_info[:2] != (3, 14) or Path(sys.executable).resolve() != python.resolve():
        raise RuntimeError("Forge process-crash harness requires selected Python 3.14")
    if operation not in BOUNDARIES or boundary not in BOUNDARIES[operation]:
        raise RuntimeError("operation or boundary is not registered")
    if root.exists():
        raise RuntimeError("disposable case root must be unused")
    wheel = wheel.resolve(strict=True)
    if file_digest(wheel) != TARGET_SHA256:
        raise RuntimeError("exact published Forge target wheel mismatch")
    root.mkdir(parents=True, mode=0o700)
    instances = root / "instances"
    instances.mkdir()
    venv = root / "venv"
    require([str(python), "-I", "-m", "venv", str(venv)], root)
    require([str(venv / "bin/python"), "-I", "-m", "pip", "install", "--isolated",
             "--no-deps", "--no-index", str(wheel)], root)
    forge = venv / "bin" / "forge"
    selected = None
    sibling = None
    identities = []
    for alias, port in (("alpha", "18767"), ("bravo", "18768")):
        initial = instances / ("temp-" + alias)
        initialized = json.loads(require([str(forge), "--data-root", str(initial), "server", "init"], root))
        data_root = instances / initialized["instance_id"]
        initial.rename(data_root)
        require([str(forge), "--data-root", str(data_root), "execution-host", "configure",
                 "--binding-id", f"ep-synthetic-{alias}", "--endpoint", f"http://127.0.0.1:{port}",
                 "--expected-instance-id", f"ep-synthetic-{alias}", "--consumer-id", f"forge-synthetic-{alias}",
                 "--host-id", f"local-synthetic-{alias}", "--project-id", f"project-synthetic-{alias}",
                 "--repository-id", f"repo-synthetic-{alias}", "--repository-identity", f"repository-synthetic-{alias}",
                 "--credential-reference", "keychain://forge.ep/consumer",
                 "--operator-id", f"operator-synthetic-{alias}", "--allow-loopback-http"], root)
        (data_root / "qualification-sentinel.txt").write_text(alias + "-sentinel\n")
        with sqlite3.connect(f"file:{data_root / 'forge.db'}?mode=ro", uri=True) as database:
            metadata = dict(database.execute("SELECT key,value FROM runtime_metadata"))
        identities.append((data_root, metadata))
    (selected, metadata), (sibling, _) = identities
    if operation == "purge" and boundary == "UNINSTALL_PARTIAL_DELETE":
        sentinel = selected / "crash-sentinel"
        sentinel.mkdir(mode=0o700)
        for index in range(files):
            (sentinel / f"file-{index:05d}").write_bytes(b"sentinel\n")
    sibling_before = tree_digest(sibling)
    identity = hashlib.sha256(selected.name.encode()).hexdigest()
    control = instances / ".forge-server-runtime-lifecycle" / identity
    op_id = f"forge-{operation}-crash-{boundary.lower().replace('_', '-')}"
    lifecycle = control / "instance-lifecycle-v1" / "operations" / op_id
    uninstall = control / "operations" / op_id
    tombstone = control / "instance-lifecycle-v1" / "purged.json"
    common = [str(forge), "--data-root", str(selected), "server", operation,
              "--operation-id", op_id, "--instances-root", str(instances),
              "--instance-id", selected.name, "--runtime-id", metadata["runtime_id"],
              "--installation-id", metadata["installation_id"], "--installed-version", "2.7.38",
              "--installed-source", TARGET_SOURCE,
              "--installed-artifact-digest", "sha256:" + TARGET_SHA256]
    if operation == "restore":
        preserve = common.copy()
        preserve[preserve.index("restore")] = "preserve"
        preserve[preserve.index(op_id)] = "forge-preserve-prerequisite"
        require(preserve, root)
        common += ["--preserve-operation-id", "forge-preserve-prerequisite"]
    control.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (control / "lifecycle.lock").open("a+b") as lock_stream:
        fcntl.flock(lock_stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        live_conflict_rejected = run(common, root).returncode != 0
        fcntl.flock(lock_stream, fcntl.LOCK_UN)
    if not live_conflict_rejected:
        raise RuntimeError("normal lifecycle entry accepted a competing live lock owner")
    state_path = (uninstall if boundary.startswith("UNINSTALL_") else lifecycle) / "state.json"
    receipt_path = state_path.with_name("receipt.json")
    child = subprocess.Popen(common, cwd=root, env=ENV, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
    observed = None
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and child.poll() is None:
        observed = observed_boundary(boundary, read_state(state_path), receipt_path,
                                     tombstone, uninstall / "detached-instance", files)
        if observed is not None and child.poll() is None:
            try:
                if os.getpgid(child.pid) != child.pid:
                    raise RuntimeError("Forge child is not its owned process-group leader")
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                observed = None
            break
        observed = None
        time.sleep(0)
    _, stderr = child.communicate(timeout=30)
    after = read_state(state_path)
    descendants = 0
    for _ in range(100):
        table = subprocess.run(("/bin/ps", "-axo", "pid=,pgid=,state="), capture_output=True, text=True)
        if table.returncode:
            return {"result": "UNPROVEN", "reason": "descendant readback unavailable"}
        descendants = sum(1 for line in table.stdout.splitlines()
                          if len(line.split()) == 3 and line.split()[1] == str(child.pid)
                          and not line.split()[2].startswith("Z"))
        if not descendants:
            break
        time.sleep(0.05)
    result: dict[str, object] = {
        "operation": operation, "boundary": boundary, "target_wheel_sha256": TARGET_SHA256,
        "source_checkout_import": False, "observed": observed, "phase_after_kill": after.get("phase"),
        "signal_exit": "SIGKILL" if child.returncode == -signal.SIGKILL else "OTHER",
        "owned_descendants_alive": descendants, "selected_root_after_kill": selected.exists(),
        "quarantine_after_kill": (uninstall / "detached-instance").exists(),
        "uninstall_receipt_after_kill": (uninstall / "receipt.json").exists(),
        "lifecycle_receipt_after_kill": (lifecycle / "receipt.json").exists(),
        "tombstone_after_kill": tombstone.exists(),
        "sibling_byte_identical_after_kill": tree_digest(sibling) == sibling_before,
    }
    if boundary == "UNINSTALL_PARTIAL_DELETE":
        sentinel = uninstall / "detached-instance" / "crash-sentinel"
        result["files_after_kill"] = len(os.listdir(sentinel)) if sentinel.is_dir() else 0
    if (observed is None or child.returncode != -signal.SIGKILL or descendants
            or after.get("phase") != observed["phase"]):
        result.update(result="NOT_HIT", child_error=stderr[-200:])
        return result
    if boundary == "UNINSTALL_PARTIAL_DELETE" and not 0 < result["files_after_kill"] < files:
        result.update(result="UNPROVEN", reason="partial deletion not retained")
        return result
    changed = common.copy()
    changed[changed.index(TARGET_SOURCE)] = "0" * 40
    changed_result = run(changed, root)
    changed_rejected = changed_result.returncode != 0
    status_command = [str(forge), "server", "lifecycle-status", "--operation-id", op_id,
                      "--instances-root", str(instances), "--instance-id", selected.name]
    foreign_operation = status_command.copy()
    foreign_operation[foreign_operation.index(op_id)] = "foreign-operation-no-evidence"
    foreign_instance = status_command.copy()
    foreign_instance[foreign_instance.index(selected.name)] = sibling.name
    foreign_operation_rejected = run(foreign_operation, root).returncode != 0
    foreign_instance_rejected = run(foreign_instance, root).returncode != 0
    resumed = run(common, root)
    if resumed.returncode:
        result.update(result="GAP_PROVEN", resume_error=resumed.stderr[-300:])
        return result
    terminal = json.loads(resumed.stdout)
    terminal_bytes = (lifecycle / "receipt.json").read_bytes()
    replay = run(common, root)
    identical = (replay.returncode == 0 and json.loads(replay.stdout) == terminal
                 and (lifecycle / "receipt.json").read_bytes() == terminal_bytes)
    integrity = None
    if selected.exists():
        with sqlite3.connect(f"file:{selected / 'forge.db'}?mode=ro", uri=True) as database:
            integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
            foreign = database.execute("PRAGMA foreign_key_check").fetchall()
    else:
        foreign = []
    purged = operation == "purge"
    purge_restore_rejected = None
    if purged:
        restore_after_purge = common.copy()
        restore_after_purge[restore_after_purge.index("purge")] = "restore"
        restore_after_purge[restore_after_purge.index(op_id)] = "restore-after-purge"
        restore_after_purge += ["--preserve-operation-id", "foreign-preserve"]
        purge_restore_rejected = run(restore_after_purge, root).returncode != 0
    okay = (identical and changed_rejected and live_conflict_rejected
            and foreign_operation_rejected and foreign_instance_rejected
            and (not purged or purge_restore_rejected)
            and tree_digest(sibling) == sibling_before
            and selected.exists() != purged and tombstone.exists() == purged
            and (purged or ((selected / "qualification-sentinel.txt").read_text() == "alpha-sentinel\n"
                            and integrity == "ok" and not foreign))
            and (operation != "restore" or terminal.get("ready") is False
                 and terminal.get("provider_auth_state") == "PRESERVED_REQUIRES_REVERIFICATION"))
    result.update(result="PASS" if okay else "FAIL", changed_request_rejected=changed_rejected,
                  live_conflict_rejected=live_conflict_rejected,
                  foreign_operation_status_rejected=foreign_operation_rejected,
                  foreign_instance_status_rejected=foreign_instance_rejected,
                  restore_after_purge_rejected=purge_restore_rejected,
                  terminal_replay_identical=identical,
                  sibling_byte_identical=tree_digest(sibling) == sibling_before,
                  selected_root_final_exists=selected.exists(), tombstone_final_exists=tombstone.exists(),
                  lifecycle_state=terminal.get("lifecycle_state"),
                  provider_auth_state=terminal.get("provider_auth_state"),
                  ready=terminal.get("ready"), integrity_check=integrity,
                  foreign_key_count=len(foreign))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--operation", choices=tuple(BOUNDARIES), required=True)
    parser.add_argument("--boundary", required=True)
    parser.add_argument("--files", type=int, default=20000)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    if not 1000 <= args.files <= 50000:
        parser.error("bounded file count must be between 1000 and 50000")
    result = qualify(args.root.resolve(), args.wheel, args.python.resolve(strict=True),
                     args.operation, args.boundary, args.files)
    args.evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

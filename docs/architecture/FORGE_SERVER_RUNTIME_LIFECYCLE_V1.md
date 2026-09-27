# Forge Server Runtime installed lifecycle V1

**Assignment:** `L2-FORGE-SERVER-RUNTIME-LIFECYCLE-V1-20260927`

**Owning product:** Forge

**Contract:** `forge-server-runtime-lifecycle/v1`
**Baseline:** frozen `FORGE_SERVER_RUNTIME_DEPLOYMENT_CONTRACT` and `forge-installed-update/v1`

## Boundary

Forge publishes two lifecycle decisions that a deployment owner may consume:

1. a read-only decision for one exact installed artifact and one exact staged candidate;
2. a durable uninstall dispatcher for one exact, already-quiesced Forge Server Runtime instance.

These are Forge product decisions. A caller must not infer `UPDATE_AVAILABLE` from version ordering or delete a Forge data root itself. Forge Platform remains responsible for service-account provisioning, LaunchDaemon definition/removal, immutable runtime-slot layout, artifact staging and service stop/start choreography. Engineering Platform and Workspace are not participants in this contract.

## Read-only update assessment

Packaged command:

```bash
forge --data-root <absolute-instance-root> server update-assess \
  --runtime-id <opaque-runtime-id> \
  --installation-id <opaque-installation-id> \
  --installed-version <version> \
  --installed-source <40-hex-source> \
  --installed-artifact-digest sha256:<64-hex> \
  --candidate-version <version> \
  --candidate-source <40-hex-source> \
  --candidate-wheel <absolute-staged-wheel> \
  --candidate-artifact-digest sha256:<64-hex>
```

The command:

- validates the exact wheel bytes, filename, package metadata, member paths and complete `RECORD` binding without importing candidate code;
- reads the instance marker and a bounded SQLite snapshot without changing the selected data root;
- binds opaque runtime and installation identities, installed inventory version, current schema and storage integrity;
- returns `UPDATE_AVAILABLE` only for an explicitly supported `(installed version, candidate version, schema)` transition;
- returns `UP_TO_DATE` only when version, source revision and artifact digest all match;
- returns `INCOMPATIBLE` for a fully observed but unsupported transition;
- returns `UNKNOWN` for malformed, missing, changing or identity-inconsistent evidence.

`UNKNOWN` and `INCOMPATIBLE` never authorize mutation. The response contains the selected installation, candidate correlation, reason codes, evidence digests, `mutating: false`, and an `assessment_digest`. It contains no credential or ambient-home information.

The assessment may use private scratch storage to read a consistent WAL-backed snapshot. It must leave every selected instance and candidate artifact byte unchanged and must reject a source snapshot that changes during the read.

## Durable uninstall dispatcher

Packaged commands:

```bash
forge --data-root <absolute-instance-root> server uninstall \
  --operation-id <opaque-operation-id> \
  --instances-root <absolute-managed-instances-root> \
  --instance-id <opaque-instance-id> \
  --runtime-id <same-opaque-runtime-id> \
  --installation-id <opaque-installation-id>

forge server uninstall-status \
  --operation-id <same-operation-id> \
  --instances-root <same-managed-instances-root> \
  --instance-id <same-instance-id>
```

The dispatcher requires the data root to be one direct child of the explicit managed instances root. `instance-id` and `runtime-id` must be identical, and the marker/database must independently bind that identity plus `installation-id`. Symbolic-link path components, symbolic links or special entries below the instance, identity drift, unsupported schema, integrity failure and concurrent lifecycle activity fail closed.

Before detaching the root, the dispatcher owns the Server, controller, runtime-mutation and bootstrap locks and proves:

- no Server process owns the instance lease;
- dispatcher state is absent/fresh or durably `IDLE`;
- every Mission and scheduler submission is terminal or explicitly paused;
- provider-generation permits are terminal;
- planning queues are empty;
- operational-reset maintenance is idle.

The durable phases are:

```text
PREPARED -> VERIFIED -> DETACHED -> REMOVED -> COMPLETE
```

State and the terminal receipt live at a product-derived path under:

```text
<instances-root>/.forge-server-runtime-lifecycle/
  <sha256(instance-id)>/operations/<operation-id>/
```

They are therefore outside the removable instance root. Detach is one atomic same-filesystem rename into the operation-owned quarantine. After a crash, the same request reconciles the source/quarantine pair and continues; it never adopts a different root. A completed replay returns the same receipt and refuses a recreated target. Reusing an operation ID with changed request fields fails closed.

The terminal receipt states:

- mutable instance data: `REMOVED`;
- service definition: `DEPLOYMENT_OWNER`;
- immutable runtime slots: `PRESERVED`.

That ownership split is intentional. The dispatcher does not unload or delete a LaunchDaemon and does not remove a shared/versioned Forge wheel or interpreter. The deployment owner may perform those actions only through its own frozen route after it has consumed the exact Forge receipt.

## Qualification

Source and fresh-installed-wheel tests must cover:

- exact `UPDATE_AVAILABLE`, `UP_TO_DATE`, `INCOMPATIBLE` and fail-closed `UNKNOWN` decisions;
- byte-for-byte read-only assessment behavior;
- corrupt/ambiguous wheel rejection;
- wrong runtime/installation identity rejection;
- live Server lock, active dispatcher/Mission and unsafe filesystem rejection;
- exact-instance deletion with a sibling instance preserved;
- interruption after verification, detach and removal plus same-operation recovery;
- idempotent terminal replay and operation-ID rebinding rejection;
- installed-distribution execution before and after registry publication.

No qualification may contact production EP, a production provider or mutate Forge Platform, EP or Workspace.

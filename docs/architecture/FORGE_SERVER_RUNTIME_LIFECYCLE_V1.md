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
  --installation-id <opaque-installation-id> \
  --installed-version <exact-selected-version> \
  --installed-source <exact-40-char-source-revision> \
  --installed-artifact-digest <sha256:...>

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


## Product-owned preserved instance lifecycle extension

**Assignment:** `L2-PRODUCT-PRESERVE-PURGE-RESTORE-V1-20260928`

**Extension contract:** `forge-server-instance-lifecycle/v1`

This extension is additive. The existing `server uninstall` /
`server uninstall-status` contract above remains destructive and unchanged.
A caller that needs data preservation must use the explicit preserved-instance
commands and must not reinterpret an old uninstall receipt.

Packaged commands:

```bash
forge --data-root <absolute-instance-root> server preserve \
  --operation-id <opaque-operation-id> \
  --instances-root <absolute-managed-instances-root> \
  --instance-id <opaque-instance-id> \
  --runtime-id <same-opaque-runtime-id> \
  --installation-id <opaque-installation-id>

forge --data-root <absolute-instance-root> server restore \
  --operation-id <opaque-operation-id> \
  --preserve-operation-id <exact-preserve-operation-id> \
  --instances-root <absolute-managed-instances-root> \
  --instance-id <same-opaque-instance-id> \
  --runtime-id <same-opaque-runtime-id> \
  --installation-id <same-opaque-installation-id> \
  --installed-version <same-exact-selected-version> \
  --installed-source <same-exact-source-revision> \
  --installed-artifact-digest <same-sha256:...>

forge --data-root <absolute-instance-root> server purge <same exact-instance arguments>
forge server lifecycle-status --operation-id <id> --instances-root <root> --instance-id <id>
```

### PRESERVE

Forge first proves the same identity, integrity and quiescence requirements used
by destructive uninstall, then proves exclusive filesystem ownership before
hashing every regular byte in the exact instance tree. The selected root and
every traversed mutable entry must not be group/world writable; regular files
must have exactly one hardlink; symbolic links and special entries remain
invalid. The data root is not detached or deleted. Durable evidence lives
under the product lifecycle control root outside mutable instance data.

Terminal evidence expresses at least:

```text
lifecycle_state = UNINSTALLED_DATA_PRESERVED
instance_identity = PRESERVED
mutable_instance_data = PRESERVED
restorable = true
service_state = REMOVED_OR_INACTIVE
service_definition = DEPLOYMENT_OWNER
immutable_runtime_slots = PRESERVED
provider_auth_state = PRESERVED_REQUIRES_REVERIFICATION
```

The deployment owner remains responsible for the LaunchDaemon and immutable
runtime layout. Forge's receipt proves that the selected data/config belongs to
the same quiescent product instance; it does not claim that an external service
definition was deleted.

### PURGE

`server purge` is the explicit product-owned permanent lifecycle projection.
It delegates the actual mutable-data deletion to the existing destructive V1
uninstall dispatcher and persists a separate purge tombstone only after that
dispatcher is terminal. This preserves legacy uninstall command and receipt
meaning while making `lifecycle_state = PURGED` and `restorable = false`
machine-readable.

A crash after destructive uninstall but before the purge projection is recovered
by the same operation ID. The purge tombstone blocks later restore from any
older preserve receipt for that instance identity. It does not delete shared
immutable runtime slots or deployment-owned service definitions.

### RESTORE

Restore names one exact prior preserve operation. Forge rejects missing,
foreign, tampered or purged evidence and revalidates the same runtime and
installation identities, schema/integrity/quiescence evidence, and the complete
preserved tree digest. It never creates a replacement identity and never
initializes a new data root over preserved state.

Because the macOS service definition remains deployment-owner state, Forge
terminal restore evidence is a product admission for reinstall/activation, not
a LaunchDaemon mutation:

```text
lifecycle_state = RESTORE_VALIDATED
instance_identity = PRESERVED
mutable_instance_data = PRESERVED
service_state = DEPLOYMENT_OWNER_REINSTALL_REQUIRED
provider_auth_state = PRESERVED_REQUIRES_REVERIFICATION
ready = false
```

Provider context/config/auth bytes may be preserved only as product-owned
instance data. Restore never promotes them to `VERIFIED`; any consumer must
complete the normal provider verification/readiness route before treating the
restored service as ready.

### Extension qualification

In addition to the original V1 matrix, qualification covers exact-instance
preserve/restore, byte-level tamper rejection, permanent purge invalidation,
interruption/replay for all three operations, operation-ID rebinding rejection,
symlink/hardlink/special-entry rejection, group/world-writable root/tree
rejection, foreign-root rejection, sibling-instance non-interference and
packaged CLI execution. Product qualification uses isolated fixtures only and performs
no Forge Platform, Engineering Platform, Workspace or production mutation.

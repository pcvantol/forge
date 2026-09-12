# Canonical Forge data root

Installed Forge owns one mutable data root. On macOS its native default is
`$HOME/Library/Application Support/Forge Server`. The resolver uses, in order,
the CLI `--data-root`, `FORGE_DATA_ROOT`, then the platform-native default.
Resolution is side-effect free: import, help, version, status, package builds,
and resource inspection never create the root.

`forge server init` is the explicit creation boundary. It creates a private
root and validates the SQLite store, instance marker, and subdirectories:

```text
Forge Server/
  forge.db       Forge-owned planning and evidence metadata
  instance/      stable instance marker and local binding metadata
  artifacts/     Forge-produced durable artifacts
  journals/      recovery journals
  logs/          Forge operational logs
  backups/       operator-controlled backups
  cache/         disposable Forge cache
  locks/         same-root mutation locks
```

The root is an installation identity, not a checkout, Python environment,
wheel, current directory, or Git identity. The instance ID persists while the
same root is reused; a distinct root has a distinct instance. Package files and
resources are immutable. Forge never writes runtime state to site-packages,
wheel metadata, the current directory, a checkout, `.git`, or
`.git/forge-runtime`.

`.git/forge-runtime` is **LEGACY_BOOTSTRAP_RUNTIME**. Installed Forge neither
discovers nor migrates it, including on help, version, status, start, or init.
Any future import is a separately documented, explicit operator action.

Forge storage remains separate from the Engineering Platform. Forge records
only the configured peer binding and receipt/readback identities; it reaches
the Execution Host through the versioned HTTP contract and never reads or
writes a peer database, queue, run directory, telemetry, or credentials.
Status output is JSON and exposes the version, resolved root, initialized
state, instance ID when present, schema, runtime status, and peer status--never
secrets. Unknown newer schemas, a marked root without `forge.db`, integrity
failure, or a competing mutating lock fail closed.

Operational backup and recovery are root-scoped: take a SQLite-consistent copy
into `backups/`, retain the corresponding `instance/` marker, then restore to
an explicitly selected data root and validate before use. Do not copy a root
over a running instance.

## Forge CENTRAL and managed Console services

The future Console calls this existing authority **Forge CENTRAL**. It remains
Forge-owned `forge.db` plus its existing durable directories, not EP's CENTRAL
or a new shared database. The [hosting contract](FORGE_CONSOLE_HOSTING_AND_CENTRAL_V1.md)
and [roadmap](../roadmap/FORGE_CONSOLE_HOSTING_V1.md) require an explicit same-root
binding for the installed Server and its Console/relay services. Console and
relay are API/access adapters, not direct SQL writers or separate state stores.
System-service startup must use the installation's pinned data root, never a
new default inferred from a different service account's HOME. Relocation must
repoint every owned root reference and prove same-instance reopen after reboot.

This clarification changes no filename, resolver precedence, schema, default
path, installed identity or existing state. Export/import/relocate/VACUUM remain
the separately qualified product operations defined in the
[configuration contract](FORGE_SERVER_CONFIGURATION_AND_DATA_OPERATIONS_V1.md).

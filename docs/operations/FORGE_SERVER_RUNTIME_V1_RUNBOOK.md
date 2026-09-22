# Forge Server Runtime V1 operator / qualification runbook

This runbook is for the Forge product surface delivered by `L1-FORGE-SERVER-RUNTIME-V1-20260922`. It is not a macOS installer or launchd runbook.

## 1. Existing-instance prerequisite

`server run` never creates an instance.

```bash
forge --data-root /absolute/forge-instance server status
```

If the instance is absent, initialize it explicitly with the existing product-owned init operation before any Server deployment. The future Universal macOS Installer owns that provisioning decision.

## 2. Bind instance-owned Codex context

Forge stores paths/identity only. Complete provider login outside Forge using the future Forge Platform fan-out ceremony, then bind the resulting component-owned paths:

```bash
forge --data-root /absolute/forge-instance server provider-context configure \
  --provider-type CODEX_CLI_CHATGPT_SESSION \
  --executable-path /absolute/component/codex \
  --provider-home /absolute/instance/provider-home \
  --provider-config-home /absolute/instance/codex-home
```

Use `server provider-context show` for safe readback. Do not copy another instance's context.

## 3. Configure the EP peer

Use the existing `execution-host configure` product operation. The endpoint must remain the supported authenticated HTTP boundary. Never substitute EP CLI calls, database reads or shared filesystem access.

Run:

```bash
forge --data-root /absolute/forge-instance execution-host preflight
```

before expecting Server scheduler readiness.

## 4. Start foreground Server

Provision a private bearer file and run:

```bash
forge --data-root /absolute/forge-instance server run \
  --credential-file /absolute/private/server-api-token \
  --host 127.0.0.1 \
  --port 8765
```

The process remains in the foreground. SIGTERM/SIGINT requests clean shutdown.

## 5. Required readbacks

Authenticated requests:

```text
GET /v1/instance
GET /v1/version
GET /v1/health
GET /v1/readiness
GET /v1/provider-context
GET /v1/execution-host/preflight
```

`health=PASS` does not imply `readiness=PASS`. Readiness includes instance-owned Codex context, peer configuration and scheduler state.

## 6. Multi-instance qualification

Create at least two distinct initialized data roots and two distinct listener ports. Bind separate provider HOME/config roots. Start both Server processes concurrently.

PASS requires:

- different opaque instance IDs;
- different roots, Server locks and ports;
- each API reports only its own provider/peer/runtime state;
- one instance lock never blocks the other;
- no evidence/correlation/log file is visible through the other instance;
- stopping/restarting one instance does not alter the other.

## 7. EP simulator qualification

Use `EpSimulatorState` + `EpSimulatorServer`. Point the normal `EngineeringPlatformHttpExecutionHost` configuration at the simulator loopback URL with synthetic credentials.

Do not patch the Mission engine or replace the Forge HTTP client.

Exercise the scenario matrix in the architecture contract, including retained simulator state across EP restart and persisted Forge bindings across Forge restart.

## 8. Failure/restart safety

A killed/restarted Server may leave only durable product state. On restart the supervisor resumes existing resumable Mission state through `InstalledDynamicMissionRuntime` and `ForgeRuntimeService`.

A second Server on the **same** data root must fail its Server lease. A Server on a different root remains valid.

## 9. Production exclusion for this assignment

A release created by this assignment may be published through the normal Forge flow, but it is not automatically installed or activated in production CENTRAL. No Mission-3/reset/T0 action belongs to this runbook.

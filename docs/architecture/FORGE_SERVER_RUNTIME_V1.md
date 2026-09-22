# Forge Server Runtime V1

**Assignment:** `L1-FORGE-SERVER-RUNTIME-V1-20260922`  
**Owning product:** Forge  
**Cross-product deployment context:** Forge Platform PR #67 / ADR-0007 and Universal macOS Installer contracts, read-only  
**Runtime implementation qualification:** pending exact-head protected evidence until the owning delivery completes

## Boundary

Forge Server is the long-running product composition of existing Forge application/runtime services. It owns no Engineering Platform behavior and it is not an EP proxy. Forge still reaches EP only with the existing authenticated `EngineeringPlatformHttpExecutionHost` HTTP client.

The Server refuses to invent an instance. `server run` requires an explicitly selected, already initialized, current-schema data root. Runtime identity is the existing opaque instance ID. Locks, database, logs, provider context, peer binding and endpoints are scoped to that data root. There is no machine-global Server singleton.

The V1 network listener is deliberately IPv4 loopback-only. Remote human access belongs to the separately planned Forge relay/Tailnet surface. This keeps the Server transport production-bounded without inventing an unaudited public-TLS edge.

## Process composition

```text
system service / terminal supervisor
        |
        +-- forge --data-root <root> server run ...
                |
                +-- one per-instance Server process lease
                +-- main-thread durable Mission resume supervisor
                |      |
                |      +-- InstalledDynamicMissionRuntime
                |      +-- ForgeRuntimeService mutation lock
                |      +-- existing planner / Mission / EP HTTP client
                |
                +-- bounded authenticated HTTP thread pool
                       |
                       +-- thin Server API adapter
                       +-- existing application/governance services
```

The supervisor may resume only persisted resumable Missions. It never selects or starts a new approved Mission by itself. A governed controller start is an explicit API operation. After a process restart, the same persisted Mission/correlation is resumed by the existing Forge runtime composition.

SIGINT/SIGTERM request bounded foreground shutdown. The process does not fork, daemonize, require a terminal, start launchd, or rely on a source checkout.

## FORGE_SERVER_RUNTIME_DEPLOYMENT_CONTRACT = FROZEN

The following is the V1 installer/provisioner boundary. Changes require an explicit compatibility decision.

### Product executable and process model

Production entrypoint:

```bash
forge --data-root <absolute-instance-root> server run \
  --credential-file <absolute-private-bearer-file> \
  --host 127.0.0.1 \
  --port <instance-port> \
  --provider-id codex-chatgpt-session
```

- one foreground Server process per Forge instance;
- exactly one Server lease per data root at `locks/forge-server-runtime.lock`;
- multiple data roots may run concurrently on the same host;
- stdout/stderr remain supervisor-owned; secret-free Server lifecycle diagnostics are appended under the selected data root at `logs/server-runtime.jsonl`;
- exit 0 follows normal SIGINT/SIGTERM shutdown; startup/configuration failures use the existing Forge CLI failure contract;
- no implicit initialization or schema migration is permitted by `server run`.

### Data root and stable identity

The installer must provision/select an explicit data root before Server start. Existing `forge --data-root ... server init` remains the product-owned initialization operation. The Server requires:

- `instance/runtime-instance.json` with the opaque Forge instance ID;
- `forge.db` at the current supported runtime schema;
- identity agreement between marker and database metadata;
- integrity PASS before startup.

Human instance names are external labels only. The opaque instance ID is authoritative.

### Multi-instance rules

Every managed Forge instance has its own:

- data root and database;
- instance marker;
- Server/runtime/mutation/update locks;
- listener port;
- logs and artifacts;
- provider-context documents;
- EP peer binding;
- bearer credential file;
- health/readiness/lifecycle.

No Forge Server V1 path uses a machine-global mutable runtime/configuration directory or a machine-global product lock. A valid second instance must never be blocked by another instance's Server lease.

### HTTP listener and authentication

- listener: explicit `127.0.0.1:<port>`;
- authentication: private bearer credential supplied by absolute file path; the credential itself is never returned by an API;
- API version: `/v1`;
- canonical route contract: `forge/api/server-openapi-v1.json`;
- exhaustive operator/qualification collection: `forge/api/server-postman-v1.json`;
- code/OpenAPI/Postman drift is a test failure.

Remote relay/TLS termination is not implemented by this slice.

### Health, readiness and identity

Required readbacks:

- `GET /v1/instance` — opaque instance identity, listener and safe deployment bindings;
- `GET /v1/health` — existing installed aggregate health;
- `GET /v1/readiness` — provider-context, configured EP peer and Server scheduler readiness;
- `GET /v1/version` — Forge product version, runtime schema and instance identity;
- `GET /v1/provider-context` — secret-free instance-owned provider context;
- `GET /v1/execution-host/preflight` — existing authenticated Forge→EP compatibility preflight.

Readiness is not health: a Server can stay up and expose diagnostics while provider or EP readiness is unavailable.

### Instance-owned provider execution context

Product-owned configuration operation:

```bash
forge --data-root <root> server provider-context configure \
  --provider-id codex-chatgpt-session \
  --provider-type CODEX_CLI_CHATGPT_SESSION \
  --executable-path <absolute-component-owned-codex> \
  --provider-home <absolute-instance-provider-home> \
  --provider-config-home <absolute-instance-codex-home>
```

Guarded replacement additionally requires the current configuration digest.

The document contains **no token/session secret material**. Forge binds it to the opaque Forge instance ID and adds its digest to the planning-provider invocation policy. In instance-owned mode Codex receives:

- explicit executable path;
- `HOME=<provider_home>`;
- `CODEX_HOME=<provider_config_home>`;
- deterministic `PATH=<executable-dir>:/usr/bin:/bin`;
- the instance ID as non-secret process identity.

Ambient installer-user `HOME`, interactive login state, user PATH, another Forge instance's context and EP's provider runtime are not inherited. Forge does not parse Codex authentication/session files. Forge Platform later owns the interactive login/fan-out ceremony that populates the component-owned context.

Legacy external-session invocation without an instance context remains compatible for existing interactive CLI consumers. **Forge Server readiness does not:** it requires the instance-owned context before the background scheduler is ready.

### Forge→EP configuration

The existing `execution-host configure/show/preflight` product operations remain authoritative. The Server API exposes the same configuration/preflight application service; it does not proxy arbitrary EP routes. EP credentials continue through the existing typed secret-reference route. A future system service deployment must provision that reference so it resolves non-interactively for the service account.

### Mission governance/controller surface

The Server HTTP adapter calls the same Mission document/governance/runtime services used by the CLI. It exposes:

- inspect;
- Business approval;
- Architecture approval;
- admission;
- Mission status/evidence lineage;
- one governed controller start;
- durable reopen/resume.

The persistent supervisor only resumes already-resumable durable state. It never creates a Mission, governance approval, Action or provider request by itself.

### Filesystem ownership

A future system service account must have:

- read/write ownership of its selected mutable data root;
- read/execute access to the immutable Forge installation and selected Codex executable;
- read/write access to that instance's provider HOME/config context as required by Codex;
- read access to its private API credential file;
- access to the separately provisioned EP credential reference.

No installer-user HOME is part of the deployment contract.

Mutable paths are confined to the instance data root and explicitly provisioned provider homes/config homes. Immutable paths are the qualified Forge distribution/venv, Server executable surface and provider executable. Forge Platform owns their eventual installation layout.

### Start/stop/restart semantics

- start: invoke the foreground command against one explicit existing instance;
- stop: SIGTERM/SIGINT, wait for clean process termination;
- restart: start the same command/configuration after termination;
- crash/restart: durable Mission/controller/EP correlation state is recovered from Forge-owned storage;
- duplicate Server start on the same instance: fail closed through the per-root Server lease;
- a different instance: allowed concurrently.

The process itself never edits launchd definitions. Forge Platform owns LaunchDaemon provisioning, quiesce/restart choreography and update orchestration.

### Installation/update integration

The normal Forge wheel remains the distributable unit. The external owning Forge updater remains the only update path; Forge Runtime does not self-update.

Before an installed update Forge Platform must use the product-owned readbacks to identify the exact instance, stop/quiesce the Server via the service supervisor, and invoke the qualified updater. It must not copy or rewrite Forge databases or instance IDs.

### Required Forge-owned provisioner operations/readbacks

For future Forge Platform consumption:

1. `server init` — explicit instance creation only;
2. `server provider-context configure/show` — secret-free component context binding/readback;
3. `execution-host configure/show/preflight` — Forge-owned EP peer binding;
4. `server run` — foreground service process;
5. `/v1/instance`, `/v1/version`, `/v1/health`, `/v1/readiness` — installed identity/health/readiness;
6. normal external Forge updater — qualified version transition.

Provider login/fan-out, service account creation, filesystem provisioning and launchd definitions remain Forge Platform responsibilities.

## EP simulator

`forge.ep_simulator` is a Forge-development component at the **real EP HTTP seam**. It owns no Mission/planning semantics.

Its restart-retainable ledger implements authenticated compatibility/readiness, idempotent submission receipts, polling, terminal artifacts and scenario-controlled transport. It can produce:

| Scenario | Simulator mechanism |
| --- | --- |
| successful Action / terminal evidence / delivery revision / exact baseline | strict v1.4 terminal builder |
| wrong baseline / stale or conflicting evidence / wrong Mission/Action/correlation | terminal copy + bounded negative mutation |
| dirty workspace / lease conflict | managed-workspace readiness controls |
| provider failure | FAILED + no-assurance terminal |
| validation failure | BLOCKED + failed assurance terminal |
| Quality block | BLOCKED + Quality FAIL |
| Security block | BLOCKED + Security FAIL |
| delivery failure | FAILED with no delivered revision |
| HTTP failure | stage-specific 4xx/5xx |
| timeout | deterministic response delay with bounded client timeout |
| connection loss | stage-specific socket close |
| delayed terminal evidence | terminal-after-N-readbacks |
| duplicate response/event | idempotent repeated POST/readback |
| EP restart/reconnect | reuse the same `EpSimulatorState` with a new listener |
| Forge restart during polling | reopen the persisted Forge DB/client binding against the retained simulator state |
| idempotent reconciliation | same submission/terminal evidence; no second accepted request |

Qualification code may retain/corrupt a copy of terminal documents to prove fail-closed consumption; it must never reach into Forge Mission state to manufacture success.

## Qualification invariants

The owning tests must prove at least:

```text
P1
<
Action A created
<
A terminal evidence accepted
<
P2
<
Action B created
```

and also prove that a genuinely sufficient Action A can complete without an artificial Action B.

Crash/restart, duplicate EP responses, delayed/stale/conflicting evidence, concurrent Server writer, duplicate start, interrupted polling and process termination must preserve:

- no duplicate logical Action;
- no duplicate EP submission;
- no ghost controller/execution projection;
- durable Repository Truth and accepted delivery revision;
- deterministic reconciliation.

## Explicit non-goals

This contract does **not**:

- install a LaunchDaemon;
- implement Forge Platform provider-login fan-out;
- mutate Engineering Platform;
- use a peer CLI/shared database/filesystem shortcut;
- install or activate a new Forge release on production CENTRAL;
- run Mission 3, T0 or a production reset;
- establish cryptographic identity for EP beyond the existing authenticated peer contract.

# Installation pairing v1 — source candidate

The installer connects one Forge runtime to one EP instance before any project
exists. Workspace selects or creates a project afterward through existing,
separate audited project authority. No installer-selected default project is
created. Project execution remains denied until its own scope is authorized.

Forge persists only an installation binding and explicit Keychain reference in
its canonical Runtime Database. The binding is independent of
`execution_host_peer_configuration`; it is neither a partial project binding
nor an input to the execution adapter. Configuration derives the actual Forge
runtime identity and requires the existing trusted macOS operator binding.
Repeated exact configuration is idempotent. A changed operation or target is
rejected pending separate reviewed replacement; it cannot rewrite the prior
binding. Normal product reset preserves installation configuration.

The `installation-peer` CLI supports configure, show and preflight. Equivalent
Server routes use existing instance-admin authentication. No request can supply
credential material, a project/repository scope or an operator/service UID.
The existing Keychain resolver supplies the bearer only at the HTTP boundary.

Installation preflight uses EP's `installation-compatibility` contract, checking
exact EP instance, Forge runtime, consumer, binding and readback-only purpose.
It refuses redirects and cleartext non-loopback transport. Connectivity never
sets execution-ready. `readiness/installation` combines provider and scheduler
readiness with authenticated installation connectivity and always reports
project_authorized=false and execution_ready=false. Existing project readiness
and execution contracts retain their stricter meaning.

New product versions, owning protected review and actual installer qualification
remain required. Source tests, including the explicit producer/consumer HTTP
contract test, do not qualify an installed or published product.

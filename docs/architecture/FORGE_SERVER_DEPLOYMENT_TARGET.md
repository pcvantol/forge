# Forge Server deployment and peer-binding target

**Status:** Canonical target architecture; implementation, migration and qualification remain separately governed.

Forge Server is a headless installed service. Its central runtime-storage root is outside every Git/source checkout and contains the Forge-owned SQL database plus durable files, dispatch/correlation journals, artifacts/references, logs, backups and cache. It exposes a versioned HTTP API above interface-neutral Forge application services. The Forge CLI remains an administration, qualification and recovery client of those services; Forge has no GUI requirement. On macOS its installed service is launchd-managed.

The current repository-bound `.git/forge-runtime` placement is historical/bootstrap-compatible runtime placement, not the target authority. Migration/relocation must preserve the existing Forge instance ID, grants, Missions, budgets, requests, cursors and evidence, use a product-owned quiesced cutover with backup/integrity checks, and leave no dual writer or old-location fallback writer. A source checkout must never create a replacement runtime because it cannot find the installed one.

Forge binds to EP and Workspace only through their versioned authenticated APIs. It never reads their databases or controls their services. The shared discovery/pairing vocabulary and descriptor are defined by Forge Platform's [contract](https://github.com/pcvantol/forge-platform/blob/main/docs/architecture/INSTANCE_DISCOVERY_AND_PAIRING_CONTRACT.md): LAN DNS-SD/mDNS and configured/unicast/tailnet endpoints locate candidates, while authenticated pairing pins peer product, stable instance ID, identity fingerprint, endpoint/version/capability set and scope in Forge-owned storage. Discovery is not authorization; a binding never silently retargets to a discovered instance.

## HTTP API implementation requirement

Forge does not yet expose its own HTTP server. When that implementation is
introduced, its versioned OpenAPI document is the canonical public transport
contract and must describe every implemented Forge-owned route, method,
authentication requirement, request/response/error envelope and version
behavior. The implementation must ship an exhaustive Postman collection
derived from that contract, covering every documented operation and its
declared authorization and error cases without embedding credentials.

CI must run the collection against an isolated Forge server state and fail on
any drift between the OpenAPI document, the routes actually exposed by that
server, and the Postman collection. A route may not be added, removed or
semantically changed without updating all three artifacts in the same change.
This requirement applies only to a future Forge-owned HTTP API; it neither
redefines the EP API nor makes Forge an EP proxy.

The autonomy canary requires only installed Forge/EP storage, stable identities, the existing versioned authenticated Forge→EP HTTP seam, a configured/pinned EP binding and restart recovery. Workspace UI, LAN discovery and universal-installer completion are post-canary productization and must not block that proof.

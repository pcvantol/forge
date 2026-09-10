# Planning-provider security configuration

`Forge::PLANNING_PROVIDER_SECURITY_CONFIGURATION_V1` is the Forge-specific
producer under the still-open shared requirement `FWV1-G011`. It does not
complete G011 and does not allocate EP or Workspace work.

Forge stores typed configuration, a version and named-operator provenance in
its Runtime Database. Provider adapters, models and project consumers have no
configuration mutation authority. There are exactly two authentication modes:

- `SECRET_REFERENCE` preserves the existing opaque `SecretReference` route.
  Secret material stays with the configured external/operator-owned secure
  store.
- `EXTERNAL_AUTHENTICATED_SESSION` is currently typed solely for
  `CODEX_CLI_CHATGPT_SESSION`. It persists the Codex executable path, optional
  model/profile, bounded invocation policy and adapter version, but never a
  secret reference or any login material.

The Codex CLI remains the owner of the ChatGPT sign-in and refresh session.
Forge does not inspect Codex authentication files, browser state, access
tokens, API keys or API-billing credentials. The existing OpenAI Responses
adapter remains an independent optional `SECRET_REFERENCE` provider route.

Configuration and audit projections are redacted. A reference that is missing,
revoked, rotated-invalid, invalid or whose store is unavailable is not ready
and fails closed; no fallback secret is selected. An external session begins
`UNVERIFIED` and is ready only after its provider-owned non-generating
readiness check confirms an executable, supported version and ChatGPT login.
No unverified selected model is substituted. The only resulting producer gate
is `Forge::PLANNING_PROVIDER_SECURITY_CONFIGURATION_V1::QUALIFIED`.

Clean installations start `NOT_CONFIGURED`; this component implements neither
a vault nor an EP or Workspace capability. A separate bounded Codex adapter
can use the session configuration only through read-only, strict-schema Action
Derivation. Its preflight does not generate a proposal.

# Planning-provider security configuration

`Forge::PLANNING_PROVIDER_SECURITY_CONFIGURATION_V1` is the Forge-specific
producer under the still-open shared requirement `FWV1-G011`. It does not
complete G011 and does not allocate EP or Workspace work.

Forge stores a typed, opaque `SecretReference`, configuration version and
named-operator provenance in its Runtime Database. Secret material stays with
the configured external/operator-owned secure store. Provider adapters, models
and project consumers have no configuration mutation authority.

Configuration and audit projections are redacted. A reference that is missing,
revoked, rotated-invalid, invalid or whose store is unavailable is not ready
and fails closed; no fallback secret is selected. The only resulting producer
gate is `Forge::PLANNING_PROVIDER_SECURITY_CONFIGURATION_V1::QUALIFIED`.

Clean installations start `NOT_CONFIGURED`; this component neither invokes a
provider nor implements a vault, provider adapter, Action Derivation, EP or
Workspace capability.

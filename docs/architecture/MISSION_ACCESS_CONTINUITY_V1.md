# Mission approval access continuity V1

Selected source correction: `L3-MISSION-ACCESS-CONTINUITY-V1-20261009` (L3 r44).
This extends the existing chat-first Mission HTTP/CLI producer without changing
its response schema or original operation identities.

Every request still requires current ACTIVE, unexpired scoped advisory access,
current owner identity/project binding and the real G001 signer/profile. Access
replacement is never a new Business or Architecture scope approval.

For a turn admitted under another credential, continuity requires exact semantic
identity under the closed `mission-access-continuity/v1` comparison basis:
principal, instance/project/repository, exact conversation set, signer/profile,
full planning profiles (effects/components/constraints/capabilities/disciplines/
human gates/action ceilings), declared Mission/turn bounds and retained minimum
allowances. Credential ID, token digest and expiry are excluded from semantic
identity. Canonical JSON digests preserve types; no boolean/numeric coercion.
The original credential must exist and be nonrevoked. Expiry may remain historical
provenance; it never grants active access.

Continuity is restricted to actual COMPLETE compound operations. The original
setup digest, admitted turn identities/result/context, registration receipt and
immutable intent, exact current Candidate subject, both checked canonical
decision receipts, validated governance envelope and real allocation/admission
must agree. The recomputed package must match the exact original frozen bytes.
The original closed confirmation request must exactly match its proposal/source
and true confirmation. Actual stored Mission definition and full admission
contract must match that original preview/envelope, including planning, both
decision IDs, candidate and installation. Lifecycle allocation lineage and the
runtime allocation keyed by that canonical envelope must resolve the same ID.
Only then may the derived current context use the original configuration revision
for freshness comparison. Stored context/package/decision/operation/Mission IDs
and durable consumption are never rewritten.

The existing package, operation and catalog reads return the original lineage.
An exact confirmation replay of an existing complete operation remains zero-effect.
A replacement credential cannot register new operation aliases or finish partial
registration, decisions or admission. New model turns remain subject to retained
consumption limits. Current source/definition/provider/dependency/signer changes,
revocation and missing/corrupt provenance fail closed under the existing routes.
Original-authority generation and partial-effect recovery keep their existing
behavior; no scheduler, credential renewal endpoint or extra approval route is added.

The isolated regression matrix uses genuine HTTP/auth/governance/Intake stores
with only external OS/model/repository fixtures. Natural expiry, equal replacement,
restart, exhausted usage, partial effects and corruption are tested. Installed
qualification includes this matrix in the existing exact-wheel concept gate.

Existing operational credentials, authorization and retained L4 fixtures are
outside this source assignment. L4 remains on its selected Forge 2.11.0 pin;
adoption of the new producer requires a separately controlled handoff.

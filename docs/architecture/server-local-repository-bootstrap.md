# Server-local repository bootstrap

**Status: operational architecture clarification.** This document defines the
small, server-local provisioning step used to connect an already declared
repository to an installed Engineering Platform (EP) instance. It does not
create a Workspace programme, Agent programme, Mission, Action, execution
lease, consumer credential, or delivery claim.

## Identity and registration

The committed `.engineering-platform/repository.json` declaration owns the
logical repository identity for this bootstrap. EP CENTRAL must retain the
same normalized declaration contract, including the validation boundary.
The existing project and repository IDs are preserved; registration is not a
reason to delete and recreate records.

For Forge, the canonical declaration fixes `FORGE_PROJECT_ID = forge`,
`FORGE_AUTHORITY_REPOSITORY_ID = forge`, and `FORGE_REPOSITORY_ID = forge`.
It is the authoritative Forge-owned declaration consumed by EP
attachment/admission; it is not itself an EP attachment or admission record.

Workspace remains the product boundary for product identity and governance.
It is **not** a required identity issuer for this server-local bootstrap.
Likewise, an empty Agent-attachment list does not make an already registered
repository unexecutable or invalidate its declaration.

`ACTIVE` means that the CENTRAL registration exists. It does not mean that the
repository has a local checkout binding, a consumer credential, admission, an
execution authorization, or delivered work.

## Required independent facts

For every repository, record these facts separately:

1. **Declaration parity:** the committed declaration at the selected owning
   revision equals the normalized CENTRAL contract, including the real
   validation entrypoint.
2. **Local repository binding:** an explicit, clean checkout is bound through
   EP's server-local bind/resolve interface. Agent topology attachments are
   not evidence for this fact.
3. **Consumer authentication:** a scoped, active consumer registration and
   credential exist. This is not implied by either registration or binding.
4. **Execution authorization:** an admitted, in-scope Action has the required
   authorization and current qualification evidence.
5. **Installed execution evidence:** an installed EP instance has received,
   dispatched, and recorded the applicable execution evidence. `BOUND`,
   topology output, provider availability, and a green local validation alone
   are not execution evidence.

## Safe correction rule

When CENTRAL is stale, use a supported, audited EP operator correction that
is tied to the existing record and exact expected old contract. It must verify
the replacement committed declaration, preserve identity, reject unrelated
changes, be transactional and idempotent, retain old/new audit information,
and avoid rewriting existing run or evidence snapshots. Direct database
patches, reset, delete/recreate, or weakening declaration validation are not
permitted.

## Bootstrap boundary

This step intentionally does not start Workspace onboarding, Project Agents,
or an Agent topology programme. It proves only the installed provider route
and its stated preconditions. A later Forge-to-EP Action flow still requires
the distinct consumer-authentication, admission, authorization, dispatch and
evidence facts above.

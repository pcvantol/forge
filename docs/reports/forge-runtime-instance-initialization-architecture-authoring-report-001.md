# Forge Runtime Instance Initialization Architecture Authoring Report 001

## Decision

Forge now treats canonical Runtime Instance initialization as a single
repository-wide transaction. The Git-common registry is the one registration
authority, and the default database is durable Git-common metadata rather than
cleanup-prone `.forge` storage.

## Integrity boundaries

The transaction takes an inter-process lock before resolution, creation, and
registry registration. Immutable Runtime Identity now includes initialization
version and an optional repository UUID supplied by the host. Existing claims,
ambiguous candidates, registry mismatches, missing registered locations, and
identity or schema inconsistencies fail closed.

## Relationship boundaries

Runtime Bootstrap creates the empty instance; Runtime Database persists its
state; Runtime Recovery and Bootstrap Qualification consume only the resolved
instance; Repository Truth remains architectural authority; and Engineering
Platform retains Execution Evidence ownership.

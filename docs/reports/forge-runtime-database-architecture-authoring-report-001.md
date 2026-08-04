# Forge Runtime Database Architecture Authoring Report 001

## Architectural boundary

Forge has one canonical local Runtime Database boundary: `.forge/runtime.db`.
It is authoritative for Forge runtime artefacts, not for Repository Truth or
Execution Host state. The database is local-only and excluded from version
control.

## Ownership decision

| Owner | Canonical artefacts |
| --- | --- |
| Forge Runtime Database | Mission State, Planning State, Architecture Reviews, Mission Recommendations, Decision Evidence, Execution Receipts |
| Repository Truth | architectural source material and evidence references |
| Engineering Platform Execution Database | execution runtime, execution evidence, reports, telemetry |

Execution Receipts record only host, run ID, Engineering Report ID, correlation
identity, timestamp, and outcome. This preserves loose coupling and prevents Forge from duplicating
Engineering Platform evidence.

## Safety decision

Startup performs deterministic migration and fails closed if the schema is
newer than supported, metadata/version values disagree, a required table or
metadata field is absent, SQLite integrity fails, or any mission, review, or
stored execution receipt is invalid. Architecture Reviews, Mission
Recommendations, Decision Evidence, and Execution Receipts are append-only immutable records.

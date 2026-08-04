# Forge Runtime Database Architecture Authoring Report 001

## Architectural boundary

Forge has one canonical local Runtime Database boundary: `.forge/runtime.db`.
It is authoritative for Forge runtime artefacts, not for Repository Truth or
Execution Host state. The database is local-only and excluded from version
control.

## Ownership decision

| Owner | Canonical artefacts |
| --- | --- |
| Forge Runtime Database | Mission State, Planning State, Architecture Reviews, Mission Recommendations, Decision Evidence |
| Repository Truth | architectural source material and evidence references |
| Engineering Platform Execution Database | execution runtime, execution evidence, reports, telemetry |

Execution references record only host, run ID, correlation, timestamp, and
outcome. This preserves loose coupling and prevents Forge from duplicating
Engineering Platform evidence.

## Safety decision

Startup performs deterministic migration and fails closed if the schema is
newer than supported, metadata/version values disagree, a required table or
metadata field is absent, SQLite integrity fails, or any mission, review, or
stored execution reference is invalid. Architecture Reviews, Mission
Recommendations, and Decision Evidence are append-only immutable records.

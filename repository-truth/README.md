# Repository Truth

`repository-truth/decision-evidence.sqlite` is the canonical local store for immutable Forge Decision Evidence records. It is created by `forge.decision_evidence.DecisionEvidenceRepository`; this directory contains no generated decision records in source control.

Portfolio Intelligence receives Repository Truth through the immutable
`forge.repository_truth.RepositoryTruthSnapshot` contract. A snapshot contains
only declared, revision- and digest-pinned evidence pointers and can expose one
bounded `ReviewEvidence` pointer for Architecture Review. It never reads a
repository, copies evidence content, records runtime state, or recommends a
Mission.

See [Decision Evidence Framework](../docs/architecture/decision-evidence-framework.md).

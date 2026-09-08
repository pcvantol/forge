# Governed progression V1 roadmap and documentary DAG

Increment: `GOVERNED_PROGRESSION_AND_DELIVERY_AUTHORITY_V1`.
Owning semantics: [governed progression and delivery authority](../architecture/GOVERNED_PROGRESSION_AND_DELIVERY_AUTHORITY.md).
Parent: [policy governance roadmap](POLICY_GOVERNANCE_V1.md), itself routed by
the canonical [Forge roadmap](../../knowledge/bootstrap/10_ROADMAP.md).
Machine-readable index: [governed-progression-v1.json](governed-progression-v1.json).
This is not the executable bootstrap DAG, a Mission or runtime configuration.

| ID | Owning delivery | Depends on | Acceptance / status |
| --- | --- | --- | --- |
| GP-0 | Four product owners | none | This coordinated design; authoritative only on owning main |
| GP-F | Forge | GP-0 | PLANNED: scoped review cadence/overrides, requirement resolution, decision reconciliation, durable successor fence |
| GP-DC | Forge/EP/Platform contract consumers; project owns each declaration | GP-0 | PLANNED: versioned delivery target/environment/authority and evidence contract |
| GP-E | EP | GP-0 | PLANNED: bounded operation/decision enforcement and evidence adapter; no Mission planner or CD takeover |
| GP-Q | Forge + EP | GP-F, GP-E | PLANNED: cross-product progression/gate/identity/restart proof with isolated qualification targets |
| GP-WC | Workspace | GP-0 | PLANNED: review settings and local/external decision projection/command contract |
| GP-W | Workspace | GP-WC, GP-Q | PLANNED: real policy/decision UI; external live claims additionally consume GP-X evidence |
| GP-X | Forge + EP integration, existing target owner retains authority | GP-Q, GP-DC | PLANNED: one approved real external pipeline, no duplicate gate/side effect, exact promotion/receipt evidence |
| GP-P | Forge Platform | GP-X | PLANNED: delivery-authority-aware composition for deployments using an external owner; existing artifact/install qualification also required |

```text
GP-0 -> GP-F --+
GP-0 -> GP-E --+-> GP-Q --+-> GP-X -> GP-P
GP-0 -> GP-DC -----------+
GP-0 -> GP-WC --+        |
GP-Q ----------+-> GP-W  |  (external live view consumes GP-X)
```

The table/JSON define AND-dependencies. They do not allocate another repository's
work or imply an external organization's approval. GP-DC ownership refers to
consumer contract implementation, not ownership of project delivery policy.
GP-E/GP-F reuse the necessary POL-E/POL-F semantics; requiring all future policy
administration is not a hidden dependency. GP-P supplements applicable POL-P,
VR-Q and qualified artifacts where those capabilities are used; it does not
make every local installation depend on an external CD pipeline.

The first serial dynamic Mission canary requires the actual selected Mission's
progression/authorization seams only. Rich Workspace UI, external CD, App Store,
PROD deployment, generalized parallelism and universal installer completion are
not newly inserted first-canary gates. Proof of one continuous profile is not
proof of all future configurable human-review profiles.

No existing F/L/POL/VR nodes are renumbered or marked complete. Adoption into a
live programme uses its separate authority/staleness reconciliation without
resetting budgets or extending grants. All implementation nodes remain PLANNED.

Documentation acceptance: four owning boundaries agree; canonical entrypoints
route to this scoped design; graph IDs/dependencies are valid and acyclic; only
Markdown and documentary DAG JSON change. No implementation, runtime, package
version, workflow, external CD configuration or credential change is implied.

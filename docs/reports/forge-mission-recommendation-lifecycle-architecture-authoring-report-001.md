# Forge Mission Recommendation Lifecycle Architecture Authoring Report 001

## Decision

The Mission Recommendation Lifecycle is now the canonical Generation 2
governance lifecycle. It separates advisory Portfolio Intelligence output,
Business decision, Architecture decision, mutable candidate refinement, Forge
allocation, operational Runtime, and historical learning.

## Authoring result

- `RecommendationLifecycleStore` is outside Runtime and has a closed,
  deterministic status map.
- Recommendations, transitions, allocations, and Decision Evidence are
  append-only; candidates freeze at allocation.
- Allocation requires recorded Business and Architecture approval evidence and
  calls a Forge-owned Mission-ID allocator only at that point.
- Runtime is the allocated-Mission operational boundary and retains references,
  not advisory recommendation state.

## Verification

Focused lifecycle regression tests cover approval gating, immutable evidence,
candidate freezing, completion evidence, rejection history, and invalid
transitions. The complete regression suite and diff validation are recorded by
the bounded engineering transaction.

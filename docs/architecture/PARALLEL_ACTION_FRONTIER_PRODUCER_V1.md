# Parallel Action graph/frontier producer V1

This is a bounded `PA-F0` producer and read-only `PA-F2` projection subset. It
does not qualify the `PA-F1/F2/F3/FQ` runtime nodes or change the serial
Mission-3 execution path. Forge remains responsible for graph interpretation;
EP owns host admission, capacity, execution and evidence production.

## Installed readback

The authenticated Forge Server `GET /v1/missions/{mission_id}` response adds
`mission.action_frontier` with contract version `parallel-action-frontier/v1`.
It reads the same installed, read-only Mission snapshot as the existing
lifecycle/evidence projection. At most 256 stored Actions are accepted. Action
IDs and orders must be unique; every dependency must name a stored Action; and
cycles, malformed statuses or invalid revisions fail closed with
`MISSION_ACTION_GRAPH_INVALID`. Output order is stable by stored order and ID.

`logical_frontier_action_ids` contains only stored `READY` Actions with no
hard predecessor. An Action with a completed predecessor still waits for
verified *edge-specific* evidence, which the current serial store cannot
prove. Failed or blocked predecessors block the dependent node. Every Action
reports `dispatchable: false` and `target_resolution: UNAVAILABLE` because the
current stored Action has no per-Action target binding. The response explicitly
reports `parallel_execution: NOT_QUALIFIED`. This is a planning/readback
classification, not authorization or proof of concurrent EP execution.

## Peer compatibility vector

The packaged
[`parallel-action-peer-graph-v1.json`](../../forge/api/parallel-action-peer-graph-v1.json)
is a synthetic `parallel-action-graph/v1` compatibility fixture: independent
Actions A/B target distinct repositories; Q names both predecessors and
repository-bound qualified-artifact digests. Forge's
`validate_peer_graph` checks the exact envelope, target fields, identifiers,
unique nodes/edges, predecessor existence, evidence digest format, evidence
repository match and cycles. It returns `dispatch_authorized: false` even for
a valid vector. An EP consumer can test parser/contract compatibility against
these bytes; the fixture is no credential, binding, grant, admission request,
execution receipt or proof that the current Forge runtime can materialize it.

Before any actual parallel Action dispatch, Forge still needs durable
per-Action target/baseline/correlation state, verified predecessor predicates,
scope policy and guarded fan-out; EP needs its separately qualified admission,
resource isolation and multi-run evidence. Those remain under their owning
`PA-F1..FQ` and `PA-E0..EQ` dependencies. Installed HTTP readback and exact
artifact qualification for this producer are separate from public release or
production installation.

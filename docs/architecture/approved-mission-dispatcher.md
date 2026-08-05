# Approved Mission Dispatcher 4.3

The Approved Mission Dispatcher owns Mission-level scheduling only. It reads a read-only Approved Mission Queue from Architecture Workspace records whose status is `approved_for_engineering`; candidates, recommendations, rejected records, and archived records cannot enter the queue.

```text
Approved Mission Queue → Mission Dispatcher → Mission Intake → Mission State
→ AI Mission Planner → Engineering → Mission Complete → Mission Dispatcher
```

Queue order is deterministic FIFO by Architecture approval timestamp and Mission
identity. `MISSION-0001` through `MISSION-0005` are historical Portfolio Seed
Missions and never enter operational Runtime Instance state; they receive no
dispatcher priority. The first queued Runtime Mission is therefore the first
Business-approved and Architecture-approved Generation 2 Mission.

The dispatcher creates a pending record, performs non-planning Mission Intake, creates the initial Mission State snapshot, and activates exactly one Mission. It is `IDLE` when no eligible record exists. An active record is durable and a SQLite partial unique index prevents a second active Mission after restart. Resume returns the persisted active Mission and verifies its non-terminal Mission State; it never reconstructs identity or starts a replacement.

When independently verified Mission State becomes `COMPLETED`, the dispatcher marks the Mission complete, invokes the supplied Architecture Review and Mission Recommendation hooks, and evaluates the queue again. A blocked or failed Mission halts advancement pending explicit recovery. The dispatcher does not plan Intents or Actions, render prompts, call an Execution Host, execute engineering, create a Mission, approve a Mission, prioritise a portfolio, or approve recommendations.

Business Workspace owns Business approval. Architecture Workspace owns engineering readiness. Mission Intake persists the governed boundary. The AI Mission Planner owns tactical planning; Forge Runtime and the Execution Host remain independent execution concerns.

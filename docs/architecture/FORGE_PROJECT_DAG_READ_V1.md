# Forge project-bound Mission/Action read projection V1

This is a bounded producer subset of `PRM-F-CONTRACT` and `PRM-F-PROJECTION` through the existing Forge Server `FH-HTTP` surface. It is not the complete project-loop capability or a new Project registration service. The current Forge Server binds at most one Engineering Platform project and repository through its existing versioned peer configuration. Both endpoints use the Server's instance-owned bearer credential and return JSON with `Cache-Control: no-store`.

An authenticated `GET /v1/project-dag/capability` on the installed Server
describes this HTTP read subset before a client requests a project. Its
`forge-project-dag-http-capability/v1` response binds the selected instance ID,
server product version, exact supported method/path pairs,
instance-bearer authentication and configured-project scope. `SUPPORTED_NOT_READINESS`
means the package supports these reads; it does not assert an EP binding, current
project availability or execution readiness. Project Mission attribution,
capability graph and Candidate/Expected views remain explicitly `UNAVAILABLE`.
The read does not probe EP or the provider, create a Project/Mission, or disclose
the credential or data-root path. This is only the project-DAG HTTP subset, not
an inventory of every Forge Server operation or a new CLI peer transport.

- `GET /v1/projects` returns `project-roadmap-read/v1`, the exact Forge instance ID and either one configured EP project/repository binding or `UNCONFIGURED` with an empty list. The list is a binding readback, not an EP availability check or a project creation operation.
- `GET /v1/projects/{project_id}/roadmap` accepts only the configured project ID. It reads up to 256 actual persisted Forge Mission states within one SQLite read transaction, in stable Mission-ID order. They are nested under `repository_scope.missions`, not represented as members of the EP project: Forge persists a repository source for each Mission but no project ID. `project_mission_attribution` is therefore `UNAVAILABLE`, including after a same-repository project rebind. Each repository-scoped Mission includes its actual lifecycle, revision, presentation group and stored Action IDs/status/dependency edges. `APPROVED_PLANNABLE` is shown as `APPROVED_PENDING`; terminal `COMPLETED`/`ARCHIVED` are `HISTORY`; other recorded states remain visible in `ACTIVE`, including blocked and recoverable failures. These are display groups, not changed lifecycle states.
- The projection reports source freshness and marks `project_capability_graph` and `candidate_and_expected_views` `UNAVAILABLE`. It does not infer project capability edges, approvals, completion, time estimates or runtime concurrency from documentary DAGs. It makes no EP request and performs no planning, admission, Mission allocation, provider call or state mutation.

A missing binding yields `UNCONFIGURED` in the list and `503 PROJECT_UNCONFIGURED` for detail. A different project yields `404 PROJECT_MISSING`; malformed IDs yield `400 PROJECT_REFERENCE_INVALID`. Inconsistent installed identity or binding, unreadable storage and more than 256 Missions return an explicit `503`; inconsistent Mission identity or Action edges/cycles return `409`. No partial graph is represented as complete. Authentication failure returns `401`; unsupported methods return `405`. The exact route inventory is checked against OpenAPI and Postman in the repository validation suite.

This producer can be exercised from a fresh installed Forge wheel. Workspace may later consume it only through the authenticated HTTP contract and must not treat `repository_scope.missions` as project membership. Full project attribution, capability DAGs, Candidate/Expected views, cross-Mission edges, remote HTTPS, Workspace peer integration and `PRM-F-Q` remain under their owning dependencies and evidence gates. Forge runtime installation and public registry release are separate product operations.

The same repository-scoped snapshot also reports sorted `active_mission_ids`,
`active_mission_count` and `active_mission_multiplicity` as `NONE`, `SINGLE` or
`UNSUPPORTED_MULTIPLE`. Only the existing `ACTIVE` presentation group counts;
approved-pending and history do not. A multiple-active observation remains
fully visible while explicitly marking the current serial Mission runtime's
unsupported cardinality. These fields do not prove project membership,
execution overlap or parallel capability, and reading them changes no state.

Project-roadmap `freshness` now comes from the persisted Mission state timelines,
never from the runtime's most recent open. Each repository-scoped Mission shows
its latest recorded transition as `source_observed_at` and its own
`CURRENT`/`STALE`/`UNKNOWN` classification against one read clock. The aggregate
`source_observed_at` is the oldest of those latest transitions; any missing or
malformed timeline makes aggregate freshness `UNKNOWN`. An empty repository
also reports `UNKNOWN`. A future timestamp reports `STALE`, including when
another Mission has a current transition. This is the age of recorded Mission
state, not a host liveness, Project membership or execution-readiness claim.

# Forge operational reset delivery status

The bounded Forge-owned operational-history reset is implemented in source with
schema 38 and the `forge server reset` command family. Patch 2.7.23 separates
general availability preview from operation-bound revalidation and adds the
explicit installed `revalidate` command. It is independent from
the planned Operations Console, full export/import/relocation product and Forge
Server daemon. Those broader nodes remain planned.

Status dimensions are deliberately separate:

| Dimension | State |
| --- | --- |
| Architecture/contract | IMPLEMENTED in `FORGE_OPERATIONAL_RESET_V1.md` |
| Application service and CLI | IMPLEMENTED |
| Same-operation revalidation regressions | PASSED locally: stable semantic plan, real row-content drift, backup, authority and fence checks |
| Joint subprocess candidate sequence | PASSED locally with non-editable candidate wheels and the real coordinator; protected installed-release repetition remains required |
| Independent protected-candidate review/checks | NOT YET EVIDENCED |
| Protected review/merge | NOT YET EVIDENCED in this source branch |
| Stable release publication | NOT YET EVIDENCED |
| Installed artifact | NOT YET EVIDENCED |
| Live selected-root preview | NOT PERFORMED by this source-delivery record |
| Production reset | NOT AUTHORIZED / NOT PERFORMED |
| Mission 3 | NOT STARTED |

The corrective stable patch release is `2.7.23` under
`forge-bootstrap-release-cadence-v2`: protected exact-head review/merge, one
clean wheel/sdist build, full qualification bound to their SHA-256 values,
draft GitHub release, PyPI publication, registry digest readback, installed-wheel
smoke, durable publication/cleanup receipt and completion. The earlier
qualification missed the defect because the coordinator revalidation path was
covered by a fixture state machine and product reset tests invoked the owning
services directly; no installed two-product sequence performed general preview
after both prepares. No branch-local test or wheel build is presented as
published or installed evidence.

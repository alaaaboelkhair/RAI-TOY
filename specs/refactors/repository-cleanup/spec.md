---
status: complete
created: 2026-10-14
---
# Repository cleanup

WHEN cleaning this repository, THE SYSTEM SHALL retain the current on-demand
RAI purchasing implementation, configuration example, dependency pin, meaningful
local tests, synthetic regression fixture and latest verification evidence.

WHEN removing obsolete files, THE SYSTEM SHALL archive local copies outside the
repository and remove old replenishment demos, materialized-plan verification,
redundant CSV/report exports and superseded specifications/documentation.

WHEN simplifying the query catalog source, THE SYSTEM SHALL keep the deployed
planner's three supporting fact queries and remove unused saved-plan queries.
RAI formulation, live tool behavior and deployed resources SHALL remain unchanged.

WHEN publishing, THE SYSTEM SHALL run local checks, exclude credentials and local
SDK state, commit the cleaned current workflow and push normally to origin/main.
Remote services SHALL NOT be redeployed or queried for this cleanup.

## Validation

- 26 local tests pass after removal of unused saved-plan queries.
- Current solver formulation and active supporting query behavior are preserved.
- Live ontology and assistant were not redeployed during cleanup.
- Obsolete local files archived to `/tmp/alaa-backorder-cleanup-20261014-145428`.
- Current README, dependency pin and latest compact evidence retained.

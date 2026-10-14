# Live purchasing reasoning

WHEN a purchasing question invokes the live planning tool, THE SYSTEM SHALL build
a fresh RAI ontology from input facts and run the prescriptive reasoner, without
using saved recommendation pack counts as decisions.

WHEN deriving a plan, THE SYSTEM SHALL use PyRel rules for counted receipts,
supplier eligibility, replenishment requirements and maximum achievable coverage,
and integer RAI/HiGHS decisions for packs with MOQ/capacity constraints.

WHEN a solve completes, THE SYSTEM SHALL verify every decision and product balance
before returning product priorities, supplier orders and shortage information.

WHEN input dimensions exceed the supported single-warehouse, fixed-window demo,
THE SYSTEM SHALL reject them rather than silently mix warehouse-level needs.

WHEN integrating with a UI, THE SYSTEM SHALL expose an explicit execution callable;
deploying a read-only ontology alone SHALL NOT be reported as enabling live solves.

Live run, deployment and UI integration require restored project authentication
and confirmation of the target UI's execution integration.

WHEN deploying this workflow, THE SYSTEM SHALL store executable model/tool logic
and input references, with derived ontology outputs represented as views rather
than static calculation tables. The planning tool SHALL read no saved plan,
recommendation or comparison table, and SHALL NOT publish solved results.

WHEN verifying a natural-language planning request, THE SYSTEM SHALL require both
a fresh successful tool execution and a complete, useful final assistant answer.

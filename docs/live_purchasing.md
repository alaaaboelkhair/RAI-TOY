# On-demand purchasing reasoning

`purchasing_reasoners.py` reads seven authoritative input tables through Snowpark
source I/O, then computes eligibility, counted receipts, requirements, achievable
coverage and early shortages using PyRel. RAI's prescriptive reasoner solves whole
pack quantities with HiGHS, enforcing MOQ and capacity while minimizing landed
cost for maximum achievable coverage. No handwritten SQL calculates the plan.

The planner never reads saved recommendations, plans or comparisons. It freezes
current raw input rows for each invocation; subsequent requests read updates.
Solved decisions are transient in memory. Independent Python checks validate the
solution; another RAI model verifies all product balances before returning it.
Neither the tool nor deployment writes calculated purchasing result tables or
places orders. Local JSON files are verification evidence, not ontology inputs.

`model.py` deploys six business concepts and input-derived logic with
`include_results=False`. Output configuration uses views rather than tables.
RAI's metadata/op-log tables store definitions and deployment history, not solved
purchasing decisions. Solver code is packaged with the existing Cortex tools.
The optimization runs when the planning tool is invoked, not during discovery.

```bash
env -u DEBUG .venv/bin/python purchasing_reasoners.py
```

Omitting `--snapshot` reads live input facts. `--snapshot
 data/smb_purchasing_results.json` uses local input fixtures and still invokes RAI.
Live execution requires working project authentication and incurs compute cost.

The supported scenario is 30 synthetic products, four suppliers and one warehouse,
with snapshot October 12 and window end November 11, 2026. Input quantities, prices
and supplier conditions recompute within that scenario; this does not create a new
forecast or shift dates when someone asks about "next month". Multiple warehouses
are rejected pending a product-location optimization formulation.

The existing agent is
`ALAA_RELAPP_PERSISTENCE.BACKORDER_AGENT.BACKORDER_ASSISTANT`. Its catalog exposes
`compute_purchasing_plan` and three supporting fact queries. Saved-plan tools and
baseline comparisons are not registered. The planning result has one summary and
30 product rows, including all supplier orders, within Cortex's response budget.
Each solve has a unique run ID. Tool timeout is 600 seconds; failures are reported
rather than replaced by a saved answer.

The user selected the existing RAI/Cortex assistant integration. Plain RelUI model
browsing does not itself invoke an optimizer; its chat must use this assistant/tool
integration. The RelUI backend is not in this repository.

`verify_live_purchasing.py` checks natural-language routing, complete fresh results,
and an actual useful final response. It rejects time-limit or incomplete answers.
Tests also exercise stale calculated columns, absent saved outputs, changed
capacity, native dates, optional arrivals, and actual PyRel result rules.

Verified October 14, 2026: all 26 local tests passed. The standalone live run and
the deployed assistant independently returned OPTIMAL: 3,226 pieces, $36,922,
49-piece demand gap and 15-piece safety gap. The end-to-end chat called the planner
once, returned all 30 product rows and 45 order lines without truncation, and
produced a complete final answer. Evidence is in
`data/live_purchasing_run_verification.json`,
`data/live_purchasing_chat_verification.json` and
`data/live_purchasing_agent_response.txt`. The metadata check in
`data/dynamic_ontology_deployment_verification.json` confirms no tables in the
ontology schema and no refresh tasks. Deployment recorded 84 op-log changes.

Warehouse settings, grants and token settings are not changed by this workflow.

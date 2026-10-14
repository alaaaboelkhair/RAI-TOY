# RelationalAI purchasing assistant

An on-demand purchasing demo using RelationalAI logic reasoning and HiGHS integer
optimization. The assistant reads current raw inputs, chooses supplier orders,
and explains inventory and delivery risks. It never reads saved purchasing
recommendations or publishes calculated output tables.

The dataset is synthetic: 30 products, four suppliers, one warehouse, and a fixed
**October 12–November 11, 2026** planning window. Changes to quantities, prices and
supplier terms recompute on the next invocation. Asking about “next month” does
not shift those dates or generate a new demand forecast.

## How it works

1. Read seven Snowflake input tables from `ALAA_DEMO_DATA.SMB_PURCHASING`.
2. Derive available stock, counted receipts, eligible offers, requirements and
   achievable coverage using PyRel rules.
3. Solve whole-pack order quantities using RAI's prescriptive reasoner and HiGHS,
   respecting approval, delivery dates, supplier capacity and minimum orders.
4. Verify decisions against an independent cost oracle and RAI-derived balances.
5. Return priorities, supplier orders, landed costs and shortages to the assistant.

The objective minimizes landed cost for maximum achievable coverage. Products
have independent supplier capacities; there is no shared budget or cross-product
allocation constraint. This is an end-window plan, not a daily stockout guarantee.

## Setup and local checks

Requires Python 3.13, an existing RelationalAI installation and access to the
configured Snowflake account, raw input tables and reasoners.

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp raiconfig.example.yaml raiconfig.yaml
```

Set `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER` and `SNOWFLAKE_TOKEN` in your local
environment. The configuration example uses warehouse `RAI_XS` and role
`RAI_DEFAULT_ROLE`; confirm these are appropriate for your account. Keep the
filled configuration and credentials out of Git.

Run the local tests without invoking remote reasoners:

```bash
env -u DEBUG .venv/bin/python -m unittest \
  test_purchasing_demo test_purchasing_ontology test_purchasing_reasoners
```

Run a fresh live plan:

```bash
env -u DEBUG .venv/bin/python purchasing_reasoners.py
```

To use the checked-in synthetic input fixture instead of live tables:

```bash
env -u DEBUG .venv/bin/python purchasing_reasoners.py \
  --snapshot data/smb_purchasing_results.json
```

Both planning commands invoke remote RAI reasoners and incur compute cost. The
JSON fixture contains historical expected results for regression checks; those
saved decisions are ignored by the fresh planner.

## Deployment and UI

The existing ontology is `ALAA_RELAPP_PERSISTENCE.BACKORDER_MODEL` and the Cortex
assistant is `ALAA_RELAPP_PERSISTENCE.BACKORDER_AGENT.BACKORDER_ASSISTANT`.
Ontology outputs are views. Solver code is packaged as the
`compute_purchasing_plan` tool alongside three supporting fact queries.

To deploy changes deliberately:

```bash
env -u DEBUG .venv/bin/rai models deploy --path model.py --wait
env -u DEBUG .venv/bin/python deploy_agent.py update
```

No automatic refresh or background optimization is required. A planning request
runs the solve; discovery does not. Plain RelUI ontology browsing does not invoke
the optimizer: its question interface must use the existing Cortex assistant/tool
integration.

Example question:

> Use the RelationalAI reasoners to recompute the purchasing recommendation for
> Nitrile gloves from current data. Which supplier should I choose, how many packs
> and pieces should I order, and what is the lowest landed cost while respecting
> delivery dates, supplier capacity and minimum orders? Flag shortages or risks.

## Files

| File | Purpose |
|---|---|
| `purchasing_reasoners.py` | Fresh input reasoning, optimization and verified answer payload |
| `purchasing_ontology.py` | Six concepts, source mappings and PyRel business rules |
| `purchasing_optimization.py` | RAI decision variables, constraints, objective and solve |
| `purchasing_sources.py` | Source schema contract |
| `model.py` | Deployed input-fact and logic ontology |
| `generated_model.py` | Compatible ontology/CLI entry point for the IDE |
| `deploy_agent.py`, `query.py` | Existing assistant deployment and supporting fact queries |
| `purchasing_demo.py` | Synthetic fixture and independent verification helpers |
| `test_purchasing_*.py` | Local business-rule and actual PyRel regression tests |
| `verify_dynamic_deployment.py` | Read-only checks for views and absent refresh tasks |
| `verify_live_purchasing.py` | End-to-end fresh solve and complete assistant-answer checks |
| `data/` | Regression fixture and latest verification evidence |

## Verified result

Verified October 14, 2026: 26 local tests passed. The standalone live run and
assistant each returned **OPTIMAL: 3,226 pieces for $36,922**, with a **49-piece
unmet-demand gap**, a **15-piece safety-stock gap** and six buyer exceptions.
The chat returned all 30 product rows and 45 order lines without truncation.

See [assistant response](data/live_purchasing_agent_response.txt),
[chat verification](data/live_purchasing_chat_verification.json),
[live-run verification](data/live_purchasing_run_verification.json) and
[deployment verification](data/dynamic_ontology_deployment_verification.json).
More details are in [the live workflow guide](docs/live_purchasing.md).

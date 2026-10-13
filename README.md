# Small-business Purchasing Assistant

The active RelationalAI ontology and Snowflake Cortex agent now serve a simpler
**30-product, four-supplier, one-warehouse purchasing scenario**. The buyer asks:

> What should we order this week, from which suppliers, and what cannot arrive in time?

All operational facts are synthetic. Product names, prices, inventory, demand,
reservations, supplier commitments and receipt dates are generated demo inputs.
`source_sku` links each product to an existing source identifier for provenance;
it does not claim the generated descriptions or quantities belong to real SKUs.
The original `ALAA_DEMO_DATA.SUPPLY_CHAIN.BACKORDERS` table is untouched.

The scenario `smb_purchasing_20261012_v1` starts **October 12, 2026** and ends
**November 11, 2026**. It is a fixed 30-day snapshot, reviewed conceptually weekly;
no automatic weekly refresh or regeneration is configured.

## Purchasing workflow

The company has one Main Warehouse, descriptive products, piece/pack units,
safety stock, dated incoming orders and approved supplier offers. Offers have
explicit deliverable capacity, MOQ and pack multiples. Prices are **USD cents per
piece**, with inbound freight included in landed price. Whole packs determine
order quantities. Existing confirmed incoming orders are distinct from proposed
new purchases.

## Data and business rules

Dedicated input/result tables are in `ALAA_DEMO_DATA.SMB_PURCHASING`:
products, suppliers, warehouse, inventory, offers, incoming orders, purchasing
needs, plan and recommendations. Each table carries a synthetic flag, scenario
ID and snapshot date; CSV exports and the complete solve artifact are in `data/`.

- Available inventory = physical on-hand pieces minus reserved pieces.
- Remaining demand excludes orders already allocated to reserved stock. Early
  obligations are included in that remaining demand, not added again.
- Confirmed receipts count only after the snapshot and on/before the planning end.
  Overdue orders need reconfirmation; cancelled and late orders do not count.
- Required replenishment = max(0, remaining demand + target safety stock
  - available inventory - counted receipts).
- Offers are eligible only when approved, lead time is known, expected arrival is
  within the window and capacity can satisfy a valid pack-rounded minimum order.
  Missing lead time is explicitly `-1`, with no invented arrival date.
- No warehouse transfers are part of the active plan.

## Optimization and exceptions

`purchasing_demo.py` formulates a genuine RAI/HiGHS integer optimization over order
pack counts and binary order activations. It respects pack multiples, MOQ, on-time
capacity, sourcing approval and coverage. There are no shared capacity constraints
between products in this small version. This permits computing the exact maximum
achievable coverage per product before minimizing landed cost, without arbitrary
shortage penalty weights. Unavoidable shortfalls stay visible.

Demand shortfall and safety-stock shortfall are reported separately. Negative
projected ending balance indicates unmet demand; it is not negative physical stock.
An independent exact dynamic program verifies minimum cost for every product.

This is an end-window plan, **not daily stockout prevention**. A separate early
obligation check flags buyer intervention where available stock and all eligible
arrivals by the early due date cannot cover the obligation. Expedite/reconfirmation
and changing commitments require a buyer. No actual purchase orders are executed.
The fixture deliberately exercises missing lead time, disallowed sourcing,
overdue/cancelled/late receipts, early shortage and no on-time supplier capacity.

## Simple baseline comparison

The optimizer is unchanged. After validating its saved solution, the script also
builds a deterministic rule-based plan for each product: visit eligible offers
in ascending landed unit price (including freight), break ties by supplier ID
then offer ID, round the remaining requirement up to whole packs and MOQ, cap
the order at deliverable capacity, and proceed to the next supplier if necessary.
Stop when maximum achievable coverage is reached. No solver is used for this rule.

Both strategies use the same stock, dated receipts, demand, safety targets and
offer eligibility. Feasibility includes the same unavoidable-shortfall allowance;
neither strategy claims complete demand coverage. Every baseline order and both
shortfall types are checked per product. The independent cost oracle continues
to verify the saved optimized plan.

| Measure | Price-first baseline | Optimized |
|---|---:|---:|
| Landed purchase cost | $38,227.12 | $36,922.00 |
| Purchased pieces | 3,366 | 3,226 |
| Demand shortfall | 49 | 49 |
| Safety-stock shortfall | 15 | 15 |
| Excess above ending-stock targets | 286 | 146 |

The optimized plan saves **$1,305.12 (3.41% of baseline cost)**, with cost savings
on 17 products. For example, product 22 costs $814.08 under the rule (48 pieces)
versus $431.04 optimized (24 pieces): a smaller order can cost less overall even
when its supplier's price per piece is higher.

`PurchasingComparison` exposes the summary through the `purchasing_comparison`
agent query. `SMB_BASELINE_ORDERS_V1` stores all 38 baseline order lines in the
source schema for audit; baseline orders remain separate from active optimized
recommendations. CSV exports and `data/smb_baseline_product_comparison.json`
provide reproducible order-level and product-level evidence. Ask the agent:
"Compare the optimized plan with the lowest-price-first baseline."

Validated RAI/HiGHS result for this fixed snapshot:

| Measure | Result |
|---|---:|
| Recommended purchase pieces | 3,226 |
| Recommended supplier order lines | 45 |
| Landed purchase cost | $36,922.00 USD |
| End-window forecast demand shortfall | 49 pieces |
| Safety-stock shortfall | 15 pieces |
| Products requiring buyer attention | 6 |

Solver status is `OPTIMAL` with zero relative gap. Product 2 (Safety glasses)
has no supplier able to arrive within the window: 49 pieces of demand and 15
pieces of safety stock remain uncovered. Product 1 has a separate 15-piece early
obligation shortfall on October 15; the other exception products have overdue
incoming orders requiring reconfirmation. These are deliberately visible
operational exceptions, not hidden infeasibility or successful demand coverage.

## Files

- `model.py`: ten concepts and derived available inventory/landed price.
- `purchasing_demo.py`: deterministic data generation, RAI solve, independent
  validation, CSV export and Snowflake publication.
- `query.py`: seven vetted read-only buyer queries, including baseline comparison.
- `deploy_agent.py`: existing Cortex agent lifecycle and updated instructions.
- `test_purchasing_demo.py`: local business-rule regression tests.
- `verify_purchasing_deployment.py`: materialized balances and actual agent-tool checks.

## Run and deploy

For a fresh checkout, create an environment and copy the credential-free template:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp raiconfig.example.yaml raiconfig.yaml
```

Set `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, and `SNOWFLAKE_TOKEN` in your local
environment. The filled `raiconfig.yaml` is ignored by Git. The target account
must have RelationalAI installed, the named warehouse/roles and appropriate
permissions. The scripts use the project database/schema names shown in the
configuration and code; adapt those identifiers for a different account.
Fresh scenario generation also needs the referenced BACKORDERS source table.
The included synthetic snapshot can instead be republished with
`purchasing_demo.py --publish-saved` once the target Snowflake environment exists.
Validate the local connection with `env -u DEBUG .venv/bin/rai connect`.


Use the existing `.venv` (`relationalai==1.35.0`). Remove the host `DEBUG` variable
because it conflicts with RAI's structured configuration:

```sh
env -u DEBUG .venv/bin/python -m unittest test_purchasing_demo.py
env -u DEBUG .venv/bin/python purchasing_demo.py --publish
env -u DEBUG .venv/bin/rai models deploy --path model.py --wait
```

If the task owner lacks account-level `EXECUTE TASK`, use the supported manual
refresh in a Snowflake SQL session:

```sql
CALL ALAA_RELAPP_PERSISTENCE.BACKORDER_MODEL_META._INTERNAL_REFRESH_MODEL('demo', NULL);
```

Then update the existing agent and verify it:

```sh
env -u DEBUG .venv/bin/python deploy_agent.py update
env -u DEBUG .venv/bin/python verify_purchasing_deployment.py
env -u DEBUG .venv/bin/python deploy_agent.py chat "What should we buy, how much will it cost, and what requires buyer attention?"
```

`--publish-saved` revalidates and republishes the saved purchasing snapshot without
re-solving. Source activation occurs after all staged writes succeed; reruns replace
only the dedicated SMB demo tables. Publication is not an atomic cross-table swap;
refresh the ontology only after the command completes successfully.

## Agent and query examples

The deployed ontology is `ALAA_RELAPP_PERSISTENCE.BACKORDER_MODEL` and the agent is
`ALAA_RELAPP_PERSISTENCE.BACKORDER_AGENT.BACKORDER_ASSISTANT`. Find the existing
agent in Snowsight's AI & ML agent interface.

Try:

- Summarize the purchasing plan, costs and shortfalls.
- Show the buyer worklist for all products.
- Which incoming orders were excluded, and why?
- Explain the missing lead time for product 3.
- What requires buyer attention for product 1 and product 2?
- Show recommended purchases with quantities in pieces and packs.

The agent reads materialized, precomputed outputs using seven catalog tools and the
RAI dynamic query facility. It does not solve live or modify business systems.
The zero-interval deployment schedule requires explicit refresh after changes.
Access for other users follows the existing caller-rights tool permissions.

Deployment verified October 12, 2026: all ten concept counts matched the saved
snapshot; SQL found zero offer, inventory-balance, or receipt-rule violations;
all seven catalog tools returned complete results, including all 45 optimized order lines.
`data/smb_deployment_verification.json` records the checks and returned rows.
An end-to-end agent chat correctly labeled the scenario synthetic and reported
the exact scope, costs, shortfalls, early exception and absence of transfers;
its answer is saved in `data/smb_agent_demo_response.txt`.

The baseline extension passed eight local business-rule tests and deployed SQL
checks of baseline pack/MOQ/capacity compliance and identical per-product
shortfalls. The comparison tool returns the exact saved costs and quantities.
The final agent comparison response is saved in `data/smb_baseline_agent_response.txt`.

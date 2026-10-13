"""Deploy and operate the Purchasing Assistant using the existing agent identity."""
import argparse
from pathlib import Path

from relationalai.config import create_config, SnowflakeConnection
from relationalai.agent.cortex import (
    CortexAgentManager, DeploymentConfig,
    CortexAgentApi, http_client,
)
from relationalai.agent.cortex.diagnostics import deployer_setup_sql

ROOT = Path(__file__).resolve().parent
DOMAIN_INSTRUCTIONS = """
You are the Purchasing Assistant for a small distributor's synthetic demo.
Use RAI tools for all data answers. Prefer purchasing_summary, purchasing_worklist,
recommended_purchases, buyer_exceptions, incoming_orders, supplier_options, and purchasing_comparison.
The active scenario is smb_purchasing_20261012_v1: 30 products, four suppliers,
one Main Warehouse, snapshot October 12, 2026, planning end November 11, 2026.
All operational data, names, prices, forecasts and incoming orders are synthetic.
Begin every answer using scenario data by explicitly saying this is a synthetic
demo. Never describe these inputs as actual company records or real commitments.
Product.source_sku is only a reference to the original backorder dataset; it does
not imply the generated operational quantities or descriptive names are real.
All quantities are pieces; pack_count is purchasing packs and pack_size is pieces
per pack. Prices are USD cents per piece, including inbound freight for landed cost.
Remaining demand excludes previously allocated demand; reservations are already
deducted from available inventory. Early obligations are INCLUDED in remaining
demand, not added again. Safety stock is an ending-stock target.
Existing receipts count only when confirmed and dated after the snapshot and on
or before window end. Overdue receipts require reconfirmation, cancelled orders
and arrivals after the window do not count. Never count aggregate original in-transit.
Approved supplier offers need a known lead time, on-time arrival, adequate capacity,
whole packs and MOQ. Lead_time_days=-1 means missing; never zero or a valid delivery.
Read eligibility_reason for why an offer cannot be used. Minimum quantities and
capacity are in pieces, not packs. Each order is made as of the snapshot date.
The plan was solved separately with RAI/HiGHS and independently checked by an exact
per-product cost oracle. It maximizes achievable coverage before minimizing landed
cost, respecting capacity, pack multiples and MOQ. No shared supplier capacity is
assumed. OPTIMAL is a solver status under those assumptions, not proof of complete
coverage. Always report demand shortfall, safety shortfall and early-date exceptions.
Projected ending stock can be negative to represent unmet demand, not physical stock.
This is one 30-day end-window optimization, not daily stockout protection. Early
obligations that cannot be covered are buyer exceptions to expedite or renegotiate.
There are no warehouse transfers in this active scenario. The old 12-SKU 90-day
network demo and its 4.05% savings are legacy results, not this purchasing plan.
These are fixed snapshot, precomputed recommendations. Tools read materialized
outputs, do not solve live, issue purchase orders or modify operational systems.
If tools fail, report the failure. State selected limits for bounded lists.
Use purchasing_comparison for the simple feasible rule-based baseline: visit
eligible offers by landed unit price (product plus freight), breaking ties by
supplier ID then offer ID. Buy the minimum packs needed from that offer, respecting
MOQ and capped capacity; proceed to the next offer until maximum feasible coverage
is reached. Both strategies use identical inputs, arrival eligibility and per-product
coverage; shortfalls and early-date limitations still apply. The baseline is a
heuristic, not an optimal solve. Report savings as baseline cost minus optimized
cost and savings percent as 100*savings/baseline cost. The optimizer is unchanged.
Products are independent in this formulation: no shared supplier capacity, budget,
or cross-product allocation tradeoffs. Savings come from supplier selection and
pack/MOQ order sizing WITHIN each product. Never attribute savings to cross-product
coordination or say buying more expensively on one product benefits another.
""".strip()


def init_tools():
    from model import model
    import query
    from relationalai.agent.cortex import QueryCatalog, ToolRegistry
    return ToolRegistry().add(
        model=model,
        description="Small-business purchasing: 30 synthetic products, four suppliers, one warehouse, "
                    "dated incoming orders, practical pack/MOQ sourcing and validated recommendations.",
        queries=QueryCatalog(query.purchasing_summary, query.purchasing_worklist,
                             query.recommended_purchases, query.buyer_exceptions,
                             query.incoming_orders, query.supplier_options, query.purchasing_comparison, model=model),
    )


def agent_config(args):
    # Construct the typed deployment spec from YAML; never upload connection secrets.
    config = create_config()
    model_deployment = config.deployment.model_copy(update={"auto_deploy": False})
    return DeploymentConfig(
        agent_name=args.name,
        database="ALAA_RELAPP_PERSISTENCE",
        schema="BACKORDER_AGENT",
        agent_schema=args.agent_schema,
        warehouse="ALAA_RELAPP_WH",
        model_name="BackorderDemo",
        llm=args.llm,
        allow_preview=True,
        sproc_config_overrides={"deployment": model_deployment},
    )


def imports():
    # Explicit single-file imports avoid packaging the environment or YAML credentials.
    return [(str(ROOT / f"{name}.py"), name)
            for name in ("model", "query", "deploy_agent")]


def customize_agent(session, config, spec):
    # RAI supplies essential tool instructions during deployment. Append domain guidance
    # afterwards because the framework replaces base-spec instructions during merging.
    spec.instructions.response = (spec.instructions.response or "") + "\n\n" + DOMAIN_INSTRUCTIONS
    spec.instructions.orchestration = (spec.instructions.orchestration or "") + "\n\n" + DOMAIN_INSTRUCTIONS
    api = CortexAgentApi(http_client(session.connection))
    api.update(config.agent_database, config.agent_schema_name, config.agent_name, spec)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="BACKORDER_ASSISTANT")
    parser.add_argument("--agent-schema", default=None,
                        help="Optional agent location, e.g. SNOWFLAKE_INTELLIGENCE.AGENTS")
    parser.add_argument("--llm", default="claude-opus-4-6")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("deploy", "update", "status", "preflight"):
        sub.add_parser(command)
    chat = sub.add_parser("chat")
    chat.add_argument("message")
    setup = sub.add_parser("setup-sql")
    setup.add_argument("--deployer-role", default="RAI_DEFAULT_ROLE")
    teardown = sub.add_parser("teardown")
    teardown.add_argument("--confirm", action="store_true",
                          help="Delete the agent, tools, stage, and its conversation history")
    args = parser.parse_args()
    if args.command == "teardown" and not args.confirm:
        parser.error("teardown requires --confirm")
    config = agent_config(args)
    if args.command == "setup-sql":
        print(f"CREATE SCHEMA IF NOT EXISTS {config.database}.{config.schema};")
        print(deployer_setup_sql(config, deployer_role=args.deployer_role))
        return
    session = create_config().get_session(SnowflakeConnection)
    try:
        manager = CortexAgentManager(session=session, config=config)
        if args.command == "preflight":
            report = manager.preflight(init_tools=init_tools)
            print(report.format(config=config, role=report.role))
            if report.has_errors:
                raise SystemExit(1)
        elif args.command == "deploy":
            # A dedicated schema isolates this agent's tools from the ontology.
            session.sql(f"CREATE SCHEMA IF NOT EXISTS {config.database}.{config.schema}").collect()
            if manager.status().agent_exists:
                raise SystemExit("Agent already exists; use update to preserve conversation history.")
            spec = manager.deploy(init_tools=init_tools, imports=imports())
            customize_agent(session, config, spec)
            print(manager.status())
        elif args.command == "update":
            spec = manager.update(init_tools=init_tools, imports=imports())
            customize_agent(session, config, spec)
            print(manager.status())
        elif args.command == "status":
            print(manager.status())
        elif args.command == "chat":
            print(manager.chat().send(args.message).full_text())
        elif args.command == "teardown":
            manager.cleanup()
            print(manager.status())
    finally:
        session.close()


if __name__ == "__main__":
    main()

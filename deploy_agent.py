"""Deploy and operate the Purchasing Assistant using the existing agent identity."""
import argparse
from pathlib import Path

from relationalai.config import create_config, SnowflakeConnection
from relationalai.agent.cortex import (
    CortexAgentManager, DeploymentConfig,
    CortexAgentApi, http_client,
    QueryCatalog,
)
from relationalai.agent.cortex.diagnostics import deployer_setup_sql

ROOT = Path(__file__).resolve().parent
DOMAIN_INSTRUCTIONS = """
You answer purchasing questions for a synthetic demo, not actual company records.
For purchases, priorities, supplier selection, quantities, costs or shortages,
call compute_purchasing_plan exactly once first. It reads current raw facts and
runs fresh RAI logic and RAI/HiGHS integer optimization. No saved plan is available.
Use its returned rows to answer directly in concise prose and a small table.
Do not call chart, skill, comparison or other tools after a successful planning
result. Do not retry a timed-out solve in the same turn; explain the failure.
The summary row contains totals and a fresh run ID; the 30 product rows contain
supplier_orders JSON arrays [supplier,pieces,packs,arrival_date,landed_cost_USD].
Never add summary totals to product totals. Prioritize demand and early shortages,
then replenishment needs, and name suppliers and quantities for key purchases.
Always state synthetic demo and the returned planning dates. The current dataset
has one warehouse and a fixed October 12–November 11, 2026 planning window; 'next
month' does not shift those dates or create new forecasts. Data updates within
that scenario are read on each invocation. Unsupported dimensions fail explicitly.
Quantities are pieces; packs times pack size gives pieces. Costs include freight.
Confirmed receipts count only after snapshot and through window end. Overdue
receipts need reconfirmation. Approved offers require known lead time, on-time
arrival, MOQ, capacity and whole packs. Remaining demand already excludes allocated
demand; reservations reduce available stock. Safety stock is an ending target.
The optimizer covers maximum achievable requirements then minimizes landed cost.
Products have independent capacities: no shared supplier budget or constraints.
OPTIMAL does not mean all demand can be covered. Report demand and safety gaps,
early-delivery exceptions and overdue receipts requiring buyer attention.
This is an end-window model, not a daily stockout guarantee. No tool places orders,
publishes calculated tables or changes operational records. Other catalog queries
are raw product/receipt/supplier facts only. If the planner fails, report that.
""".strip()


class LivePlanningCatalog(QueryCatalog):
    """Expose one live planner and supporting facts; no saved planning tools."""
    def get_available_queries(self):
        metadata=super().get_available_queries()
        visible={'compute_purchasing_plan','find_products','incoming_orders',
                 'supplier_options'}
        metadata['queries']={key:value for key,value in metadata['queries'].items() if key in visible}
        metadata['query_instructions']=(
            'For any purchasing plan, priorities, supplier order quantities, costs or shortages, '
            'execute {"id":"compute_purchasing_plan","args":{}} first. '
            'This is the only planning query. The other queries provide product lookup, '
            'incoming-order and supplier facts. '
            'Execute catalog queries with an id and args; dynamic queries are unavailable.')
        return metadata


def init_tools():
    from model import model
    import query
    from purchasing_reasoners import compute_purchasing_plan
    from relationalai.agent.cortex import QueryCatalog, ToolRegistry
    return ToolRegistry().add(
        model=model,
        description="Small-business purchasing: 30 synthetic products, four suppliers, one warehouse, "
                    "current input facts and on-demand RAI purchasing optimization.",
        queries=LivePlanningCatalog(query.incoming_orders, query.supplier_options,
                                   query.find_products, compute_purchasing_plan),
    )


def agent_config(args):
    # Construct the typed deployment spec from YAML; never upload connection secrets.
    config = create_config()
    return DeploymentConfig(
        agent_name=args.name,
        database="ALAA_RELAPP_PERSISTENCE",
        schema="BACKORDER_AGENT",
        agent_schema=args.agent_schema,
        warehouse=config.get_connection(SnowflakeConnection).warehouse,
        model_name="PurchasingAssistant",
        llm=args.llm,
        allow_preview=True,
        # Cortex's generic tools enforce a maximum of 600 seconds.
        query_timeout_s=600,
        sproc_config_overrides={"deployment": None},
    )


def imports():
    # Explicit single-file imports avoid packaging the environment or YAML credentials.
    return [(str(ROOT / f"{name}.py"), name)
            for name in ("model", "query", "deploy_agent", "purchasing_ontology", "purchasing_sources",
                         "purchasing_reasoners", "purchasing_optimization", "purchasing_demo")]


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

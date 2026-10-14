"""Run fresh RAI logic and HiGHS purchasing reasoning; never execute business SQL.

CLI: python purchasing_reasoners.py --snapshot data/smb_purchasing_results.json
For live input tables, omit --snapshot. No source or deployed table is written.
The callable compute_purchasing_plan can be registered in a RAI QueryCatalog.
RelUI must explicitly invoke that callable through its execution integration.
"""
import argparse
from copy import deepcopy
import json
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4

from relationalai.config import create_config,DuckDBConnection
from relationalai.semantics import inspect

from purchasing_demo import restore_dates, validate_inputs, finish, TABLES
from purchasing_sources import SOURCE_SCHEMAS
from purchasing_ontology import build_ontology
from purchasing_optimization import solve_purchasing


def load_raw_snapshot(config):
    """Source I/O only: fetch input facts; all calculations run in RAI afterward.

    No recommendation, plan or comparison table is read. Snowpark generates the
    simple source SELECTs; there are no SQL business calculations or output writes.
    """
    from relationalai.config import SnowflakeConnection
    from purchasing_sources import SCHEMA
    session=config.get_session(SnowflakeConnection)
    excluded={'offers':{'ELIGIBLE_PACKS','ELIGIBILITY_REASON'},
              'incoming_orders':{'COUNTED_QTY','EXCLUSION_REASON'},
              'needs':set(SOURCE_SCHEMAS[TABLES['needs']])-{
                  'PRODUCT_ID','WAREHOUSE_ID','WINDOW_END','REMAINING_DEMAND_QTY',
                  'EARLY_DUE_DATE','EARLY_DEMAND_QTY','IS_SYNTHETIC','SCENARIO_ID','SNAPSHOT_DATE'}}
    data={}
    for key in ('products','suppliers','warehouses','inventory','offers','incoming_orders','needs'):
        columns=[c for c in SOURCE_SCHEMAS[TABLES[key]] if c not in excluded.get(key,set())]
        data[key]=[row.as_dict() for row in session.table(f'{SCHEMA}.{TABLES[key]}').select(*columns).collect()]
    return restore_dates(data)


def derive_purchasing_inputs(data=None, *, config=None):
    """Derive eligibility, receipts and coverage from input facts using PyRel."""
    config=(config or create_config()).model_copy(deep=True)
    if data is None:
        data=load_raw_snapshot(config)
        config.deployment=None
    else:
        data=deepcopy(data)
    ontology=build_ontology(name='PurchasingInputReasoning',config=config,data=data,
                           include_results=False,recompute_inputs=True)
    m=ontology.model;p=ontology.Product;o=ontology.SupplierOffer;r=ontology.IncomingOrder
    # This demo supports one inventory location and one fixed planning window.
    if len(data['warehouses'])!=1 or len({n['PRODUCT_ID'] for n in data['needs']})!=len(data['needs']):
        raise ValueError('This planning workflow requires one warehouse and one need per product')
    fields=['available_qty','counted_receipts_qty','required_qty',
            'unavoidable_shortfall_qty','early_shortfall_qty']
    needs=m.select(p.product_id.alias('product_id'),
        *(getattr(p,field).alias(field) for field in fields)).to_df().to_dict('records')
    offers=m.select(o.offer_id.alias('offer_id'),o.eligible_packs.alias('eligible_packs'),o.eligibility_reason.alias('reason')).to_df().to_dict('records')
    receipts=m.select(r.order_id.alias('order_id'),r.counted_qty.alias('counted_qty'),r.exclusion_reason.alias('reason')).to_df().to_dict('records')
    if len(needs)!=len(data['needs']) or len(offers)!=len(data['offers']) or len(receipts)!=len(data['incoming_orders']):
        raise ValueError('Reasoning produced incomplete inputs; no optimization will run')
    by_product={int(row['product_id']):row for row in needs}
    by_offer={int(row['offer_id']):row for row in offers}
    by_order={int(row['order_id']):row for row in receipts}
    for row in data['needs']:
        row.update({field.upper():int(by_product[row['PRODUCT_ID']][field]) for field in fields})
    for row in data['offers']:
        row['ELIGIBLE_PACKS']=int(by_offer[row['OFFER_ID']]['eligible_packs'])
        row['ELIGIBILITY_REASON']=by_offer[row['OFFER_ID']]['reason']
    for row in data['incoming_orders']:
        row['COUNTED_QTY']=int(by_order[row['ORDER_ID']]['counted_qty'])
        row['EXCLUSION_REASON']=by_order[row['ORDER_ID']]['reason']
    validate_inputs(data)
    return data,inspect.schema(m).to_dict()


def run_purchasing_reasoners(data=None, *, config=None):
    """Each invocation derives fresh inputs, solves, and independently verifies."""
    execution={'run_id':str(uuid4()),'started_at_utc':datetime.now(timezone.utc).isoformat()}
    inputs,schema=derive_purchasing_inputs(data,config=config)
    result=solve_purchasing(inputs,config=config,recompute_inputs=True)
    # finish verifies the exact per-product oracle and all order/inventory balances.
    finish(inputs,result,write_artifacts=False)
    read_reasoned_results(inputs,config=config)
    execution['finished_at_utc']=datetime.now(timezone.utc).isoformat()
    return {'data':inputs,'solve':result,'input_reasoning_schema':schema,'run':execution,
            'execution':'fresh RAI logic + prescriptive solve; no saved decisions loaded'}


def read_reasoned_results(data, *, config=None):
    """Cross-check the newly solved packs through RAI-derived balances and flags."""
    config=(config or create_config()).model_copy(deep=True)
    if not isinstance(config.get_default_connection(),DuckDBConnection):
        config.deployment=None
    ontology=build_ontology(name='PurchasingSolvedReasoning',config=config,data=data,
                           include_results=True,recompute_inputs=True)
    m=ontology.model;p=ontology.Product
    fields=['available_qty','counted_receipts_qty','required_qty','purchase_qty',
            'total_cost_cents','projected_ending_qty','demand_shortfall_qty',
            'safety_shortfall_qty','excess_above_target_qty','early_shortfall_qty']
    rows=m.select(p.product_id.alias('product_id'),
        *(getattr(p,f).alias(f) for f in fields)).to_df().to_dict('records')
    expected={n['PRODUCT_ID']:n for n in data['needs']}
    if len(rows)!=len(expected):
        raise ValueError('RAI result reasoning omitted one or more products')
    for row in rows:
        for field in fields:
            if int(row[field])!=expected[int(row['product_id'])][field.upper()]:
                raise ValueError(f'RAI result mismatch for product {row["product_id"]}: {field}')
    return rows


def compute_purchasing_plan():
    """Run fresh RAI/HiGHS optimization for the fixed synthetic planning window.

Use this tool for purchase priorities, supplier selection, quantities and shortages.
Returns one summary row and one row per product. supplier_orders is a JSON list
of [supplier, pieces, packs, arrival_date, landed_cost_USD] for that product.
All shortage quantities are pieces. Do not add summary totals to product totals.
Does not place orders, refresh or publish tables.
Each invocation runs the reasoners and can incur compute cost.
"""
    return format_plan_table(run_purchasing_reasoners())


def format_plan_table(artifact):
    """Compact, complete response within the Cortex 50-row/14-KB envelope."""
    import pandas as pd
    data=artifact['data'];products={p['PRODUCT_ID']:p for p in data['products']}
    suppliers={s['SUPPLIER_ID']:s for s in data['suppliers']}
    plan=data['plans'][0]
    rows=[dict(record_type='summary',product=f'Synthetic demo; {plan["SNAPSHOT_DATE"]} to {plan["WINDOW_END"]}; {plan["STATUS"]}',
        purchase_pieces=plan['PURCHASE_QTY'],cost_usd=plan['TOTAL_COST_CENTS']/100,
        demand_shortfall=plan['DEMAND_SHORTFALL_QTY'],safety_shortfall=plan['SAFETY_SHORTFALL_QTY'],
        early_shortfall=sum(n['EARLY_SHORTFALL_QTY'] for n in data['needs']),
        attention=f'{plan["EXCEPTION_PRODUCT_COUNT"]} products need buyer attention',
        supplier_orders='[]',run_id=artifact['run']['run_id'])]
    for n in sorted(data['needs'],key=lambda n:(-n['DEMAND_SHORTFALL_QTY'],
                    -n['EARLY_SHORTFALL_QTY'],-n['REQUIRED_QTY'],n['PRODUCT_ID'])):
        orders=[[suppliers[a['SUPPLIER_ID']]['NAME'],a['QUANTITY'],a['PACK_COUNT'],
                 str(a['EXPECTED_ARRIVAL_DATE']),a['TOTAL_COST_CENTS']/100]
                for a in data['recommendations'] if a['PRODUCT_ID']==n['PRODUCT_ID']]
        rows.append(dict(record_type='product',product=products[n['PRODUCT_ID']]['NAME'],
            purchase_pieces=n['PURCHASE_QTY'],cost_usd=n['TOTAL_COST_CENTS']/100,
            demand_shortfall=n['DEMAND_SHORTFALL_QTY'],safety_shortfall=n['SAFETY_SHORTFALL_QTY'],
            early_shortfall=n['EARLY_SHORTFALL_QTY'],attention=n['BUYER_EXCEPTION'],
            supplier_orders=json.dumps(orders,separators=(',',':')),run_id=''))
    return pd.DataFrame(rows)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path)
    parser.add_argument('--output',type=Path,default=Path('data/live_purchasing_verified.json'))
    args=parser.parse_args()
    data=restore_dates(json.loads(args.snapshot.read_text())['data']) if args.snapshot else None
    artifact=run_purchasing_reasoners(data)
    args.output.write_text(json.dumps(artifact,indent=2,default=str)+'\n')
    print(json.dumps(artifact['data']['plans'][0],default=str,indent=2))


if __name__=='__main__':
    main()

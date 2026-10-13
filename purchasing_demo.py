"""Generate, solve, independently verify, and publish the small-business demo."""
import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from relationalai.config import SnowflakeConnection, create_config

ROOT = Path(__file__).resolve().parent
SCHEMA = 'ALAA_DEMO_DATA.SMB_PURCHASING'
SNAPSHOT = date(2026, 10, 12)
END = SNAPSHOT + timedelta(days=30)
SCENARIO = 'smb_purchasing_20261012_v1'
PRODUCT_NAMES = [
    'Nitrile gloves', 'Safety glasses', 'Dust masks', 'Ear plugs', 'Work gloves',
    'Packing tape', 'Stretch film', 'Shipping labels', 'Small cartons', 'Large cartons',
    'M6 bolts', 'M8 bolts', 'M6 nuts', 'M8 nuts', 'Flat washers',
    'Cable ties', 'Electrical tape', 'Extension leads', 'LED bulbs', 'AA batteries',
    'Air filters', 'Water filters', 'Cleaning wipes', 'Hand soap', 'Paper towels',
    'Marker pens', 'Utility knives', 'Replacement blades', 'Measuring tapes', 'Shop brushes',
]


def generate(source_ids):
    if len(source_ids) != 30 or len(set(source_ids)) != 30:
        raise ValueError('Thirty distinct source SKU references are required')
    common = dict(IS_SYNTHETIC=1, SCENARIO_ID=SCENARIO, SNAPSHOT_DATE=SNAPSHOT)
    products, inventory, receipts, offers = [], [], [], []
    suppliers = [dict(SUPPLIER_ID=i+1, NAME=name, **common) for i, name in enumerate([
        'Demo Regional Supply', 'Demo Value Wholesale',
        'Demo Express Industrial', 'Demo Specialty Distribution'])]
    warehouse = [dict(WAREHOUSE_ID=1, NAME='Demo Main Warehouse', **common)]
    for i, source_id in enumerate(source_ids):
        pid = i + 1
        category = ['Safety', 'Packaging', 'Fasteners', 'Electrical', 'Maintenance', 'Tools'][i // 5]
        demand = 60 + (i * 37) % 190
        onhand = 25 + (i * 29) % 110
        reserved = 5 + i % 16
        safety = max(12, math.ceil(demand * 0.15))
        early_demand = 35 if pid == 1 else 0
        products.append(dict(PRODUCT_ID=pid, SOURCE_SKU=int(source_id),
                             NAME=PRODUCT_NAMES[i], CATEGORY=category, BASE_UNIT='piece',
                             SAFETY_STOCK_QTY=safety, **common))
        inventory.append(dict(PRODUCT_ID=pid, WAREHOUSE_ID=1, ON_HAND_QTY=onhand,
                              RESERVED_QTY=reserved, **common))
        # Remaining demand excludes orders already allocated against reserved stock.
        # One confirmed early obligation is deliberately visible as a buyer exception.
        for supplier in range(1, 5):
            if supplier > 1 and (i + supplier) % 3 == 0:
                continue
            pack = [6, 12, 10, 5][supplier-1]
            lead = [12, 22, 4, 35][supplier-1]
            if pid == 2:
                lead = 40  # No on-time option: expose unavoidable shortfall.
            if pid == 3 and supplier == 1:
                lead = -1  # Explicit missing lead-time sentinel; never treat as zero.
            approved = int(not (pid == 4 and supplier == 2))
            capacity = 60 + ((i * 19 + supplier * 31) % 180)
            unit_cost = 180 + (i * 71) % 1800 + [100, 0, 240, -30][supplier-1]
            moq = [24, 48, 10, 20][supplier-1]
            arrival = SNAPSHOT + timedelta(days=lead) if lead >= 0 else None
            eligible = approved == 1 and arrival is not None and arrival <= END
            max_packs = capacity // pack if eligible else 0
            min_packs = math.ceil(moq / pack)
            if max_packs < min_packs:
                max_packs = 0
            reason = ('not approved' if not approved else 'missing lead time' if lead < 0
                      else 'arrives after planning window' if arrival > END
                      else 'capacity below minimum order' if max_packs == 0 else 'eligible')
            offers.append(dict(OFFER_ID=len(offers)+1, PRODUCT_ID=pid, SUPPLIER_ID=supplier,
                               UNIT_COST_CENTS=unit_cost, FREIGHT_CENTS_PER_UNIT=25 if supplier != 3 else 60,
                               CURRENCY='USD', PACK_SIZE=pack, MINIMUM_ORDER_QTY=moq,
                               CONFIRMED_CAPACITY_QTY=capacity, LEAD_TIME_DAYS=lead,
                               EXPECTED_ARRIVAL_DATE=arrival, IS_APPROVED=approved,
                               ELIGIBLE_PACKS=max_packs, ELIGIBILITY_REASON=reason, **common))
        if i % 2 == 0:
            receipts.append(dict(ORDER_ID=len(receipts)+1, PRODUCT_ID=pid, SUPPLIER_ID=1,
                                 QUANTITY=12 + i % 4 * 6, EXPECTED_RECEIPT_DATE=SNAPSHOT+timedelta(days=8),
                                 STATUS='confirmed', **common))
        if i % 5 == 0:
            receipts.append(dict(ORDER_ID=len(receipts)+1, PRODUCT_ID=pid, SUPPLIER_ID=1,
                                 QUANTITY=24, EXPECTED_RECEIPT_DATE=SNAPSHOT+timedelta(days=38),
                                 STATUS='confirmed', **common))
        if i % 7 == 0:
            receipts.append(dict(ORDER_ID=len(receipts)+1, PRODUCT_ID=pid, SUPPLIER_ID=1,
                                 QUANTITY=18, EXPECTED_RECEIPT_DATE=SNAPSHOT-timedelta(days=3),
                                 STATUS='confirmed', **common))
        if i % 9 == 0:
            receipts.append(dict(ORDER_ID=len(receipts)+1, PRODUCT_ID=pid, SUPPLIER_ID=1,
                                 QUANTITY=30, EXPECTED_RECEIPT_DATE=SNAPSHOT+timedelta(days=5),
                                 STATUS='cancelled', **common))
        products[-1].update(_demand=demand, _early_demand=early_demand)
    for r in receipts:
        eligible = r['STATUS'] == 'confirmed' and SNAPSHOT < r['EXPECTED_RECEIPT_DATE'] <= END
        r.update(COUNTED_QTY=r['QUANTITY'] if eligible else 0,
                 EXCLUSION_REASON='counted' if eligible else 'cancelled' if r['STATUS'] != 'confirmed'
                 else 'overdue; arrival requires reconfirmation' if r['EXPECTED_RECEIPT_DATE'] <= SNAPSHOT
                 else 'arrives after planning window')
    needs = []
    for p, stock in zip(products, inventory):
        pid = p['PRODUCT_ID']
        available = stock['ON_HAND_QTY']-stock['RESERVED_QTY']
        incoming = sum(r['COUNTED_QTY'] for r in receipts if r['PRODUCT_ID'] == pid)
        demand = p.pop('_demand')
        early = p.pop('_early_demand')
        required = max(0, demand+p['SAFETY_STOCK_QTY']-available-incoming)
        max_supply = sum(o['ELIGIBLE_PACKS']*o['PACK_SIZE'] for o in offers if o['PRODUCT_ID'] == pid)
        early_date = SNAPSHOT+timedelta(days=3)
        early_supply = available + sum(r['COUNTED_QTY'] for r in receipts
                                       if r['PRODUCT_ID'] == pid and r['EXPECTED_RECEIPT_DATE'] <= early_date)
        early_supply += sum(o['ELIGIBLE_PACKS']*o['PACK_SIZE'] for o in offers
                            if o['PRODUCT_ID'] == pid and o['EXPECTED_ARRIVAL_DATE'] is not None
                            and o['EXPECTED_ARRIVAL_DATE'] <= early_date)
        needs.append(dict(PRODUCT_ID=pid, WAREHOUSE_ID=1, WINDOW_END=END,
                          REMAINING_DEMAND_QTY=demand, AVAILABLE_QTY=available,
                          COUNTED_RECEIPTS_QTY=incoming, REQUIRED_QTY=required,
                          UNAVOIDABLE_SHORTFALL_QTY=max(0, required-max_supply),
                          EARLY_DUE_DATE=early_date, EARLY_DEMAND_QTY=early,
                          EARLY_SHORTFALL_QTY=max(0, early-early_supply), **common))
    return {'products': products, 'suppliers': suppliers, 'warehouses': warehouse,
            'inventory': inventory, 'incoming_orders': receipts, 'offers': offers, 'needs': needs}


def validate_inputs(data):
    products = {p['PRODUCT_ID'] for p in data['products']}
    suppliers = {s['SUPPLIER_ID'] for s in data['suppliers']}
    assert len(products) == 30 and len(suppliers) == 4 and len(data['warehouses']) == 1
    assert len(data['needs']) == len(data['inventory']) == len(products)
    for key, identity in [('products','PRODUCT_ID'),('suppliers','SUPPLIER_ID'),
                          ('warehouses','WAREHOUSE_ID'),('inventory','PRODUCT_ID'),
                          ('offers','OFFER_ID'),('incoming_orders','ORDER_ID'),('needs','PRODUCT_ID')]:
        assert len({r[identity] for r in data[key]}) == len(data[key])
        assert all(r['IS_SYNTHETIC']==1 and r['SCENARIO_ID']==SCENARIO
                   and r['SNAPSHOT_DATE']==SNAPSHOT for r in data[key])
    for s in data['inventory']:
        assert s['PRODUCT_ID'] in products and 0 <= s['RESERVED_QTY'] <= s['ON_HAND_QTY']
    for o in data['offers']:
        assert o['PRODUCT_ID'] in products and o['SUPPLIER_ID'] in suppliers
        assert o['PACK_SIZE'] > 0 and o['MINIMUM_ORDER_QTY'] > 0 and o['UNIT_COST_CENTS'] > 0
        assert o['CONFIRMED_CAPACITY_QTY'] >= 0
        arrival = SNAPSHOT+timedelta(days=o['LEAD_TIME_DAYS']) if o['LEAD_TIME_DAYS']>=0 else None
        assert o['EXPECTED_ARRIVAL_DATE'] == arrival
        capacity_packs = o['CONFIRMED_CAPACITY_QTY']//o['PACK_SIZE']
        expected = capacity_packs if o['IS_APPROVED']==1 and arrival is not None and arrival<=END \
                   and capacity_packs*o['PACK_SIZE']>=o['MINIMUM_ORDER_QTY'] else 0
        assert o['ELIGIBLE_PACKS']==expected
        if o['ELIGIBLE_PACKS']:
            assert o['IS_APPROVED'] == 1 and o['LEAD_TIME_DAYS'] >= 0
            assert SNAPSHOT <= o['EXPECTED_ARRIVAL_DATE'] <= END
            assert o['ELIGIBLE_PACKS']*o['PACK_SIZE'] <= o['CONFIRMED_CAPACITY_QTY']
    for r in data['incoming_orders']:
        assert r['PRODUCT_ID'] in products and r['SUPPLIER_ID'] in suppliers and r['QUANTITY'] > 0
        assert r['COUNTED_QTY'] == (r['QUANTITY'] if r['STATUS'] == 'confirmed'
                                   and SNAPSHOT < r['EXPECTED_RECEIPT_DATE'] <= END else 0)
    for n in data['needs']:
        p = next(p for p in data['products'] if p['PRODUCT_ID'] == n['PRODUCT_ID'])
        stock = next(s for s in data['inventory'] if s['PRODUCT_ID'] == n['PRODUCT_ID'])
        assert n['AVAILABLE_QTY'] == stock['ON_HAND_QTY']-stock['RESERVED_QTY']
        incoming = sum(r['COUNTED_QTY'] for r in data['incoming_orders'] if r['PRODUCT_ID'] == n['PRODUCT_ID'])
        assert n['COUNTED_RECEIPTS_QTY'] == incoming
        assert n['REQUIRED_QTY'] == max(0,n['REMAINING_DEMAND_QTY']+p['SAFETY_STOCK_QTY']-n['AVAILABLE_QTY']-incoming)
        max_supply = sum(o['ELIGIBLE_PACKS']*o['PACK_SIZE'] for o in data['offers'] if o['PRODUCT_ID']==n['PRODUCT_ID'])
        assert n['UNAVOIDABLE_SHORTFALL_QTY']==max(0,n['REQUIRED_QTY']-max_supply)
        assert 0<=n['EARLY_DEMAND_QTY']<=n['REMAINING_DEMAND_QTY']
    print('Input identities, quantities, receipt dates and offer eligibility verified', flush=True)


def oracle_cost(data, product_id, target):
    """Exact independent dynamic program over valid pack orders, including MOQs."""
    states = {0: 0}
    for o in data['offers']:
        if o['PRODUCT_ID'] != product_id:
            continue
        minimum = math.ceil(o['MINIMUM_ORDER_QTY']/o['PACK_SIZE'])
        quantities = [0] + [packs*o['PACK_SIZE'] for packs in range(minimum, o['ELIGIBLE_PACKS']+1)]
        nxt = {}
        for previous, cost in states.items():
            for qty in quantities:
                # All excess over target is equivalent for future nonnegative costs.
                total = min(target, previous+qty)
                value = cost + qty*(o['UNIT_COST_CENTS']+o['FREIGHT_CENTS_PER_UNIT'])
                nxt[total] = min(nxt.get(total, value), value)
        states = nxt
    return states[target]


def solve(data):
    from relationalai.semantics import Model, Integer, Float, inspect
    from relationalai.semantics.std import aggregates as aggs
    from relationalai.semantics.reasoners.prescriptive import Problem
    config = create_config()
    config.deployment = None
    m = Model('SMBPurchasingSolve', config=config)
    need = m.Concept('Need', identify_by={'id': Integer})
    offer = m.Concept('Offer', identify_by={'id': Integer})
    for c, fields in [(need, ['required', 'shortfall']),
                      (offer, ['product_id', 'pack', 'min_packs', 'max_packs', 'cost'])]:
        for field in fields:
            setattr(c, field, m.Property(f'{c} has {Float:{field}}'))
    m.define(need.new(m.data([dict(id=n['PRODUCT_ID'], required=float(n['REQUIRED_QTY']),
                                 shortfall=float(n['UNAVOIDABLE_SHORTFALL_QTY'])) for n in data['needs']]).to_schema()))
    m.define(offer.new(m.data([dict(id=o['OFFER_ID'], product_id=float(o['PRODUCT_ID']),
                                  pack=float(o['PACK_SIZE']), min_packs=float(math.ceil(o['MINIMUM_ORDER_QTY']/o['PACK_SIZE'])),
                                  max_packs=float(o['ELIGIBLE_PACKS']),
                                  cost=float(o['UNIT_COST_CENTS']+o['FREIGHT_CENTS_PER_UNIT']))
                                 for o in data['offers']]).to_schema()))
    offer.packs = m.Property(f'{offer} orders {Float:packs} packs')
    offer.used = m.Property(f'{offer} has {Float:used} activation')
    print(inspect.schema(m), flush=True)
    problem = Problem(m, Float)
    packs = problem.solve_for(offer.packs, type='int', lower=0, upper=offer.max_packs, name=['packs', offer.id])
    problem.solve_for(offer.used, type='bin', lower=0, upper=1, name=['active', offer.id])
    quantity = aggs.sum(offer.packs*offer.pack).per(need).where(offer.product_id == need.id)
    requirements = [m.require(quantity+need.shortfall >= need.required),
                    m.require(offer.packs <= offer.max_packs*offer.used),
                    m.require(offer.packs >= offer.min_packs*offer.used)]
    coverage = problem.satisfy(requirements[0], name=['coverage', need.id])
    problem.satisfy(requirements[1], name=['capacity', offer.id])
    problem.satisfy(requirements[2], name=['moq', offer.id])
    problem.minimize(aggs.sum(offer.packs*offer.pack*offer.cost))
    assert len(m.select(packs).to_df()) == len(data['offers'])
    assert len(m.select(coverage).to_df()) == 30
    problem.solve('highs', time_limit_sec=120, relative_gap_tolerance=0.0)
    info = problem.solve_info()
    info.display()
    if info.termination_status != 'OPTIMAL':
        raise RuntimeError(f'{info.termination_status}: {info.error}')
    problem.verify(*requirements)
    rows = m.where(offer.packs > 0.5).select(offer.id.alias('offer_id'), offer.packs.alias('packs')).to_df().to_dict('records')
    for r in rows:
        assert abs(float(r['packs'])-round(float(r['packs']))) < 1e-6
    result = dict(status=info.termination_status, objective_cents=int(round(info.objective_value)),
                  solver_version=str(info.solver_version), orders=[dict(offer_id=int(r['offer_id']), packs=int(round(float(r['packs'])))) for r in rows])
    return result


def lowest_price_first(data):
    """Greedy landed-price ordering; round packs up to MOQ and use capacity first."""
    orders = []
    for n in data['needs']:
        remaining = n['REQUIRED_QTY']-n['UNAVOIDABLE_SHORTFALL_QTY']
        eligible = sorted((o for o in data['offers'] if o['PRODUCT_ID']==n['PRODUCT_ID'] and o['ELIGIBLE_PACKS']>0),
                          key=lambda o: (o['UNIT_COST_CENTS']+o['FREIGHT_CENTS_PER_UNIT'],o['SUPPLIER_ID'],o['OFFER_ID']))
        for o in eligible:
            if remaining<=0:
                break
            packs = min(o['ELIGIBLE_PACKS'], max(math.ceil(o['MINIMUM_ORDER_QTY']/o['PACK_SIZE']),
                                                 math.ceil(remaining/o['PACK_SIZE'])))
            qty = packs*o['PACK_SIZE']
            orders.append(dict(ACTION_ID=len(orders)+1, PRODUCT_ID=o['PRODUCT_ID'],
                               SUPPLIER_ID=o['SUPPLIER_ID'], OFFER_ID=o['OFFER_ID'],
                               QUANTITY=qty, PACK_COUNT=packs,
                               LANDED_UNIT_COST_CENTS=o['UNIT_COST_CENTS']+o['FREIGHT_CENTS_PER_UNIT'],
                               TOTAL_COST_CENTS=qty*(o['UNIT_COST_CENTS']+o['FREIGHT_CENTS_PER_UNIT']),
                               EXPECTED_ARRIVAL_DATE=o['EXPECTED_ARRIVAL_DATE'],
                               IS_SYNTHETIC=1, SCENARIO_ID=SCENARIO, SNAPSHOT_DATE=SNAPSHOT))
            remaining -= qty
        assert remaining<=0, ('baseline cannot reach achievable coverage',n['PRODUCT_ID'])
    return orders


def evaluate_orders(data, orders):
    """Validate a candidate strategy against the same inputs and reconstruct its balances."""
    offers = {o['OFFER_ID']:o for o in data['offers']}
    quantities, costs = defaultdict(int), defaultdict(int)
    seen = set()
    for a in orders:
        o = offers[a['OFFER_ID']]
        assert a['OFFER_ID'] not in seen
        seen.add(a['OFFER_ID'])
        assert isinstance(a['PACK_COUNT'],int) and 0<a['PACK_COUNT']<=o['ELIGIBLE_PACKS']
        assert a['QUANTITY']==a['PACK_COUNT']*o['PACK_SIZE']
        assert o['MINIMUM_ORDER_QTY']<=a['QUANTITY']<=o['CONFIRMED_CAPACITY_QTY']
        assert a['PRODUCT_ID']==o['PRODUCT_ID'] and a['SUPPLIER_ID']==o['SUPPLIER_ID']
        assert a['EXPECTED_ARRIVAL_DATE']==o['EXPECTED_ARRIVAL_DATE'] and SNAPSHOT<=a['EXPECTED_ARRIVAL_DATE']<=END
        landed = o['UNIT_COST_CENTS']+o['FREIGHT_CENTS_PER_UNIT']
        assert a['LANDED_UNIT_COST_CENTS']==landed and a['TOTAL_COST_CENTS']==a['QUANTITY']*landed
        quantities[o['PRODUCT_ID']] += a['QUANTITY']
        costs[o['PRODUCT_ID']] += a['TOTAL_COST_CENTS']
    products = {p['PRODUCT_ID']:p for p in data['products']}
    rows = []
    for n in data['needs']:
        pid = n['PRODUCT_ID']
        assert quantities[pid]>=n['REQUIRED_QTY']-n['UNAVOIDABLE_SHORTFALL_QTY']
        ending = n['AVAILABLE_QTY']+n['COUNTED_RECEIPTS_QTY']+quantities[pid]-n['REMAINING_DEMAND_QTY']
        demand_shortfall = max(0,-ending)
        safety_shortfall = max(0,products[pid]['SAFETY_STOCK_QTY']-max(0,ending))
        assert demand_shortfall+safety_shortfall==n['UNAVOIDABLE_SHORTFALL_QTY']
        rows.append(dict(PRODUCT_ID=pid,PURCHASE_QTY=quantities[pid],TOTAL_COST_CENTS=costs[pid],
                         DEMAND_SHORTFALL_QTY=demand_shortfall,SAFETY_SHORTFALL_QTY=safety_shortfall,
                         EXCESS_ABOVE_TARGET_QTY=max(0,ending-products[pid]['SAFETY_STOCK_QTY'])))
    return rows


def add_baseline(data):
    baseline_orders = lowest_price_first(data)
    baseline = evaluate_orders(data,baseline_orders)
    optimized = evaluate_orders(data,data['recommendations'])
    for b,o in zip(baseline,optimized):
        assert b['PRODUCT_ID']==o['PRODUCT_ID'] and b['TOTAL_COST_CENTS']>=o['TOTAL_COST_CENTS']
        assert b['DEMAND_SHORTFALL_QTY']==o['DEMAND_SHORTFALL_QTY']
        assert b['SAFETY_SHORTFALL_QTY']==o['SAFETY_SHORTFALL_QTY']
    def total(rows,key): return sum(r[key] for r in rows)
    base_cost = total(baseline,'TOTAL_COST_CENTS')
    opt_cost = total(optimized,'TOTAL_COST_CENTS')
    assert opt_cost==data['plans'][0]['TOTAL_COST_CENTS']
    data['baseline_orders'] = baseline_orders
    data['comparisons'] = [dict(COMPARISON_ID=1,PLAN_ID=1,BASELINE_STRATEGY='Lowest landed price first',
        BASELINE_STATUS='FEASIBLE_AT_MAXIMUM_COVERAGE',CURRENCY='USD',WINDOW_END=END,
        BASELINE_COST_CENTS=base_cost,OPTIMIZED_COST_CENTS=opt_cost,SAVINGS_CENTS=base_cost-opt_cost,
        BASELINE_PURCHASE_QTY=total(baseline,'PURCHASE_QTY'),OPTIMIZED_PURCHASE_QTY=total(optimized,'PURCHASE_QTY'),
        BASELINE_DEMAND_SHORTFALL_QTY=total(baseline,'DEMAND_SHORTFALL_QTY'),
        OPTIMIZED_DEMAND_SHORTFALL_QTY=total(optimized,'DEMAND_SHORTFALL_QTY'),
        BASELINE_SAFETY_SHORTFALL_QTY=total(baseline,'SAFETY_SHORTFALL_QTY'),
        OPTIMIZED_SAFETY_SHORTFALL_QTY=total(optimized,'SAFETY_SHORTFALL_QTY'),
        BASELINE_EXCESS_QTY=total(baseline,'EXCESS_ABOVE_TARGET_QTY'),OPTIMIZED_EXCESS_QTY=total(optimized,'EXCESS_ABOVE_TARGET_QTY'),
        PRODUCTS_WITH_SAVINGS=sum(b['TOTAL_COST_CENTS']>o['TOTAL_COST_CENTS'] for b,o in zip(baseline,optimized)),
        IS_SYNTHETIC=1,SCENARIO_ID=SCENARIO,SNAPSHOT_DATE=SNAPSHOT)]
    # Product-level audit is local; order-level baseline is also published to Snowflake.
    audit = [dict(PRODUCT_ID=b['PRODUCT_ID'],BASELINE_COST_CENTS=b['TOTAL_COST_CENTS'],
                  OPTIMIZED_COST_CENTS=o['TOTAL_COST_CENTS'],SAVINGS_CENTS=b['TOTAL_COST_CENTS']-o['TOTAL_COST_CENTS'],
                  BASELINE_PURCHASE_QTY=b['PURCHASE_QTY'],OPTIMIZED_PURCHASE_QTY=o['PURCHASE_QTY'])
             for b,o in zip(baseline,optimized)]
    (ROOT/'data/smb_baseline_product_comparison.json').write_text(json.dumps(audit,indent=2)+'\n')
    print('Price-first baseline validated: same per-product coverage; costs reconstructed',flush=True)


def finish(data, result):
    validate_inputs(data)
    offers = {o['OFFER_ID']: o for o in data['offers']}
    quantities, costs = defaultdict(int), defaultdict(int)
    recommendations = []
    for action in result['orders']:
        o = offers[action['offer_id']]
        packs = action['packs']
        qty = packs*o['PACK_SIZE']
        assert 0 < packs <= o['ELIGIBLE_PACKS'] and qty >= o['MINIMUM_ORDER_QTY']
        cost = qty*(o['UNIT_COST_CENTS']+o['FREIGHT_CENTS_PER_UNIT'])
        quantities[o['PRODUCT_ID']] += qty
        costs[o['PRODUCT_ID']] += cost
        recommendations.append(dict(ACTION_ID=len(recommendations)+1, PLAN_ID=1,
                                    PRODUCT_ID=o['PRODUCT_ID'], SUPPLIER_ID=o['SUPPLIER_ID'], OFFER_ID=o['OFFER_ID'],
                                    QUANTITY=qty, PACK_COUNT=packs, LANDED_UNIT_COST_CENTS=o['UNIT_COST_CENTS']+o['FREIGHT_CENTS_PER_UNIT'],
                                    TOTAL_COST_CENTS=cost, EXPECTED_ARRIVAL_DATE=o['EXPECTED_ARRIVAL_DATE'],
                                    REASON='Lowest cost; pack/MOQ validated',
                                    IS_SYNTHETIC=1, SCENARIO_ID=SCENARIO, SNAPSHOT_DATE=SNAPSHOT))
    for n in data['needs']:
        pid = n['PRODUCT_ID']
        target = n['REQUIRED_QTY']-n['UNAVOIDABLE_SHORTFALL_QTY']
        assert quantities[pid] >= target
        assert costs[pid] == oracle_cost(data, pid, target), ('nonoptimal', pid)
        p = next(p for p in data['products'] if p['PRODUCT_ID'] == pid)
        ending = n['AVAILABLE_QTY']+n['COUNTED_RECEIPTS_QTY']+quantities[pid]-n['REMAINING_DEMAND_QTY']
        demand_shortfall = max(0, -ending)
        safety_shortfall = max(0,p['SAFETY_STOCK_QTY']-max(0,ending))
        notes = []
        if n['EARLY_SHORTFALL_QTY']:
            notes.append(f"Early obligation: {n['EARLY_SHORTFALL_QTY']} units cannot arrive by {n['EARLY_DUE_DATE']}; buyer must expedite or revise commitment")
        if n['UNAVOIDABLE_SHORTFALL_QTY']:
            notes.append('Insufficient approved on-time supplier capacity; buyer intervention required')
        if any(r['PRODUCT_ID']==pid and 'overdue' in r['EXCLUSION_REASON'] for r in data['incoming_orders']):
            notes.append('Overdue incoming order excluded until arrival is reconfirmed')
        n.update(PURCHASE_QTY=quantities[pid], TOTAL_COST_CENTS=costs[pid], PROJECTED_ENDING_QTY=ending,
                 DEMAND_SHORTFALL_QTY=demand_shortfall, SAFETY_SHORTFALL_QTY=safety_shortfall,
                 EXCESS_ABOVE_TARGET_QTY=max(0, ending-p['SAFETY_STOCK_QTY']),
                 BUYER_EXCEPTION='; '.join(notes) or 'none')
        assert demand_shortfall+safety_shortfall == n['UNAVOIDABLE_SHORTFALL_QTY']
    assert sum(costs.values()) == result['objective_cents']
    data['recommendations'] = recommendations
    data['plans'] = [dict(PLAN_ID=1, NAME='30-day purchasing plan', STATUS=result['status'],
                         SOLVER_VERSION=result['solver_version'], CURRENCY='USD', WINDOW_END=END,
                         PRODUCT_COUNT=30, SUPPLIER_COUNT=4, WAREHOUSE_COUNT=1,
                         TOTAL_COST_CENTS=result['objective_cents'], PURCHASE_QTY=sum(quantities.values()),
                         DEMAND_SHORTFALL_QTY=sum(n['DEMAND_SHORTFALL_QTY'] for n in data['needs']),
                         SAFETY_SHORTFALL_QTY=sum(n['SAFETY_SHORTFALL_QTY'] for n in data['needs']),
                         EXCEPTION_PRODUCT_COUNT=sum(n['BUYER_EXCEPTION']!='none' for n in data['needs']),
                         IS_SYNTHETIC=1, SCENARIO_ID=SCENARIO, SNAPSHOT_DATE=SNAPSHOT)]
    print('Independent exact cost oracle, pack/MOQ/capacity and balances verified for all 30 products', flush=True)
    add_baseline(data)


TABLES = {'products': 'SMB_PRODUCTS_V1', 'suppliers': 'SMB_SUPPLIERS_V1', 'warehouses': 'SMB_WAREHOUSES_V1',
          'inventory': 'SMB_INVENTORY_V1', 'incoming_orders': 'SMB_INCOMING_ORDERS_V1', 'offers': 'SMB_OFFERS_V1',
          'needs': 'SMB_NEEDS_V1', 'recommendations': 'SMB_RECOMMENDATIONS_V1', 'plans': 'SMB_PLANS_V1',
          'baseline_orders': 'SMB_BASELINE_ORDERS_V1', 'comparisons': 'SMB_COMPARISONS_V1'}


def publish(session, data):
    from snowflake.snowpark.types import StructType, StructField, LongType, StringType, DateType
    session.sql(f'CREATE SCHEMA IF NOT EXISTS {SCHEMA}').collect()
    session.use_database('ALAA_DEMO_DATA')
    session.use_schema('SMB_PURCHASING')
    # Stage every validated table first. Source activation occurs only after all writes succeed.
    for key, name in TABLES.items():
        rows = data[key]
        columns = list(rows[0])
        def field_type(column):
            sample = next((r[column] for r in rows if r[column] is not None), None)
            return DateType() if isinstance(sample,date) else StringType() if isinstance(sample,str) else LongType()
        schema = StructType([StructField(c,field_type(c),nullable=True) for c in columns])
        session.create_dataframe([[r[c] for c in columns] for r in rows], schema=schema).write.mode('overwrite').save_as_table(f'{SCHEMA}.{name}_STAGED')
        count = session.sql(f'SELECT COUNT(*) FROM {SCHEMA}.{name}_STAGED').collect()[0][0]
        assert count == len(rows)
        with (ROOT/'data'/f'{name.lower()}.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();writer.writerows(rows)
    for name in TABLES.values():
        session.sql(f'CREATE OR REPLACE TABLE {SCHEMA}.{name} CLONE {SCHEMA}.{name}_STAGED').collect()
        session.sql(f'ALTER TABLE {SCHEMA}.{name} SET CHANGE_TRACKING=TRUE').collect()
        print('Published',name,flush=True)


def restore_dates(value):
    if isinstance(value, list): return [restore_dates(v) for v in value]
    if isinstance(value, dict): return {k: date.fromisoformat(v) if k.endswith('DATE') or k=='WINDOW_END' else restore_dates(v)
                                      for k,v in value.items() if v is not None} | {k:None for k,v in value.items() if v is None}
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    parser.add_argument('--publish-saved', action='store_true')
    args = parser.parse_args()
    session = create_config().get_session(SnowflakeConnection)
    try:
        if args.publish_saved:
            artifact = json.loads((ROOT/'data/smb_purchasing_results.json').read_text())
            data, result = restore_dates(artifact['data']), artifact['solve']
            assert result['status'] == 'OPTIMAL'
        else:
            ids = [int(r[0]) for r in session.sql('SELECT SKU FROM ALAA_DEMO_DATA.SUPPLY_CHAIN.BACKORDERS WHERE NATIONAL_INV>=0 AND FORECAST_3_MONTH>0 ORDER BY SKU LIMIT 30').collect()]
            data = generate(ids)
            validate_inputs(data)
            result = solve(data)
        finish(data,result)
        (ROOT/'data/smb_purchasing_results.json').write_text(json.dumps(dict(data=data,solve=result),indent=2,default=str)+'\n')
        print(json.dumps(data['plans'], default=str),flush=True)
        if args.publish or args.publish_saved:
            publish(session,data)
    finally:
        session.close()


if __name__ == '__main__':
    main()

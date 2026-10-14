"""Template-style prescriptive problem over the shared purchasing ontology.

The Retail Planning template separates named decisions, coverage constraints,
objective, solve, and ontology-native extraction. This module follows that flow.
"""
from collections import defaultdict
from relationalai.config import create_config
from relationalai.semantics import Float, inspect
from relationalai.semantics.std import aggregates as aggs
from relationalai.semantics.reasoners.prescriptive import Problem
from purchasing_ontology import build_ontology


def formulate(ontology):
    """Register whole-pack orders on SupplierOffer and coverage on Product."""
    model = ontology.model
    offer, need = ontology.SupplierOffer, ontology.Product
    offer.order_active = model.Property(f'{offer} has {Float:order_active} order activation')
    problem = Problem(model, Float)
    packs = problem.solve_for(offer.order_packs, type='int', lower=0,
                              upper=offer.eligible_packs, name=['packs',offer.offer_id])
    problem.solve_for(offer.order_active, type='bin', lower=0, upper=1,
                      name=['active',offer.offer_id])
    # Typed product links replace the old copied Float product IDs.
    bought = aggs.sum(offer.order_packs*offer.pack_size).per(need).where(offer.product == need)
    requirements = [
        model.require(bought+need.unavoidable_shortfall_qty >= need.required_qty),
        model.require(offer.order_packs <= offer.eligible_packs*offer.order_active),
        model.require(offer.order_packs >= offer.minimum_packs*offer.order_active),
    ]
    coverage = problem.satisfy(requirements[0],name=['coverage',need.product_id])
    problem.satisfy(requirements[1],name=['capacity',offer.offer_id])
    problem.satisfy(requirements[2],name=['minimum_order',offer.offer_id])
    problem.minimize(aggs.sum(offer.order_packs*offer.pack_size*offer.landed_unit_cost_cents))
    return problem, requirements, packs, coverage


def solve_purchasing(data, *, config=None, recompute_inputs=False):
    config = (config or create_config()).model_copy(deep=True)
    config.deployment = None
    ontology = build_ontology(name='PurchasingOptimization',config=config,data=data,
                             include_results=False,recompute_inputs=recompute_inputs)
    model, offer = ontology.model, ontology.SupplierOffer
    print(inspect.schema(model),flush=True)
    problem, requirements, packs, coverage = formulate(ontology)
    actual_packs = len(model.select(packs).to_df())
    actual_coverage = len(model.select(coverage).to_df())
    assert actual_packs==len(data['offers']),('order variable population',actual_packs,len(data['offers']))
    assert actual_coverage==len(data['needs']),('coverage population',actual_coverage,len(data['needs']))
    problem.solve('highs',time_limit_sec=120,relative_gap_tolerance=0.0)
    info = problem.solve_info()
    info.display()
    if info.termination_status!='OPTIMAL':
        raise RuntimeError(f'{info.termination_status}: {info.error}')
    # Read the actual ontology-native solution and coefficients. PyRel 1.35's
    # temporary-IC verifier cannot ground this derived target; explicit readback
    # also avoids its documented set-versus-bag aggregate ambiguity.
    rows = model.select(offer.offer_id.alias('offer_id'),offer.product.product_id.alias('product_id'),
        offer.order_packs.alias('packs'),offer.order_active.alias('active'),
        offer.eligible_packs.alias('capacity'),offer.minimum_packs.alias('minimum'),
        offer.pack_size.alias('pack_size'),offer.landed_unit_cost_cents.alias('cost')).to_df().to_dict('records')
    assert len(rows)==len(data['offers'])
    bought, cost = defaultdict(int), 0
    for row in rows:
        packs=int(round(float(row['packs'])));active=int(round(float(row['active'])))
        assert abs(float(row['packs'])-packs)<1e-6 and abs(float(row['active'])-active)<1e-6
        assert active in (0,1) and 0<=packs<=int(row['capacity'])*active
        assert packs>=int(row['minimum'])*active
        quantity=packs*int(row['pack_size'])
        bought[int(row['product_id'])]+=quantity
        cost+=quantity*int(row['cost'])
    targets=model.select(ontology.Product.product_id.alias('product_id'),
        ontology.Product.required_qty.alias('required'),
        ontology.Product.unavoidable_shortfall_qty.alias('shortfall')).to_df().to_dict('records')
    expected={n['PRODUCT_ID']:n for n in data['needs']}
    assert len(targets)==len(expected) and {int(t['product_id']) for t in targets}==set(expected)
    for target in targets:
        pid=int(target['product_id'])
        assert int(target['required'])==expected[pid]['REQUIRED_QTY']
        assert int(target['shortfall'])==expected[pid]['UNAVOIDABLE_SHORTFALL_QTY']
        assert bought[pid]+int(target['shortfall'])>=int(target['required'])
    assert cost==int(round(info.objective_value))
    print('Ontology readback verified all pack/activation/capacity/MOQ decisions and derived coverage targets',flush=True)
    return dict(status=info.termination_status,objective_cents=int(round(info.objective_value)),
                solver_version=str(info.solver_version),
                verification='ontology_readback_and_independent_oracle',
                orders=[dict(offer_id=int(row['offer_id']),packs=int(round(float(row['packs']))))
                        for row in rows if float(row['packs'])>0.5])

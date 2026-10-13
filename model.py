"""One-warehouse purchasing ontology backed by a validated synthetic snapshot."""
from relationalai.semantics import Model, Integer, String, Date

# Retain deployment identity while replacing the active planning surface.
model = Model('BackorderDemo')
Product = model.Concept('Product', identify_by={'product_id': Integer})
Supplier = model.Concept('Supplier', identify_by={'supplier_id': Integer})
Warehouse = model.Concept('Warehouse', identify_by={'warehouse_id': Integer})
InventoryPosition = model.Concept('InventoryPosition', identify_by={'product': Product, 'warehouse': Warehouse})
SupplierOffer = model.Concept('SupplierOffer', identify_by={'offer_id': Integer})
IncomingOrder = model.Concept('IncomingOrder', identify_by={'order_id': Integer})
PurchasingNeed = model.Concept('PurchasingNeed', identify_by={'product': Product})
PurchasingPlan = model.Concept('PurchasingPlan', identify_by={'plan_id': Integer})
PurchaseRecommendation = model.Concept('PurchaseRecommendation', identify_by={'action_id': Integer})
PurchasingComparison = model.Concept('PurchasingComparison', identify_by={'comparison_id': Integer})

PROVENANCE = {'is_synthetic': Integer, 'scenario_id': String, 'snapshot_date': Date}
SCHEMA = 'ALAA_DEMO_DATA.SMB_PURCHASING'


def properties(concept, fields):
    for field, type_ in fields.items():
        setattr(concept, field, model.Property(f'{concept} has {type_:{field}}'))


# Each numeric source is NUMBER(38,0); dates are DATE; descriptive fields are TEXT.
DEFINITIONS = [
    (Product, 'SMB_PRODUCTS_V1', 'product_id',
     {'source_sku': Integer, 'name': String, 'category': String, 'base_unit': String, 'safety_stock_qty': Integer}, {}),
    (Supplier, 'SMB_SUPPLIERS_V1', 'supplier_id', {'name': String}, {}),
    (Warehouse, 'SMB_WAREHOUSES_V1', 'warehouse_id', {'name': String}, {}),
    (InventoryPosition, 'SMB_INVENTORY_V1', None, {'on_hand_qty': Integer, 'reserved_qty': Integer},
     {'product': (Product, 'product_id', 'PRODUCT_ID'), 'warehouse': (Warehouse, 'warehouse_id', 'WAREHOUSE_ID')}),
    (SupplierOffer, 'SMB_OFFERS_V1', 'offer_id',
     {'unit_cost_cents': Integer, 'freight_cents_per_unit': Integer, 'currency': String,
      'pack_size': Integer, 'minimum_order_qty': Integer, 'confirmed_capacity_qty': Integer,
      'lead_time_days': Integer, 'expected_arrival_date': Date, 'is_approved': Integer,
      'eligible_packs': Integer, 'eligibility_reason': String},
     {'product': (Product, 'product_id', 'PRODUCT_ID'), 'supplier': (Supplier, 'supplier_id', 'SUPPLIER_ID')}),
    (IncomingOrder, 'SMB_INCOMING_ORDERS_V1', 'order_id',
     {'quantity': Integer, 'expected_receipt_date': Date, 'status': String, 'counted_qty': Integer, 'exclusion_reason': String},
     {'product': (Product, 'product_id', 'PRODUCT_ID'), 'supplier': (Supplier, 'supplier_id', 'SUPPLIER_ID')}),
    (PurchasingNeed, 'SMB_NEEDS_V1', None,
     {'window_end': Date, 'remaining_demand_qty': Integer, 'available_qty': Integer,
      'counted_receipts_qty': Integer, 'required_qty': Integer, 'unavoidable_shortfall_qty': Integer,
      'early_due_date': Date, 'early_demand_qty': Integer, 'early_shortfall_qty': Integer,
      'purchase_qty': Integer, 'total_cost_cents': Integer, 'projected_ending_qty': Integer,
      'demand_shortfall_qty': Integer, 'safety_shortfall_qty': Integer,
      'excess_above_target_qty': Integer, 'buyer_exception': String},
     {'product': (Product, 'product_id', 'PRODUCT_ID'), 'warehouse': (Warehouse, 'warehouse_id', 'WAREHOUSE_ID')}),
    (PurchasingPlan, 'SMB_PLANS_V1', 'plan_id',
     {'name': String, 'status': String, 'solver_version': String, 'currency': String,
      'window_end': Date, 'product_count': Integer, 'supplier_count': Integer, 'warehouse_count': Integer,
      'total_cost_cents': Integer, 'purchase_qty': Integer, 'demand_shortfall_qty': Integer,
      'safety_shortfall_qty': Integer, 'exception_product_count': Integer}, {}),
    (PurchaseRecommendation, 'SMB_RECOMMENDATIONS_V1', 'action_id',
     {'quantity': Integer, 'pack_count': Integer, 'landed_unit_cost_cents': Integer,
      'total_cost_cents': Integer, 'expected_arrival_date': Date, 'reason': String},
     {'product': (Product, 'product_id', 'PRODUCT_ID'), 'supplier': (Supplier, 'supplier_id', 'SUPPLIER_ID'),
      'offer': (SupplierOffer, 'offer_id', 'OFFER_ID'), 'plan': (PurchasingPlan, 'plan_id', 'PLAN_ID')}),
    (PurchasingComparison, 'SMB_COMPARISONS_V1', 'comparison_id',
     {'baseline_strategy': String, 'baseline_status': String, 'currency': String, 'window_end': Date,
      'baseline_cost_cents': Integer, 'optimized_cost_cents': Integer, 'savings_cents': Integer,
      'baseline_purchase_qty': Integer, 'optimized_purchase_qty': Integer,
      'baseline_demand_shortfall_qty': Integer, 'optimized_demand_shortfall_qty': Integer,
      'baseline_safety_shortfall_qty': Integer, 'optimized_safety_shortfall_qty': Integer,
      'baseline_excess_qty': Integer, 'optimized_excess_qty': Integer, 'products_with_savings': Integer},
     {'plan': (PurchasingPlan, 'plan_id', 'PLAN_ID')}),
]
for concept, table, key, fields, links in DEFINITIONS:
    # Compound identity fields already have properties declared by identify_by.
    implicit = {'product', 'warehouse'} if concept is InventoryPosition else {'product'} if concept is PurchasingNeed else set()
    properties(concept, {**fields, **PROVENANCE, **{k: v[0] for k,v in links.items() if k not in implicit}})
for concept, table, key, fields, links in DEFINITIONS:
    fields = {**fields, **PROVENANCE}
    schema = {**{k.upper(): t for k,t in fields.items()}, **{v[2]: Integer for v in links.values()}}
    if key:
        schema[key.upper()] = Integer
    source = model.Table(f'{SCHEMA}.{table}', schema=schema)
    values = {k: source[k.upper()] for k in fields}
    if key:
        values[key] = source[key.upper()]
    values.update({k: target.lookup(**{identity: source[column]}) for k,(target,identity,column) in links.items()})
    model.define(concept.new(**values))

InventoryPosition.available_qty = model.Property(f'{InventoryPosition} has {Integer:available_qty} usable pieces')
model.define(InventoryPosition.available_qty(InventoryPosition.on_hand_qty-InventoryPosition.reserved_qty))
SupplierOffer.landed_unit_cost_cents = model.Property(f'{SupplierOffer} has {Integer:landed_unit_cost_cents} landed USD cents per piece')
model.define(SupplierOffer.landed_unit_cost_cents(SupplierOffer.unit_cost_cents+SupplierOffer.freight_cents_per_unit))

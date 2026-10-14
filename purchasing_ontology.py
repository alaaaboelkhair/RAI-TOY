"""Explicit purchasing ontology: declarations -> source facts -> business rules.

Patterns adapted from the official Retail Planning and Energy Grid templates.
This builder is shared by the deployed model and the prescriptive solver.
"""
from types import SimpleNamespace
from relationalai.semantics import Model, Integer, String, Date, Float
from relationalai.semantics.std import strings, math, aggregates as aggs

from purchasing_sources import SCHEMA, PROVENANCE, SOURCE_SCHEMAS

def build_ontology(*, name="PurchasingAssistant", config=None, data=None, include_results=True,
                   recompute_inputs=False):
    """Bind Snowflake tables, or the identical validated inline snapshot for a solve."""
    if include_results and data is None:
        raise ValueError('Solved decisions must be supplied transiently; saved result tables are not live inputs')
    model = Model(name, config=config)

    # 1. Stable business identities.
    Product = model.Concept('Product', identify_by={'product_id': Integer})
    Supplier = model.Concept('Supplier', identify_by={'supplier_id': Integer})
    Warehouse = model.Concept('Warehouse', identify_by={'warehouse_id': Integer})
    InventoryPosition = model.Concept('InventoryPosition', identify_by={'product': Product, 'warehouse': Warehouse})
    SupplierOffer = model.Concept('SupplierOffer', identify_by={'offer_id': Integer})
    IncomingOrder = model.Concept('IncomingOrder', identify_by={'order_id': Integer})

    # 2. Scalar attributes and functional (many-to-one) business links.
    # Product
    Product.source_sku = model.Property(f"{Product} has {Integer:source_sku}")
    Product.name = model.Property(f"{Product} has {String:name}")
    Product.category = model.Property(f"{Product} has {String:category}")
    Product.base_unit = model.Property(f"{Product} has {String:base_unit}")
    Product.safety_stock_qty = model.Property(f"{Product} has {Integer:safety_stock_qty}")
    Product.is_synthetic = model.Property(f"{Product} has {Integer:is_synthetic}")
    Product.scenario_id = model.Property(f"{Product} has {String:scenario_id}")
    Product.snapshot_date = model.Property(f"{Product} has {Date:snapshot_date}")
    # Supplier
    Supplier.name = model.Property(f"{Supplier} has {String:name}")
    Supplier.is_synthetic = model.Property(f"{Supplier} has {Integer:is_synthetic}")
    Supplier.scenario_id = model.Property(f"{Supplier} has {String:scenario_id}")
    Supplier.snapshot_date = model.Property(f"{Supplier} has {Date:snapshot_date}")
    # Warehouse
    Warehouse.name = model.Property(f"{Warehouse} has {String:name}")
    Warehouse.is_synthetic = model.Property(f"{Warehouse} has {Integer:is_synthetic}")
    Warehouse.scenario_id = model.Property(f"{Warehouse} has {String:scenario_id}")
    Warehouse.snapshot_date = model.Property(f"{Warehouse} has {Date:snapshot_date}")
    # InventoryPosition
    InventoryPosition.on_hand_qty = model.Property(f"{InventoryPosition} has {Integer:on_hand_qty}")
    InventoryPosition.reserved_qty = model.Property(f"{InventoryPosition} has {Integer:reserved_qty}")
    InventoryPosition.is_synthetic = model.Property(f"{InventoryPosition} has {Integer:is_synthetic}")
    InventoryPosition.scenario_id = model.Property(f"{InventoryPosition} has {String:scenario_id}")
    InventoryPosition.snapshot_date = model.Property(f"{InventoryPosition} has {Date:snapshot_date}")
    # SupplierOffer
    SupplierOffer.unit_cost_cents = model.Property(f"{SupplierOffer} has {Integer:unit_cost_cents}")
    SupplierOffer.freight_cents_per_unit = model.Property(f"{SupplierOffer} has {Integer:freight_cents_per_unit}")
    SupplierOffer.currency = model.Property(f"{SupplierOffer} has {String:currency}")
    SupplierOffer.pack_size = model.Property(f"{SupplierOffer} has {Integer:pack_size}")
    SupplierOffer.minimum_order_qty = model.Property(f"{SupplierOffer} has {Integer:minimum_order_qty}")
    SupplierOffer.confirmed_capacity_qty = model.Property(f"{SupplierOffer} has {Integer:confirmed_capacity_qty}")
    SupplierOffer.lead_time_days = model.Property(f"{SupplierOffer} has {Integer:lead_time_days}")
    SupplierOffer.expected_arrival_date = model.Property(f"{SupplierOffer} has {Date:expected_arrival_date}")
    SupplierOffer.is_approved = model.Property(f"{SupplierOffer} has {Integer:is_approved}")
    SupplierOffer.eligible_packs = model.Property(f"{SupplierOffer} has {Integer:eligible_packs}")
    SupplierOffer.eligibility_reason = model.Property(f"{SupplierOffer} has {String:eligibility_reason}")
    SupplierOffer.is_synthetic = model.Property(f"{SupplierOffer} has {Integer:is_synthetic}")
    SupplierOffer.scenario_id = model.Property(f"{SupplierOffer} has {String:scenario_id}")
    SupplierOffer.snapshot_date = model.Property(f"{SupplierOffer} has {Date:snapshot_date}")
    SupplierOffer.product = model.Property(f"{SupplierOffer} for {Product:product}")
    SupplierOffer.supplier = model.Property(f"{SupplierOffer} offered by {Supplier:supplier}")
    # IncomingOrder
    IncomingOrder.quantity = model.Property(f"{IncomingOrder} has {Integer:quantity}")
    IncomingOrder.expected_receipt_date = model.Property(f"{IncomingOrder} has {Date:expected_receipt_date}")
    IncomingOrder.status = model.Property(f"{IncomingOrder} has {String:status}")
    IncomingOrder.counted_qty = model.Property(f"{IncomingOrder} has {Integer:counted_qty}")
    IncomingOrder.exclusion_reason = model.Property(f"{IncomingOrder} has {String:exclusion_reason}")
    IncomingOrder.is_synthetic = model.Property(f"{IncomingOrder} has {Integer:is_synthetic}")
    IncomingOrder.scenario_id = model.Property(f"{IncomingOrder} has {String:scenario_id}")
    IncomingOrder.snapshot_date = model.Property(f"{IncomingOrder} has {Date:snapshot_date}")
    IncomingOrder.product = model.Property(f"{IncomingOrder} for {Product:product}")
    IncomingOrder.supplier = model.Property(f"{IncomingOrder} ordered from {Supplier:supplier}")
    # Fixed-window planning metrics belong to the product.
    Product.window_end = model.Property(f"{Product} has {Date:window_end}")
    Product.remaining_demand_qty = model.Property(f"{Product} has {Integer:remaining_demand_qty}")
    Product.available_qty = model.Property(f"{Product} has {Integer:available_qty}")
    Product.counted_receipts_qty = model.Property(f"{Product} has {Integer:counted_receipts_qty}")
    Product.required_qty = model.Property(f"{Product} has {Integer:required_qty}")
    Product.unavoidable_shortfall_qty = model.Property(f"{Product} has {Integer:unavoidable_shortfall_qty}")
    Product.early_due_date = model.Property(f"{Product} has {Date:early_due_date}")
    Product.early_demand_qty = model.Property(f"{Product} has {Integer:early_demand_qty}")
    Product.early_shortfall_qty = model.Property(f"{Product} has {Integer:early_shortfall_qty}")
    Product.purchase_qty = model.Property(f"{Product} has {Integer:purchase_qty}")
    Product.total_cost_cents = model.Property(f"{Product} has {Integer:total_cost_cents}")
    Product.projected_ending_qty = model.Property(f"{Product} has {Integer:projected_ending_qty}")
    Product.demand_shortfall_qty = model.Property(f"{Product} has {Integer:demand_shortfall_qty}")
    Product.safety_shortfall_qty = model.Property(f"{Product} has {Integer:safety_shortfall_qty}")
    Product.excess_above_target_qty = model.Property(f"{Product} has {Integer:excess_above_target_qty}")
    Product.buyer_exception = model.Property(f"{Product} has {String:buyer_exception}")
    Product.warehouse = model.Property(f"{Product} held at {Warehouse:warehouse}")
    InventoryPosition.available_qty = model.Property(f"{InventoryPosition} has {Integer:available_qty} usable pieces")
    SupplierOffer.landed_unit_cost_cents = model.Property(f"{SupplierOffer} costs {Integer:landed_unit_cost_cents} USD cents per piece")
    SupplierOffer.minimum_packs = model.Property(f"{SupplierOffer} requires {Integer:minimum_packs} packs")
    Product.name_key = model.Property(f"{Product} has normalized {String:name_key}")
    SupplierOffer.eligible = model.Relationship(f"{SupplierOffer} is eligible for purchase")
    Product.offers = model.Relationship(f"{Product} has supplier offer {SupplierOffer:offer}")
    Product.incoming_orders = model.Relationship(f"{Product} has incoming order {IncomingOrder:order}")
    Product.stock_positions = model.Relationship(f"{Product} has stock position {InventoryPosition:position}")
    pack_type = Integer if include_results else Float
    SupplierOffer.order_packs = model.Property(f"{SupplierOffer} orders {pack_type:order_packs} packs")
    SupplierOffer.order_quantity = model.Property(f"{SupplierOffer} orders {Integer:order_quantity} pieces")
    SupplierOffer.order_cost_cents = model.Property(f"{SupplierOffer} has order cost {Integer:order_cost_cents}")
    SupplierOffer.order_reason = model.Property(f"{SupplierOffer} has order reason {String:order_reason}")
    SupplierOffer.is_selected = model.Relationship(f"{SupplierOffer} is selected for purchase")
    Product.has_shortage = model.Relationship(f"{Product} has unmet demand")
    Product.has_early_shortage = model.Relationship(f"{Product} has early delivery shortage")
    Product.requires_attention = model.Relationship(f"{Product} requires buyer attention")
    IncomingOrder.is_overdue = model.Relationship(f"{IncomingOrder} is overdue")

    # 3. Explicit source mappings. No undeclared properties are created implicitly.
    def source(table, key):
        if data is None:
            return model.Table(f"{SCHEMA}.{table}", schema=SOURCE_SCHEMAS[table])
        if key == 'offers':
            # Inline Data treats a None field as a missing row binding. Keep the
            # identity/terms complete; load optional dates from their own source.
            return model.data([{k:v for k,v in row.items() if k != 'EXPECTED_ARRIVAL_DATE'}
                               for row in data[key]])
        return model.data(data[key])

    src_products = source('SMB_PRODUCTS_V1', 'products')
    model.define(Product.new(
        product_id=src_products['PRODUCT_ID'],
        source_sku=src_products['SOURCE_SKU'],
        name=src_products['NAME'],
        category=src_products['CATEGORY'],
        base_unit=src_products['BASE_UNIT'],
        safety_stock_qty=src_products['SAFETY_STOCK_QTY'],
        is_synthetic=src_products['IS_SYNTHETIC'],
        scenario_id=src_products['SCENARIO_ID'],
        snapshot_date=src_products['SNAPSHOT_DATE'],
    ))

    src_suppliers = source('SMB_SUPPLIERS_V1', 'suppliers')
    model.define(Supplier.new(
        supplier_id=src_suppliers['SUPPLIER_ID'],
        name=src_suppliers['NAME'],
        is_synthetic=src_suppliers['IS_SYNTHETIC'],
        scenario_id=src_suppliers['SCENARIO_ID'],
        snapshot_date=src_suppliers['SNAPSHOT_DATE'],
    ))

    src_warehouses = source('SMB_WAREHOUSES_V1', 'warehouses')
    model.define(Warehouse.new(
        warehouse_id=src_warehouses['WAREHOUSE_ID'],
        name=src_warehouses['NAME'],
        is_synthetic=src_warehouses['IS_SYNTHETIC'],
        scenario_id=src_warehouses['SCENARIO_ID'],
        snapshot_date=src_warehouses['SNAPSHOT_DATE'],
    ))

    src_inventory = source('SMB_INVENTORY_V1', 'inventory')
    model.define(InventoryPosition.new(
        product=Product.lookup(product_id=src_inventory['PRODUCT_ID']),
        warehouse=Warehouse.lookup(warehouse_id=src_inventory['WAREHOUSE_ID']),
        on_hand_qty=src_inventory['ON_HAND_QTY'],
        reserved_qty=src_inventory['RESERVED_QTY'],
        is_synthetic=src_inventory['IS_SYNTHETIC'],
        scenario_id=src_inventory['SCENARIO_ID'],
        snapshot_date=src_inventory['SNAPSHOT_DATE'],
    ))

    src_offers = source('SMB_OFFERS_V1', 'offers')
    model.define(SupplierOffer.new(
        offer_id=src_offers['OFFER_ID'],
        product=Product.lookup(product_id=src_offers['PRODUCT_ID']),
        supplier=Supplier.lookup(supplier_id=src_offers['SUPPLIER_ID']),
        unit_cost_cents=src_offers['UNIT_COST_CENTS'],
        freight_cents_per_unit=src_offers['FREIGHT_CENTS_PER_UNIT'],
        currency=src_offers['CURRENCY'],
        pack_size=src_offers['PACK_SIZE'],
        minimum_order_qty=src_offers['MINIMUM_ORDER_QTY'],
        confirmed_capacity_qty=src_offers['CONFIRMED_CAPACITY_QTY'],
        lead_time_days=src_offers['LEAD_TIME_DAYS'],
        is_approved=src_offers['IS_APPROVED'],
        **({} if recompute_inputs else {'eligible_packs': src_offers['ELIGIBLE_PACKS']}),
        **({} if recompute_inputs else {'eligibility_reason':src_offers['ELIGIBILITY_REASON']}),
        is_synthetic=src_offers['IS_SYNTHETIC'],
        scenario_id=src_offers['SCENARIO_ID'],
        snapshot_date=src_offers['SNAPSHOT_DATE'],
    ))
    # A missing optional date must not suppress the offer's identity/base facts.
    if data is None:
        model.define(SupplierOffer.expected_arrival_date(src_offers['EXPECTED_ARRIVAL_DATE'])).where(
            SupplierOffer.offer_id == src_offers['OFFER_ID'])
    else:
        date_rows = [{'offer_id':row['OFFER_ID'], 'arrival':row['EXPECTED_ARRIVAL_DATE']}
                     for row in data['offers'] if row['EXPECTED_ARRIVAL_DATE'] is not None]
        if date_rows:
            dates = model.data(date_rows)
            model.define(SupplierOffer.expected_arrival_date(dates.arrival)).where(
                SupplierOffer.offer_id == dates.offer_id)

    src_incoming_orders = source('SMB_INCOMING_ORDERS_V1', 'incoming_orders')
    model.define(IncomingOrder.new(
        order_id=src_incoming_orders['ORDER_ID'],
        product=Product.lookup(product_id=src_incoming_orders['PRODUCT_ID']),
        supplier=Supplier.lookup(supplier_id=src_incoming_orders['SUPPLIER_ID']),
        quantity=src_incoming_orders['QUANTITY'],
        expected_receipt_date=src_incoming_orders['EXPECTED_RECEIPT_DATE'],
        status=src_incoming_orders['STATUS'],
        **({} if recompute_inputs else {'counted_qty': src_incoming_orders['COUNTED_QTY']}),
        **({} if recompute_inputs else {'exclusion_reason':src_incoming_orders['EXCLUSION_REASON']}),
        is_synthetic=src_incoming_orders['IS_SYNTHETIC'],
        scenario_id=src_incoming_orders['SCENARIO_ID'],
        snapshot_date=src_incoming_orders['SNAPSHOT_DATE'],
    ))

    # Demand inputs enrich existing Product instances; no parallel need entities.
    src_needs = source('SMB_NEEDS_V1', 'needs')
    for field, column in [('window_end','WINDOW_END'),
                          ('remaining_demand_qty','REMAINING_DEMAND_QTY'),
                          ('unavoidable_shortfall_qty','UNAVOIDABLE_SHORTFALL_QTY'),
                          ('early_due_date','EARLY_DUE_DATE'),
                          ('early_demand_qty','EARLY_DEMAND_QTY'),
                          ('early_shortfall_qty','EARLY_SHORTFALL_QTY')]:
        if recompute_inputs and field in {'unavoidable_shortfall_qty','early_shortfall_qty'}:
            continue
        model.where(Product.product_id == src_needs['PRODUCT_ID']).define(
            getattr(Product, field)(src_needs[column]))
    model.where(Product.product_id == src_needs['PRODUCT_ID']).define(
        Product.warehouse(Warehouse.lookup(warehouse_id=src_needs['WAREHOUSE_ID'])))
    summary_source = comparison_source = None
    if include_results:
        src_orders = source('SMB_RECOMMENDATIONS_V1', 'recommendations')
        model.where(SupplierOffer.offer_id == src_orders['OFFER_ID']).define(
            SupplierOffer.order_packs(src_orders['PACK_COUNT']),
            SupplierOffer.order_reason(src_orders['REASON']))
        # Every offer has a decision, including offers with zero ordered packs.
        model.where(model.not_(model.where(SupplierOffer.offer_id == src_orders["OFFER_ID"]))).define(
            SupplierOffer.order_packs(0))
        model.where(Product.product_id == src_needs['PRODUCT_ID']).define(
            Product.buyer_exception(src_needs['BUYER_EXCEPTION']))
        # Reports are source records consumed by report queries, not concepts.
        summary_source = source('SMB_PLANS_V1', 'plans')
        comparison_source = source('SMB_COMPARISONS_V1', 'comparisons')

    # 4. Reusable derived business facts (also consumed by the optimizer).
    model.define(Product.name_key(strings.lower(Product.name)))
    model.define(InventoryPosition.available_qty(InventoryPosition.on_hand_qty - InventoryPosition.reserved_qty))
    model.define(SupplierOffer.landed_unit_cost_cents(SupplierOffer.unit_cost_cents + SupplierOffer.freight_cents_per_unit))
    model.define(SupplierOffer.minimum_packs((SupplierOffer.minimum_order_qty + SupplierOffer.pack_size - 1) // SupplierOffer.pack_size))
    if not recompute_inputs:
        model.where(SupplierOffer.eligible_packs > 0).define(SupplierOffer.eligible())
    model.where(SupplierOffer.product == Product).define(Product.offers(SupplierOffer))
    model.where(IncomingOrder.product == Product).define(Product.incoming_orders(IncomingOrder))
    model.where(InventoryPosition.product == Product).define(Product.stock_positions(InventoryPosition))
    model.where(Product == InventoryPosition.product,
                Product.warehouse == InventoryPosition.warehouse).define(
        Product.available_qty(InventoryPosition.available_qty))
    if recompute_inputs:
        on_time = model.where(IncomingOrder.status == 'confirmed',
            IncomingOrder.expected_receipt_date > IncomingOrder.snapshot_date,
            IncomingOrder.expected_receipt_date <= IncomingOrder.product.window_end)
        on_time.define(IncomingOrder.counted_qty(IncomingOrder.quantity))
        model.where(model.not_(on_time)).define(IncomingOrder.counted_qty(0))
        on_time.define(IncomingOrder.exclusion_reason('counted'))
        model.where(IncomingOrder.status != 'confirmed').define(IncomingOrder.exclusion_reason('cancelled'))
        model.where(IncomingOrder.status == 'confirmed',
            IncomingOrder.expected_receipt_date <= IncomingOrder.snapshot_date).define(
                IncomingOrder.exclusion_reason('overdue; requires reconfirmation'))
        model.where(IncomingOrder.status == 'confirmed',
            IncomingOrder.expected_receipt_date > IncomingOrder.product.window_end).define(
                IncomingOrder.exclusion_reason('after planning window'))
        capacity_packs = SupplierOffer.confirmed_capacity_qty // SupplierOffer.pack_size
        model.where(SupplierOffer.is_approved == 1, SupplierOffer.lead_time_days >= 0,
            SupplierOffer.expected_arrival_date >= SupplierOffer.snapshot_date,
            SupplierOffer.expected_arrival_date <= SupplierOffer.product.window_end,
            capacity_packs >= SupplierOffer.minimum_packs).define(SupplierOffer.eligible())
        model.where(SupplierOffer.eligible()).define(SupplierOffer.eligible_packs(capacity_packs))
        model.where(model.not_(SupplierOffer.eligible())).define(SupplierOffer.eligible_packs(0))
        model.where(SupplierOffer.eligible()).define(SupplierOffer.eligibility_reason('eligible'))
        model.where(model.not_(SupplierOffer.eligible())).define(
            SupplierOffer.eligibility_reason('ineligible: check approval, lead time, arrival and MOQ/capacity'))
    model.define(Product.counted_receipts_qty(
        aggs.sum(IncomingOrder.counted_qty).per(Product).where(IncomingOrder.product == Product) | 0))
    gap = Product.remaining_demand_qty + Product.safety_stock_qty - Product.available_qty - Product.counted_receipts_qty
    model.define(Product.required_qty(math.maximum(0, gap)))
    if recompute_inputs:
        supply = aggs.sum(SupplierOffer.eligible_packs * SupplierOffer.pack_size).per(Product).where(
            SupplierOffer.product == Product) | 0
        model.define(Product.unavoidable_shortfall_qty(math.maximum(0, Product.required_qty - supply)))
        early_receipts = aggs.sum(IncomingOrder.counted_qty).per(Product).where(
            IncomingOrder.product == Product,
            IncomingOrder.expected_receipt_date <= Product.early_due_date) | 0
        early_supply = aggs.sum(SupplierOffer.eligible_packs * SupplierOffer.pack_size).per(Product).where(
            SupplierOffer.product == Product,
            SupplierOffer.expected_arrival_date <= Product.early_due_date) | 0
        model.define(Product.early_shortfall_qty(math.maximum(0,
            Product.early_demand_qty - Product.available_qty - early_receipts - early_supply)))
    model.where(IncomingOrder.expected_receipt_date <= IncomingOrder.snapshot_date,
                IncomingOrder.status == 'confirmed').define(IncomingOrder.is_overdue())
    model.where(Product.early_shortfall_qty > 0).define(Product.has_early_shortage())
    if include_results:
        model.define(SupplierOffer.order_quantity(SupplierOffer.order_packs * SupplierOffer.pack_size))
        model.define(SupplierOffer.order_cost_cents(SupplierOffer.order_quantity * SupplierOffer.landed_unit_cost_cents))
        model.where(SupplierOffer.order_packs > 0).define(SupplierOffer.is_selected())
        model.where(SupplierOffer.product == Product).define(
            Product.purchase_qty(aggs.sum(SupplierOffer.order_quantity).per(Product)),
            Product.total_cost_cents(aggs.sum(SupplierOffer.order_cost_cents).per(Product)))
        model.define(Product.projected_ending_qty(Product.available_qty + Product.counted_receipts_qty +
                                                  Product.purchase_qty - Product.remaining_demand_qty))
        model.define(Product.demand_shortfall_qty(math.maximum(0, -Product.projected_ending_qty)))
        model.define(Product.safety_shortfall_qty(math.maximum(0, Product.safety_stock_qty -
                                                              math.maximum(0, Product.projected_ending_qty))))
        model.define(Product.excess_above_target_qty(math.maximum(0, Product.projected_ending_qty - Product.safety_stock_qty)))
        model.where(Product.demand_shortfall_qty > 0).define(Product.has_shortage())
        # Multiple definitions collect every business reason for attention.
        model.where(Product.has_shortage()).define(Product.requires_attention())
        model.where(Product.safety_shortfall_qty > 0).define(Product.requires_attention())
        model.where(Product.has_early_shortage()).define(Product.requires_attention())
        model.where(IncomingOrder.product == Product, IncomingOrder.is_overdue()).define(
            Product.requires_attention())

    return SimpleNamespace(model=model, sources=SOURCE_SCHEMAS, Product=Product,
        Supplier=Supplier, Warehouse=Warehouse, InventoryPosition=InventoryPosition,
        SupplierOffer=SupplierOffer, IncomingOrder=IncomingOrder,
        summary_source=summary_source, comparison_source=comparison_source,
        input_sources={'products':src_products,'suppliers':src_suppliers,
            'warehouses':src_warehouses,'inventory':src_inventory,'offers':src_offers,
            'incoming_orders':src_incoming_orders,'needs':src_needs})

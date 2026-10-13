"""Read-only buyer queries over the small-business purchasing ontology."""
from relationalai.semantics.std import aggregates as aggs
from model import (model, Product, Supplier, SupplierOffer, IncomingOrder,
                   PurchasingNeed, PurchasingPlan, PurchaseRecommendation, PurchasingComparison)


def purchasing_comparison():
    """Compare optimized cost with feasible lowest-landed-price-first ordering on identical synthetic inputs. Baseline respects packs/MOQ/capacity and matches maximum feasible coverage; USD cents. Savings are baseline minus optimized; percentage uses baseline cost."""
    c = PurchasingComparison
    return model.select(c.baseline_strategy.alias('baseline_strategy'),c.baseline_status.alias('baseline_status'),
        c.baseline_cost_cents.alias('baseline_cost_cents'),c.optimized_cost_cents.alias('optimized_cost_cents'),
        c.savings_cents.alias('savings_cents'),c.baseline_purchase_qty.alias('baseline_purchase_pieces'),
        c.optimized_purchase_qty.alias('optimized_purchase_pieces'),
        c.baseline_demand_shortfall_qty.alias('baseline_demand_shortfall_pieces'),
        c.optimized_demand_shortfall_qty.alias('optimized_demand_shortfall_pieces'),
        c.baseline_safety_shortfall_qty.alias('baseline_safety_shortfall_pieces'),
        c.optimized_safety_shortfall_qty.alias('optimized_safety_shortfall_pieces'),
        c.baseline_excess_qty.alias('baseline_excess_pieces'),c.optimized_excess_qty.alias('optimized_excess_pieces'),
        c.products_with_savings.alias('products_with_savings'),c.currency.alias('currency'),c.is_synthetic.alias('is_synthetic'))


def purchasing_summary():
    """Show the synthetic one-warehouse, 30-product, 30-day plan: USD cents, purchase pieces, demand and safety shortfalls, snapshot dates and solver status. Precomputed recommendations only."""
    p = PurchasingPlan
    return model.select(p.name.alias('plan'), p.status.alias('solver_status'),
                        p.snapshot_date.alias('snapshot_date'), p.window_end.alias('window_end'),
                        p.product_count.alias('products'), p.supplier_count.alias('suppliers'),
                        p.warehouse_count.alias('warehouses'), p.currency.alias('currency'),
                        p.total_cost_cents.alias('total_cost_cents'), p.purchase_qty.alias('purchase_pieces'),
                        p.demand_shortfall_qty.alias('demand_shortfall_pieces'),
                        p.safety_shortfall_qty.alias('safety_shortfall_pieces'),
                        p.exception_product_count.alias('exception_products'), p.is_synthetic.alias('is_synthetic'))


def purchasing_worklist(product_id: int = 0, limit: int = 50):
    """Buyer worklist: current available pieces, remaining unallocated demand, on-time incoming orders, safety target, shortage, recommended purchases and exceptions. Optional product ID; limit 1..50."""
    _limit(limit)
    n = PurchasingNeed
    q = model.where(n.product == Product)
    if product_id: q = q.where(Product.product_id == product_id)
    return q.where(aggs.limit(limit, aggs.desc(n.required_qty), Product.product_id)).select(
        Product.product_id.alias('product_id'), Product.name.alias('product'),
        Product.base_unit.alias('base_unit'), n.available_qty.alias('available_pieces'),
        n.remaining_demand_qty.alias('remaining_demand_pieces'), n.counted_receipts_qty.alias('on_time_receipts_pieces'),
        Product.safety_stock_qty.alias('safety_stock_pieces'), n.required_qty.alias('required_purchase_pieces'),
        n.purchase_qty.alias('recommended_purchase_pieces'), n.projected_ending_qty.alias('projected_ending_pieces'),
        n.demand_shortfall_qty.alias('demand_shortfall_pieces'), n.safety_shortfall_qty.alias('safety_shortfall_pieces'),
        n.excess_above_target_qty.alias('pack_rounding_excess_pieces'), n.buyer_exception.alias('buyer_exception'))


def recommended_purchases(product_id: int = 0, limit: int = 50):
    """Show synthetic recommended supplier orders in pieces and packs, landed USD cents, expected arrivals and reasons. Optional product ID; limit 1..50. Never places orders."""
    _limit(limit)
    a = PurchaseRecommendation
    q = model.where(a.product == Product, a.supplier == Supplier, a.offer == SupplierOffer)
    if product_id: q = q.where(Product.product_id == product_id)
    return q.where(aggs.limit(limit, aggs.desc(a.total_cost_cents), a.action_id)).select(
        Product.product_id.alias('product_id'), Product.name.alias('product'), Supplier.name.alias('supplier'),
        a.quantity.alias('pieces'), a.pack_count.alias('packs'), SupplierOffer.pack_size.alias('pieces_per_pack'),
        a.landed_unit_cost_cents.alias('landed_unit_cost_usd_cents'), a.total_cost_cents.alias('total_cost_usd_cents'),
        a.expected_arrival_date.alias('expected_arrival'), a.reason.alias('reason'), a.is_synthetic.alias('is_synthetic'))


def buyer_exceptions():
    """List all buyer exceptions: unavoidable demand/safety shortfall, early delivery obligations, or overdue incoming orders. Early demand is already included in remaining demand, not additional demand."""
    n = PurchasingNeed
    return model.where(n.product == Product, n.buyer_exception != 'none').select(
        Product.product_id.alias('product_id'), Product.name.alias('product'),
        n.demand_shortfall_qty.alias('window_demand_shortfall_pieces'), n.safety_shortfall_qty.alias('safety_shortfall_pieces'),
        n.early_due_date.alias('early_due_date'), n.early_demand_qty.alias('early_demand_pieces'),
        n.early_shortfall_qty.alias('early_shortfall_pieces'), n.buyer_exception.alias('buyer_exception'))


def incoming_orders(product_id: int = 0):
    """List synthetic existing orders and dated arrivals, including counted quantity and explicit reasons for excluding overdue, cancelled, and beyond-window receipts. Optional product ID."""
    r = IncomingOrder
    q = model.where(r.product == Product, r.supplier == Supplier)
    if product_id: q = q.where(Product.product_id == product_id)
    return q.select(r.order_id.alias('order_id'), Product.product_id.alias('product_id'),
                    Product.name.alias('product'), Supplier.name.alias('supplier'),
                    r.quantity.alias('pieces'), r.expected_receipt_date.alias('expected_receipt_date'),
                    r.status.alias('status'), r.counted_qty.alias('counted_pieces'), r.exclusion_reason.alias('receipt_treatment'))


def supplier_options(product_id: int):
    """Show all supplier offers for a product including approval, MOQ, pack size, capacity, lead days, eligibility and synthetic USD pricing. Missing lead time uses -1 and has no arrival date."""
    o = SupplierOffer
    # A nullable date is intentionally omitted so a missing-date offer still appears.
    return model.where(o.product == Product, o.supplier == Supplier, Product.product_id == product_id).select(
        Supplier.name.alias('supplier'), o.landed_unit_cost_cents.alias('landed_unit_cost_usd_cents'),
        o.pack_size.alias('pieces_per_pack'), o.minimum_order_qty.alias('minimum_order_pieces'),
        o.confirmed_capacity_qty.alias('confirmed_capacity_pieces'), o.lead_time_days.alias('lead_time_days'),
        o.is_approved.alias('approved'), o.eligible_packs.alias('eligible_packs'), o.eligibility_reason.alias('eligibility'))


def _limit(limit):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ValueError('limit must be an integer from 1 to 50')

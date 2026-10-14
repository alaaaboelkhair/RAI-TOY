"""Supporting fact queries for the on-demand RAI purchasing assistant."""
from model import model, Product, Supplier, SupplierOffer, IncomingOrder


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


def find_products(name: str):
    """Resolve a product name case-insensitively; rejects empty names before querying."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError('name must be a non-empty string')
    return model.where(Product.name_key == name.strip().lower()).select(
        Product.product_id.alias('product_id'), Product.name.alias('product'))

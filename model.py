"""Deployed purchasing model. Ontology authoring lives in purchasing_ontology.py."""
from purchasing_ontology import build_ontology, SOURCE_SCHEMAS, PROVENANCE

ontology = build_ontology(include_results=False,recompute_inputs=True)
model = ontology.model
Product = ontology.Product
Supplier = ontology.Supplier
Warehouse = ontology.Warehouse
InventoryPosition = ontology.InventoryPosition
SupplierOffer = ontology.SupplierOffer
IncomingOrder = ontology.IncomingOrder
summary_source = ontology.summary_source
comparison_source = ontology.comparison_source

"""Complete ontology entry point replacing the incomplete RelUI code export.

Deploy model.py. Run this file to execute fresh logic + prescriptive reasoning.
All declarations and definitions come from the tested authored ontology.
"""
from model import (model, ontology, Product, Supplier, Warehouse, InventoryPosition,
                   SupplierOffer, IncomingOrder, summary_source, comparison_source)
from purchasing_reasoners import compute_purchasing_plan, run_purchasing_reasoners

m = model

if __name__ == "__main__":
    from purchasing_reasoners import main
    main()

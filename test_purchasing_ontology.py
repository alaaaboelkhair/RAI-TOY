"""Regression checks for the shared semantic surface and query boundaries."""
import unittest
import json
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy
from relationalai.config import create_config
from relationalai.semantics import inspect
from purchasing_demo import generate
from purchasing_ontology import build_ontology
from purchasing_optimization import formulate
from purchasing_demo import restore_dates


class OntologyBoundaryTests(unittest.TestCase):
    def test_only_business_entities_are_concepts(self):
        config=create_config();config.deployment=None
        ontology=build_ontology(name='DomainConceptTest',config=config,
                                data=generate(list(range(1001,1031))),include_results=False)
        names={c.name for c in inspect.schema(ontology.model).concepts}
        self.assertEqual(names,{'Product','Supplier','Warehouse','InventoryPosition',
                               'SupplierOffer','IncomingOrder'})

    def test_solver_uses_typed_domain_links_and_one_constraint_family(self):
        config=create_config();config.deployment=None
        ontology=build_ontology(name='OntologyBoundaryTest',config=config,
                                data=generate(list(range(1001,1031))),include_results=False)
        schema=inspect.schema(ontology.model)
        offer=schema['SupplierOffer']
        fields={p.name:p.type_name for p in offer.properties}
        self.assertEqual(fields['product'],'Product')
        self.assertEqual(fields['supplier'],'Supplier')
        self.assertNotIn('product_id',fields)
        problem, requirements, _, _ = formulate(ontology)
        self.assertEqual(len(problem.variables),2)
        self.assertEqual(len(problem.constraints),3)
        self.assertEqual(len(requirements),3)

    def test_missing_all_arrival_dates_does_not_prevent_model_construction(self):
        data=generate(list(range(1001,1031)))
        for offer in data['offers']:
            offer.update(EXPECTED_ARRIVAL_DATE=None,LEAD_TIME_DAYS=-1,ELIGIBLE_PACKS=0)
        config=create_config();config.deployment=None
        ontology=build_ontology(name='AllMissingArrivalTest',config=config,data=data,include_results=False)
        self.assertIsNotNone(inspect.schema(ontology.model)['SupplierOffer'])

    def test_empty_names_are_rejected_before_any_database_query(self):
        from query import find_products
        for value in ['', '   ', None]:
            with self.assertRaises(ValueError):find_products(value)


class LocalReasoningTests(unittest.TestCase):
    """Execute real PyRel rules against the saved snapshot, without Snowflake."""
    @classmethod
    def setUpClass(cls):
        from relationalai.config import DuckDBConnection
        cls.data=restore_dates(json.loads(Path('data/smb_purchasing_results.json').read_text())['data'])
        config=create_config(connections={'local':DuckDBConnection(path=':memory:')},
            default_connection='local',deployment={'schema':'main','auto_deploy':True})
        cls.ontology=build_ontology(name='LocalPurchasingRules',config=config,data=cls.data)

    def test_all_product_balances_match_verified_snapshot(self):
        o=self.ontology;p=o.Product
        fields=['available_qty','counted_receipts_qty','required_qty','purchase_qty',
                'total_cost_cents','projected_ending_qty','demand_shortfall_qty',
                'safety_shortfall_qty','excess_above_target_qty']
        rows=o.model.select(p.product_id.alias('product_id'),
            *(getattr(p,f).alias(f) for f in fields)).to_df().to_dict('records')
        self.assertEqual(len(rows),30)
        expected={n['PRODUCT_ID']:n for n in self.data['needs']}
        for row in rows:
            for field in fields:
                self.assertEqual(int(row[field]),expected[int(row['product_id'])][field.upper()],
                                 (row['product_id'],field))

    def test_supporting_fact_queries_preserve_results(self):
        import query
        o=self.ontology
        replacements={name:getattr(o,name) for name in ['model','Product','Supplier',
            'SupplierOffer','IncomingOrder']}
        with patch.multiple(query,**replacements):
            self.assertEqual(len(query.incoming_orders().to_df()),30)
            self.assertEqual(len(query.find_products('  Nitrile Gloves  ').to_df()),1)
            self.assertEqual(len(query.supplier_options(3).to_df()),3)

    def test_logic_flags_match_business_exceptions(self):
        o=self.ontology;p=o.Product
        def ids(flag):
            return {int(x) for x in o.model.where(flag()).select(p.product_id).to_df()['product_id']}
        self.assertEqual(ids(p.has_shortage),{2})
        self.assertEqual(ids(p.has_early_shortage),{1})
        self.assertEqual(ids(p.requires_attention),{1,2,8,15,22,29})

    def test_equal_order_values_are_counted_for_each_offer(self):
        from relationalai.config import DuckDBConnection
        data=deepcopy(self.data)
        offers=[o for o in data['offers'] if o['PRODUCT_ID']==1][:2]
        for offer in offers:
            offer.update(PACK_SIZE=10,UNIT_COST_CENTS=100,FREIGHT_CENTS_PER_UNIT=0)
        data['recommendations']=[r for r in data['recommendations'] if r['PRODUCT_ID']!=1]
        for offer in offers:
            record=dict(self.data['recommendations'][0])
            record.update(OFFER_ID=offer['OFFER_ID'],SUPPLIER_ID=offer['SUPPLIER_ID'],
                PACK_COUNT=1,QUANTITY=10,LANDED_UNIT_COST_CENTS=100,TOTAL_COST_CENTS=1000,
                EXPECTED_ARRIVAL_DATE=offer['EXPECTED_ARRIVAL_DATE'],
                REASON='Equal-value aggregation fixture')
            data['recommendations'].append(record)
        config=create_config(connections={'local':DuckDBConnection(path=':memory:')},
            default_connection='local',deployment={'schema':'main','auto_deploy':True})
        o=build_ontology(name='EqualOfferValues',config=config,data=data);p=o.Product
        rows=o.model.where(p.product_id==1).select(
            p.purchase_qty.alias('quantity'),p.total_cost_cents.alias('cost')).to_df()
        self.assertEqual(int(rows.iloc[0]['quantity']),20)
        self.assertEqual(int(rows.iloc[0]['cost']),2000)


if __name__=='__main__':unittest.main()

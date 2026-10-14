"""Actual PyRel input reasoning checks, independent of saved calculated columns."""
from copy import deepcopy
import json
from datetime import date,datetime
from pathlib import Path
import unittest
from relationalai.config import create_config,DuckDBConnection
from purchasing_demo import generate,restore_dates
from purchasing_reasoners import derive_purchasing_inputs,read_reasoned_results,format_plan_table


class FreshInputReasoningTests(unittest.TestCase):
    def test_native_snowflake_dates_and_optional_dates_are_preserved(self):
        value={'SNAPSHOT_DATE':datetime(2026,10,12),'WINDOW_END':'2026-11-11',
               'EXPECTED_ARRIVAL_DATE':None}
        actual=restore_dates(value)
        self.assertEqual(actual['SNAPSHOT_DATE'],date(2026,10,12))
        self.assertEqual(actual['WINDOW_END'],date(2026,11,11))
        self.assertIsNone(actual['EXPECTED_ARRIVAL_DATE'])

    def local_config(self):
        return create_config(connections={'local':DuckDBConnection(path=':memory:')},
            default_connection='local',deployment={'schema':'main','auto_deploy':True})

    def test_calculated_columns_are_recomputed_from_raw_facts(self):
        expected=generate(list(range(1001,1031)))
        stale=deepcopy(expected)
        for row in stale['offers']:row['ELIGIBLE_PACKS']=999
        for row in stale['incoming_orders']:row['COUNTED_QTY']=999
        for row in stale['needs']:
            for field in ['AVAILABLE_QTY','COUNTED_RECEIPTS_QTY','REQUIRED_QTY',
                          'UNAVOIDABLE_SHORTFALL_QTY','EARLY_SHORTFALL_QTY']:
                row[field]=999
        actual,_=derive_purchasing_inputs(stale,config=self.local_config())
        for key,fields in [('offers',['ELIGIBLE_PACKS']),('incoming_orders',['COUNTED_QTY']),
            ('needs',['AVAILABLE_QTY','COUNTED_RECEIPTS_QTY','REQUIRED_QTY',
                      'UNAVOIDABLE_SHORTFALL_QTY','EARLY_SHORTFALL_QTY'])]:
            for a,e in zip(actual[key],expected[key]):
                for field in fields:self.assertEqual(a[field],e[field],(key,field))

    def test_changed_capacity_changes_coverage(self):
        data=generate(list(range(1001,1031)))
        for row in data['offers']:
            if row['PRODUCT_ID']==1:row['CONFIRMED_CAPACITY_QTY']=0
        actual,_=derive_purchasing_inputs(data,config=self.local_config())
        need=next(n for n in actual['needs'] if n['PRODUCT_ID']==1)
        self.assertEqual(need['UNAVOIDABLE_SHORTFALL_QTY'],40)

    def test_raw_inputs_need_no_saved_results_or_derived_columns(self):
        data=generate(list(range(1001,1031)))
        for key in ('recommendations','plans','comparisons','baseline_recommendations'):
            data.pop(key,None)
        for row in data['offers']:
            row.pop('ELIGIBLE_PACKS');row.pop('ELIGIBILITY_REASON')
        for row in data['incoming_orders']:
            row.pop('COUNTED_QTY');row.pop('EXCLUSION_REASON')
        allowed={'PRODUCT_ID','WAREHOUSE_ID','WINDOW_END','REMAINING_DEMAND_QTY',
                 'EARLY_DUE_DATE','EARLY_DEMAND_QTY','IS_SYNTHETIC','SCENARIO_ID','SNAPSHOT_DATE'}
        data['needs']=[{k:v for k,v in n.items() if k in allowed} for n in data['needs']]
        actual,_=derive_purchasing_inputs(data,config=self.local_config())
        self.assertEqual(len(actual['needs']),30)
        self.assertNotIn('recommendations',actual)

    def test_deployed_model_has_no_saved_report_bindings(self):
        from model import ontology
        self.assertIsNone(ontology.summary_source)
        self.assertIsNone(ontology.comparison_source)
        self.assertEqual(len(ontology.input_sources),7)
        from purchasing_ontology import build_ontology
        with self.assertRaises(ValueError):build_ontology(include_results=True)

    def test_multiple_warehouses_are_rejected(self):
        data=generate(list(range(1001,1031)))
        data['warehouses'].append(dict(data['warehouses'][0],WAREHOUSE_ID=2))
        with self.assertRaises(ValueError):
            derive_purchasing_inputs(data,config=self.local_config())

    def test_result_rules_match_independently_verified_solution(self):
        data=restore_dates(json.loads(Path('data/smb_purchasing_results.json').read_text())['data'])
        rows=read_reasoned_results(data,config=self.local_config())
        self.assertEqual(len(rows),30)
        self.assertEqual(sum(int(r['purchase_qty']) for r in rows),3226)
        self.assertEqual(sum(int(r['demand_shortfall_qty']) for r in rows),49)

    def test_live_callable_can_be_registered_in_rai_catalog(self):
        from relationalai.agent.cortex import QueryCatalog
        from purchasing_reasoners import compute_purchasing_plan
        metadata=QueryCatalog(compute_purchasing_plan).get_available_queries()
        self.assertIn('compute_purchasing_plan',metadata['queries'])

    def test_discovery_offers_live_planning_without_ambiguous_saved_alternatives(self):
        from deploy_agent import LivePlanningCatalog
        from purchasing_reasoners import compute_purchasing_plan
        from query import find_products
        catalog=LivePlanningCatalog(compute_purchasing_plan,find_products)
        metadata=catalog.get_available_queries()
        self.assertEqual(set(metadata['queries']),{'compute_purchasing_plan','find_products'})
        self.assertEqual(metadata['query_mode'],'catalog')
        self.assertNotIn('purchasing_summary',metadata['queries'])

    def test_complete_supplier_orders_fit_cortex_response_budget(self):
        from relationalai.agent.cortex.response_envelope import shape_tool_response
        artifact=json.loads(Path('data/smb_purchasing_results.json').read_text())
        artifact['run']={'run_id':'offline-format-verification'}
        frame=format_plan_table(artifact)
        response=shape_tool_response(frame.to_dict('records'),kind='tabular')
        self.assertFalse(response['truncated'])
        self.assertEqual(len(response['content']),31)
        orders=[o for row in response['content'] for o in json.loads(row['supplier_orders'])]
        self.assertEqual(len(orders),45)
        self.assertEqual(sum(o[1] for o in orders),3226)
        self.assertAlmostEqual(sum(o[4] for o in orders),36922)


if __name__=='__main__':unittest.main()

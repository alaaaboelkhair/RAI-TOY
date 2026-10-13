"""Verify deployed counts, balances, date rules and the agent's actual query tools."""
import json
from pathlib import Path
from relationalai.config import create_config, SnowflakeConnection
from model import DEFINITIONS, PROVENANCE


def verify_source_types(session):
    from relationalai.semantics import Integer, String, Date
    rows = session.sql("""SELECT TABLE_NAME,COLUMN_NAME,DATA_TYPE,NUMERIC_SCALE
        FROM ALAA_DEMO_DATA.INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='SMB_PURCHASING'""").collect()
    actual = {(r['TABLE_NAME'],r['COLUMN_NAME']):(r['DATA_TYPE'],r['NUMERIC_SCALE']) for r in rows}
    for concept, table, key, fields, links in DEFINITIONS:
        columns = {**{k.upper():t for k,t in {**fields,**PROVENANCE}.items()},
                   **{v[2]:Integer for v in links.values()}}
        if key: columns[key.upper()] = Integer
        for column, expected in columns.items():
            type_, scale = actual[table,column]
            assert ((expected is Integer and type_=='NUMBER' and scale==0)
                    or (expected is String and type_=='TEXT')
                    or (expected is Date and type_=='DATE')),(table,column,type_,scale,expected)
    print('All ontology source column types verified against Snowflake metadata',flush=True)


def main():
    artifact = json.loads(Path('data/smb_purchasing_results.json').read_text())
    expected = artifact['data']['plans'][0]
    s = create_config().get_session(SnowflakeConnection)
    report = {}
    try:
        verify_source_types(s)
        s.use_database('ALAA_RELAPP_PERSISTENCE')
        s.use_schema('BACKORDER_MODEL')
        counts = {table: int(s.sql(f'SELECT COUNT(*) FROM {table}').collect()[0][0])
                  for table in ['PRODUCT','SUPPLIER','WAREHOUSE','INVENTORYPOSITION','SUPPLIEROFFER',
                                'INCOMINGORDER','PURCHASINGNEED','PURCHASINGPLAN','PURCHASERECOMMENDATION','PURCHASINGCOMPARISON']}
        assert counts == dict(PRODUCT=30,SUPPLIER=4,WAREHOUSE=1,INVENTORYPOSITION=30,SUPPLIEROFFER=90,
                              INCOMINGORDER=30,PURCHASINGNEED=30,PURCHASINGPLAN=1,
                              PURCHASERECOMMENDATION=len(artifact['data']['recommendations']),PURCHASINGCOMPARISON=1),counts
        report['counts'] = counts
        sql_checks = {
            'offer_violations': '''SELECT COUNT(*) FROM PURCHASERECOMMENDATION r
                JOIN SUPPLIEROFFER o ON r.OFFER=o.OFFER_ID WHERE
                o.ELIGIBLE_PACKS=0 OR r.PACK_COUNT>o.ELIGIBLE_PACKS OR r.PACK_COUNT<=0 OR
                r.QUANTITY<>r.PACK_COUNT*o.PACK_SIZE OR r.QUANTITY<o.MINIMUM_ORDER_QTY OR
                r.QUANTITY>o.CONFIRMED_CAPACITY_QTY OR r.PRODUCT<>o.PRODUCT OR r.SUPPLIER<>o.SUPPLIER OR
                r.TOTAL_COST_CENTS<>r.QUANTITY*o.LANDED_UNIT_COST_CENTS OR
                r.EXPECTED_ARRIVAL_DATE<>o.EXPECTED_ARRIVAL_DATE OR r.EXPECTED_ARRIVAL_DATE>'2026-11-11'::DATE''',
            'balance_violations': '''WITH purchases AS (
                SELECT PRODUCT,SUM(QUANTITY) Q,SUM(TOTAL_COST_CENTS) C FROM PURCHASERECOMMENDATION GROUP BY 1),
                receipts AS (SELECT PRODUCT,SUM(COUNTED_QTY) Q FROM INCOMINGORDER GROUP BY 1)
                SELECT COUNT(*) FROM PURCHASINGNEED n JOIN INVENTORYPOSITION i ON i.PRODUCT=n.PRODUCT
                JOIN PRODUCT p ON p.PRODUCT_ID=n.PRODUCT
                LEFT JOIN purchases b ON b.PRODUCT=n.PRODUCT LEFT JOIN receipts r ON r.PRODUCT=n.PRODUCT
                WHERE n.AVAILABLE_QTY<>i.AVAILABLE_QTY OR n.COUNTED_RECEIPTS_QTY<>COALESCE(r.Q,0) OR
                n.PURCHASE_QTY<>COALESCE(b.Q,0) OR n.TOTAL_COST_CENTS<>COALESCE(b.C,0) OR
                n.PROJECTED_ENDING_QTY<>n.AVAILABLE_QTY+n.COUNTED_RECEIPTS_QTY+n.PURCHASE_QTY-n.REMAINING_DEMAND_QTY OR
                n.DEMAND_SHORTFALL_QTY<>GREATEST(0,-n.PROJECTED_ENDING_QTY) OR
                n.SAFETY_SHORTFALL_QTY<>GREATEST(0,p.SAFETY_STOCK_QTY-GREATEST(0,n.PROJECTED_ENDING_QTY)) OR
                n.REQUIRED_QTY<>GREATEST(0,n.REMAINING_DEMAND_QTY+p.SAFETY_STOCK_QTY-n.AVAILABLE_QTY-n.COUNTED_RECEIPTS_QTY)''',
            'receipt_violations': '''SELECT COUNT(*) FROM INCOMINGORDER WHERE COUNTED_QTY<>
                IFF(STATUS='confirmed' AND EXPECTED_RECEIPT_DATE>SNAPSHOT_DATE AND
                EXPECTED_RECEIPT_DATE<='2026-11-11'::DATE,QUANTITY,0)''',
        }
        for name, sql in sql_checks.items():
            value = int(s.sql(sql).collect()[0][0])
            assert value==0,(name,value)
            report[name] = value
        summary = s.sql('SELECT * FROM PURCHASINGPLAN').collect()[0].as_dict()
        for key in ['TOTAL_COST_CENTS','PURCHASE_QTY','DEMAND_SHORTFALL_QTY','SAFETY_SHORTFALL_QTY','EXCEPTION_PRODUCT_COUNT']:
            assert summary[key] == expected[key],(key,summary[key],expected[key])
        report['plan'] = summary
        comparison = s.sql('SELECT * FROM PURCHASINGCOMPARISON').collect()[0].as_dict()
        for key,value in artifact['data']['comparisons'][0].items():
            if not key.endswith('DATE') and key!='WINDOW_END':
                assert comparison[key if key!='PLAN_ID' else 'PLAN']==value,(key,comparison,value)
        report['comparison'] = comparison
        baseline = s.sql('''SELECT SUM(TOTAL_COST_CENTS),SUM(QUANTITY),COUNT(*)
            FROM ALAA_DEMO_DATA.SMB_PURCHASING.SMB_BASELINE_ORDERS_V1''').collect()[0]
        assert baseline[0]==comparison['BASELINE_COST_CENTS'] and baseline[1]==comparison['BASELINE_PURCHASE_QTY']
        assert baseline[2]==len(artifact['data']['baseline_orders'])
        invalid = s.sql('''WITH orders AS (
            SELECT OFFER_ID,SUM(QUANTITY) Q,SUM(PACK_COUNT) P,SUM(TOTAL_COST_CENTS) C
            FROM ALAA_DEMO_DATA.SMB_PURCHASING.SMB_BASELINE_ORDERS_V1 GROUP BY 1)
            SELECT COUNT(*) FROM orders b JOIN SUPPLIEROFFER o ON o.OFFER_ID=b.OFFER_ID
            WHERE o.ELIGIBLE_PACKS=0 OR b.P>o.ELIGIBLE_PACKS OR b.Q<>b.P*o.PACK_SIZE
               OR b.Q<o.MINIMUM_ORDER_QTY OR b.Q>o.CONFIRMED_CAPACITY_QTY OR b.C<>b.Q*o.LANDED_UNIT_COST_CENTS''').collect()[0][0]
        assert invalid==0
        # Reconstruct both shortfall types per product, not merely equal aggregate totals.
        differences = s.sql('''WITH orders AS (
            SELECT PRODUCT_ID,SUM(QUANTITY) Q FROM ALAA_DEMO_DATA.SMB_PURCHASING.SMB_BASELINE_ORDERS_V1 GROUP BY 1),
            balances AS (SELECT n.*,p.SAFETY_STOCK_QTY,
                n.AVAILABLE_QTY+n.COUNTED_RECEIPTS_QTY+COALESCE(b.Q,0)-n.REMAINING_DEMAND_QTY AS ENDING
                FROM PURCHASINGNEED n JOIN PRODUCT p ON p.PRODUCT_ID=n.PRODUCT
                LEFT JOIN orders b ON b.PRODUCT_ID=n.PRODUCT)
            SELECT COUNT(*) FROM balances WHERE DEMAND_SHORTFALL_QTY<>GREATEST(0,-ENDING)
               OR SAFETY_SHORTFALL_QTY<>GREATEST(0,SAFETY_STOCK_QTY-GREATEST(0,ENDING))''').collect()[0][0]
        assert differences==0
        report['baseline_order_violations']=int(invalid)
        report['baseline_coverage_differences']=int(differences)
        tool_results = {}
        for name, args in [('purchasing_summary',{}),('purchasing_worklist',{'limit':50}),
                           ('recommended_purchases',{'limit':50}),('buyer_exceptions',{}),
                           ('incoming_orders',{}),('supplier_options',{'product_id':3}),('purchasing_comparison',{})]:
            response = json.loads(s.sql('CALL ALAA_RELAPP_PERSISTENCE.BACKORDER_AGENT.RAI_QUERY_MODEL(?,?)',
                                 params=[0,json.dumps({'id':name,'args':args})]).collect()[0][0])
            assert response['kind']=='tabular',response
            assert not response.get('truncated'),response
            tool_results[name] = response
            print('Verified agent catalog:',name,len(response['content']),flush=True)
        assert len(tool_results['purchasing_worklist']['content'])==30
        assert len(tool_results['recommended_purchases']['content'])==counts['PURCHASERECOMMENDATION']
        assert tool_results['purchasing_summary']['content'][0]['total_cost_cents']==expected['TOTAL_COST_CENTS']
        assert any(row['lead_time_days']==-1 and row['eligible_packs']==0
                   for row in tool_results['supplier_options']['content'])
        c=tool_results['purchasing_comparison']['content'][0]
        assert c['baseline_cost_cents']==comparison['BASELINE_COST_CENTS']
        assert c['optimized_cost_cents']==comparison['OPTIMIZED_COST_CENTS']
        assert c['savings_cents']==c['baseline_cost_cents']-c['optimized_cost_cents']
        report['tools'] = tool_results
        Path('data/smb_deployment_verification.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k!='tools'},default=str),flush=True)
    finally:
        s.close()


if __name__=='__main__': main()

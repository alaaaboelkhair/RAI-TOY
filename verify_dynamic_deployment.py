"""Read-only metadata checks for the code/view deployment (no business SQL)."""
import json
from pathlib import Path
from relationalai.config import create_config,SnowflakeConnection


def main():
    session=create_config().get_session(SnowflakeConnection)
    try:
        tables=[r.as_dict()['name'] for r in session.sql(
            'SHOW TABLES IN SCHEMA ALAA_RELAPP_PERSISTENCE.BACKORDER_MODEL').collect()]
        views=[r.as_dict()['name'] for r in session.sql(
            'SHOW VIEWS IN SCHEMA ALAA_RELAPP_PERSISTENCE.BACKORDER_MODEL').collect()]
        tasks=[r.as_dict() for r in session.sql(
            'SHOW TASKS IN SCHEMA ALAA_RELAPP_PERSISTENCE.BACKORDER_MODEL_META').collect()]
        assert not tables,tables
        assert {'PRODUCT','SUPPLIER','WAREHOUSE','INVENTORYPOSITION','SUPPLIEROFFER','INCOMINGORDER'}<=set(views),views
        assert not any(t['state']=='started' for t in tasks),[(t['name'],t['state']) for t in tasks]
        evidence={'status':'PASSED','schema':'ALAA_RELAPP_PERSISTENCE.BACKORDER_MODEL',
                  'tables':tables,'views':views,'tasks':[{k:t[k] for k in ('name','state','schedule')} for t in tasks],
                  'calculated_output_tables':0,'automatic_refresh_tasks_running':False}
        Path('data/dynamic_ontology_deployment_verification.json').write_text(json.dumps(evidence,indent=2)+'\n')
        print(json.dumps(evidence,indent=2))
    finally:session.close()


if __name__=='__main__':main()

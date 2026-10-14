"""Verify that a natural-language Cortex question actually invokes a fresh solve."""
from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace

from relationalai.config import create_config,SnowflakeConnection
from relationalai.agent.cortex import CortexAgentManager
from deploy_agent import agent_config


def envelopes(value):
    if isinstance(value,str):
        try:value=json.loads(value)
        except (ValueError,TypeError):return
    if isinstance(value,dict):
        if value.get('kind')=='tabular' and isinstance(value.get('content'),list):
            yield value
        for child in value.values():yield from envelopes(child)
    elif isinstance(value,list):
        for child in value:yield from envelopes(child)


def main():
    proof=Path('data/live_purchasing_chat_verification.json')
    proof.write_text(json.dumps({'status':'RUNNING'},indent=2)+'\n')
    args=SimpleNamespace(name='BACKORDER_ASSISTANT',agent_schema=None,llm='claude-opus-4-6')
    session=create_config().get_session(SnowflakeConnection)
    try:
        manager=CortexAgentManager(session=session,config=agent_config(args))
        question=("I'm planning our inventory purchases for the next month. Which products should "
                  "I prioritize ordering, who should I buy them from, and are there any shortages "
                  "I need to worry about? Give the planning dates and supplier quantities.")
        response=manager.chat().send(question)
        calls=[asdict(call) for call in response.tool_calls()]
        results=[asdict(result) for result in response.tool_results()]
        Path('data/live_purchasing_agent_response.txt').write_text(response.full_text()+'\n')
        Path('data/live_purchasing_agent_trace.json').write_text(
            json.dumps({'question':question,'tool_calls':calls,'tool_results':results},indent=2,default=str)+'\n')
        assert any('compute_purchasing_plan' in json.dumps(call) for call in calls),calls
        live=[e for e in envelopes(results) if any(isinstance(row,dict) and
            row.get('record_type')=='summary' and row.get('run_id') for row in e['content'])]
        assert live,'The chat did not return a fresh planning result'
        result=live[-1]
        assert not result.get('truncated'),result
        summary=next(r for r in result['content'] if r['record_type']=='summary')
        assert summary['purchase_pieces']==3226 and summary['cost_usd']==36922
        assert summary['demand_shortfall']==49 and summary['safety_shortfall']==15
        assert 'OPTIMAL' in summary['product']
        products=[r for r in result['content'] if r['record_type']=='product']
        assert len(products)==30
        orders=[o for row in products for o in json.loads(row['supplier_orders'])]
        assert len(orders)==45 and sum(o[1] for o in orders)==3226
        assert abs(sum(o[4] for o in orders)-36922)<1e-6
        answer=response.full_text()
        assert 'time limit' not in answer.lower() and 'incomplete' not in answer.lower(),answer
        assert '36,922' in answer or '36922' in answer,answer
        assert 'synthetic' in answer.lower() and 'supplier' in answer.lower(),answer
        assert 'safety glasses' in answer.lower() and 'nitrile gloves' in answer.lower(),answer
        evidence={'status':'PASSED','run_id':summary['run_id'],'product_rows':len(products),
            'order_lines':len(orders),'summary':summary,'fresh_tool_called':True,
            'complete_final_answer':True,'truncated':False}
        proof.write_text(json.dumps(evidence,indent=2)+'\n')
        Path('data/live_purchasing_tool_verification.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(evidence,indent=2),flush=True)
    except Exception as error:
        proof.write_text(json.dumps({'status':'FAILED','error':str(error)},indent=2)+'\n')
        raise
    finally:
        session.close()


if __name__=='__main__':main()

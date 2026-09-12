"""Paused exact-state LLM pilot; provider never receives simulator/filesystem tools."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

from .environment import Environment
from .interface import PolicyInterface, VERSION
from .guarded_baseline import run_policy
from .guarded_evaluation import provenance as mechanical_provenance
from .scene import ROOT

MODEL = 'gpt-5.6-sol'
MAX_OUTPUT = 2048
MAX_CALLS = 20
DEADLINE = 25.
# Official standard rates verified 2026-09-11; conservative local estimate, not invoice.
RATES = (4., .4, 20.)
PROMPT = '''Control a supported G1 humanoid in a MuJoCo simulation. Pick the red block
from the table and place it fully inside the basket, release it, withdraw the hand
at least 0.12 m from the object, and let it settle for at least 2 seconds.
Choose ONE primitive per response using the supplied action schema. No automatic
pickup skill exists. You choose approach, grasp, lift, transport, release and
withdrawal. Use current observations and previous actions to close the loop.
Physics pauses while you think; only action durations consume simulated time.
The entire episode must finish by simulated t=25 s including reset. At most 20
actions are allowed. A rejected action ends the episode, without retry. Do not
request an action that exceeds the remaining time. Hold is an explicit action.
All poses use world metres, Z up; joint readings use radians. move targets the
right grasp-site pose; orientation is a unit quaternion in w,x,y,z order mapping
site-local axes into world coordinates. The downward orientation is
[0.5,-0.5,0.5,0.5]; local hand X then points down and finger flexion is toward
world -X. The site is a hand reference, not an automatic object grasp or centering
operation. Hand closure 0 opens and 1 closes the coordinated three fingers.
Actions take 0.02 to 10 s. Motion interpolation and force-limited physical contacts
control the arm; completed means execution, not exact tracking or task success.
Workspace input bounds: X [0.15,0.55], Y [-0.60,-0.05], Z [0.60,1.15]. Some poses
inside these bounds are unreachable or rejected by the sampled collision guard.
Robot pelvis is fixed; do not walk. The arm starts in an overhead ready pose.
Static task geometry: table top z=0.70; block dimensions 0.05 x 0.07 x 0.12 m,
mass 0.06 kg; basket floor top z=0.712, rim top z=0.84, interior 0.17 x 0.17 m.
Basket observation z=0.70 is its reference, not the floor surface. The block must
be lifted at least 0.04 m above the table with hand contact for 0.2 s, then fully
contained, on the basket floor, without hand contact, nearly stationary for 2 s.
Keep contact gentle. The private evaluator measures maximum object penetration.
Use only the supplied observations; no images are supplied in this condition.
Return only the structured action. Do not claim success in prose.'''


def response_schema():
    schema = json.loads((ROOT/'experiments/humanoid-pick-place/schemas/action-v2.schema.json').read_text())
    # Strict Structured Outputs supports a nested union, not a union at the root.
    variants = []
    for branch in schema['oneOf']:
        props = {'action': {'type':'string', **branch['properties']['action']}, 'arguments': branch['properties']['arguments']}
        variants.append({'type':'object','properties':props,'required':list(props),'additionalProperties':False})
    return {'type':'object','properties':{'command':{'anyOf':variants}},'required':['command'],'additionalProperties':False}


def strict_json(text):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ValueError('Duplicate JSON field')
            result[key]=value
        return result
    def constant(_): raise ValueError('Nonfinite JSON constant')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def write_json(path, value):
    path = Path(path); temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n');temp.replace(path)


class Session:
    """Identical action count/deadline boundary for both policies; no score access."""
    def __init__(self, api): self.api=api;self.attempts=0
    def observe(self): return self.api.observe()
    def execute(self, request):
        now=self.observe()['time_s'];self.attempts+=1
        arguments=request.get('arguments') if isinstance(request,dict) else None
        seconds=arguments.get('seconds') if isinstance(arguments,dict) else None
        error=None
        if self.attempts>MAX_CALLS: error='Action limit reached'
        elif type(seconds) in (float,int) and math.isfinite(seconds) and math.ceil(seconds/.001)*.001>DEADLINE-now+1e-6:
            error='Action exceeds episode deadline'
        if error:
            response={'status':'rejected','error':error,'start_time_s':now,'end_time_s':now,'observation':self.observe()}
            self.api.env.events.append({'interface_request':request,'interface_response':response,'score':self.api.env.scorer.report()})
            return response
        return self.api.execute(request)


def payload(observation, history):
    public={'instruction_version':1,'remaining_time_s':max(0,DEADLINE-observation['time_s']),
            'remaining_actions':MAX_CALLS-len(history),'observation':observation,'history':history}
    return {'model':MODEL,'store':False,'reasoning':{'effort':'low'},'max_output_tokens':MAX_OUTPUT,
            'instructions':PROMPT,'input':[{'role':'user','content':json.dumps(public,sort_keys=True,allow_nan=False)}],
            'text':{'format':{'type':'json_schema','name':'humanoid_primitive','strict':True,'schema':response_schema()}}}


def estimate_cost(usage):
    if not isinstance(usage,dict) or not all(type(usage.get(k)) is int and usage[k]>=0 for k in ('input_tokens','output_tokens')):
        return None
    cached=usage.get('input_tokens_details',{}).get('cached_tokens',0)
    if type(cached) is not int or not 0<=cached<=usage['input_tokens']: return None
    return ((usage['input_tokens']-cached)*RATES[0]+cached*RATES[1]+usage['output_tokens']*RATES[2])/1e6


def http_transport(body):
    key=os.environ.get('OPENAI_API_KEY')
    if not key: raise ValueError('OPENAI_API_KEY not configured')
    req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(body).encode(),
                               headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=45) as response:
        return json.load(response),response.headers.get('x-request-id')


class Client:
    def __init__(self, root, budget=5., transport=None):
        if not math.isfinite(budget) or budget<=0: raise ValueError('Budget must be finite and positive')
        self.root=Path(root);self.budget=budget;self.transport=transport or http_transport
    def used(self):
        return sum(json.loads(p.read_text())['charged_estimate_usd'] for p in self.root.glob('**/call_*.json'))
    def call(self, body, destination):
        destination=Path(destination)
        if destination.exists(): raise ValueError('Model attempt already exists')
        # Bound request bytes; one token per UTF-8 byte plus overhead is a generous
        # reserve for these text-only prompts. Not a provider billing guarantee.
        size=len(json.dumps(body).encode())
        if size>120000: raise ValueError('Prompt byte limit reached')
        reserve=((size+4096)*RATES[0]+MAX_OUTPUT*RATES[2])/1e6
        if self.used()+reserve>self.budget: raise ValueError('Local API budget reached')
        record={'status':'pending','request':body,'reserved_usd':reserve,'charged_estimate_usd':reserve}
        write_json(destination,record)  # Reserve uncertain/interrupted calls before network I/O.
        start=time.monotonic()
        try:
            result,request_id=self.transport(body)
            record.update(raw_response=result,request_id=request_id,returned_model=result.get('model'),
                          response_id=result.get('id'),usage=result.get('usage'),service_tier=result.get('service_tier'))
            cost=estimate_cost(result.get('usage'));record['estimated_cost_usd']=cost
            if cost is not None:record['charged_estimate_usd']=cost
            if result.get('status')!='completed': raise ValueError('Response did not complete')
            content=[c for item in result.get('output',[]) if item.get('type')=='message' for c in item.get('content',[])]
            if any(c.get('type')=='refusal' for c in content): raise ValueError('Model refused request')
            decision=strict_json(''.join(c['text'] for c in content if c.get('type')=='output_text'))
            if not isinstance(decision,dict) or set(decision)!={'command'}:raise ValueError('Expected command wrapper')
            command=decision['command']
            if not isinstance(command,dict) or set(command)!={'action','arguments'}:raise ValueError('Invalid command fields')
            record.update(status='completed',command=command)
        except urllib.error.HTTPError as exc:
            record.update(status='api_error',error=f'HTTP {exc.code}',request_id=exc.headers.get('x-request-id'))
        except (urllib.error.URLError,TimeoutError,OSError) as exc:
            record.update(status='transport_error',error=type(exc).__name__)
        except (ValueError,TypeError,KeyError,AttributeError) as exc:
            record.update(status='invalid_response',error=str(exc))
        finally:
            record['api_round_trip_wall_s']=time.monotonic()-start;write_json(destination,record)
        return record


def provenance():
    result=mechanical_provenance('g2')
    protocol=ROOT/'experiments/humanoid-pick-place/protocols/L2.md'
    result['source_sha256'][str(protocol.relative_to(ROOT))]=hashlib.sha256(protocol.read_bytes()).hexdigest()
    result.update(protocol_id='humanoid-exact-state-L2',model=MODEL,reasoning_effort='low',
                  max_output_tokens=MAX_OUTPUT,max_actions=MAX_CALLS,deadline_s=DEADLINE,
                  prompt_sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),
                  response_schema_sha256=hashlib.sha256(json.dumps(response_schema(),sort_keys=True).encode()).hexdigest(),
                  token_prices_per_million=RATES)
    return result


def run_episode(folder,seed,controller,client=None,frozen=None):
    if controller not in ('conventional','llm'):raise ValueError('Unknown controller')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    actual=provenance()
    if frozen is not None and actual!=frozen:raise ValueError('Frozen configuration changed')
    env=Environment();env.reset(seed,True);session=Session(PolicyInterface(env))
    initial=session.observe();history=[];error=None;reason='deadline';calls=0
    env.save(folder)
    try:
        if controller=='conventional':
            error=run_policy(session,release_z=.88,release_closure=.4)
            reason='recipe_complete' if error is None else error
        else:
            if client is None:raise ValueError('LLM client required')
            while session.observe()['time_s']<DEADLINE-1e-6 and calls<MAX_CALLS:
                observation=session.observe();body=payload(observation,history);calls+=1
                record=client.call(body,folder/f'call_{calls:03}.json')
                if record['status']!='completed':
                    error=record.get('error',record['status']);reason=record['status'];break
                command=record['command']
                request={'schema_version':VERSION,'instruction_version':1,'request_id':f'llm-{calls}',**command}
                response=session.execute(request)
                history.append({'action':request,'response':response})
                env.save(folder)
                print(json.dumps({'seed':seed,'call':calls,'action':command,'status':response['status'],'time_s':env.data.time}),flush=True)
                if response['status']!='completed':error=response.get('error');reason=response['status'];break
            if calls==MAX_CALLS and env.data.time<DEADLINE-1e-6 and error is None:reason='action_limit';error='Action limit reached'
    except (ValueError,RuntimeError,OSError) as exc:
        error=str(exc);reason=type(exc).__name__
    finally:
        env.save(folder)
        attempts=[json.loads(p.read_text()) for p in folder.glob('call_*.json')]
        report={**env.scorer.report(),'seed':seed,'controller':controller,'termination':reason,'error':error,
                'initial':initial,'final':session.observe(),'action_attempts':session.attempts,'model_calls':len(attempts),
                'estimated_cost_usd':sum(a.get('estimated_cost_usd') or 0 for a in attempts),
                'charged_estimate_usd':sum(a['charged_estimate_usd'] for a in attempts),
                'unknown_usage_attempts':sum(a.get('estimated_cost_usd') is None for a in attempts),'provenance':actual}
        report['gate_success']=bool(report['success'] and report['max_object_penetration_m']<=.002 and env.data.time<=DEADLINE+1e-6 and error is None)
        write_json(folder/'report.json',report)
    return report


def run_pilot(folder,seeds,budget=5.,transport=None):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    frozen=provenance();write_json(folder/'manifest.json',{'development_only':True,'seeds':seeds,'budget_usd':budget,'provenance':frozen})
    client=Client(folder,budget,transport);reports=[]
    for seed in seeds:
        for controller in ('conventional','llm'):
            reports.append(run_episode(folder/f'seed-{seed:04}'/controller,seed,controller,client,frozen))
            summary={'development_only':True,'status':'running','reports':reports,'charged_estimate_usd':client.used()}
            write_json(folder/'summary.json',summary)
    summary['status']='complete';write_json(folder/'summary.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seeds',type=int,nargs='+',default=[700,701,702])
    parser.add_argument('--budget-usd',type=float,default=5.)
    args=parser.parse_args()
    if len(set(args.seeds))!=len(args.seeds):parser.error('Seeds must be unique')
    run_pilot(args.output,args.seeds,args.budget_usd)


if __name__=='__main__':main()

import copy,json,tempfile
from pathlib import Path
from types import SimpleNamespace
from humanoid_sim.visual_policy_runner import run_visual_episode,HoldStub,parse_and_validate_response
OBS=json.loads(Path('/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture/seed-820/00-observation.json').read_text())
class FakeSession:
 def __init__(self,execute_error=False):self.env=SimpleNamespace(data=SimpleNamespace(time=.5));self.n=0;self.execute_error=execute_error
 def capture(self):
  self.n+=1;o=copy.deepcopy(OBS);o['observation_id']=str(self.n);o['time_s']=self.env.data.time;o['robot_state']['time_s']=o['time_s'];return o
 def execute(self,oid,req):
  if self.execute_error:raise RuntimeError('injected interface exception')
  start=self.env.data.time;self.env.data.time+=req['arguments']['seconds'];return {'status':'completed','start_time_s':start,'end_time_s':self.env.data.time}
for name,session,model,kwargs in [
 ('NaN response',FakeSession(),lambda _: {'command':{'action':'hand','arguments':{'closure':float('nan'),'seconds':1}}},{}),
 ('Malformed response envelope',FakeSession(),lambda _: {'output':None},{}),
 ('Execution exception',FakeSession(True),HoldStub(.02),{}),
 ('21 allowed calls',FakeSession(),HoldStub(.02),{'max_calls':21}),
 ('Deadline overshoot',FakeSession(),HoldStub(1),{'max_calls':1,'deadline':1}),
]:
 with tempfile.TemporaryDirectory() as tmp:
  folder=Path(tmp)/'run'
  try:r=run_visual_episode(folder,session,model,**kwargs);print(name, 'returned',r['termination_reason'],'calls',r['model_calls'],'time',r['simulated_time_s'])
  except Exception as e:print(name,'raised',type(e).__name__,'final report exists:',(folder/'report.json').exists())
print('Boolean seconds accepted:',parse_and_validate_response({'command':{'action':'hold','arguments':{'seconds':True}}}))

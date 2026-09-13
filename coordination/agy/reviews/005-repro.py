import base64,copy,hashlib,json,tempfile
from pathlib import Path
from humanoid_sim.visual_provider_adapter import VisualProviderAdapter,build_responses_request,export_request
SOURCE=Path('experiments/humanoid-pick-place/results/visual_policy_scaffold/demo_request_payload.json')
payload=json.loads(SOURCE.read_text())
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp)
 def transport(body):
  print('pending record exists during transport:',(root/'pending/provider_call_001.json').exists())
  return ()
 adapter=VisualProviderAdapter(transport=transport,record_dir=root/'pending',model='offline-fixture-model')
 try: adapter(payload)
 except Exception as exc: print('empty tuple:',type(exc).__name__,'record exists:',(root/'pending/provider_call_001.json').exists())
 bad=copy.deepcopy(payload);bad['observation']['rgb_png_base64']='invalid'
 calls=[]
 adapter=VisualProviderAdapter(transport=lambda body:calls.append(body),record_dir=root/'invalid',model='offline-fixture-model')
 try: adapter(bad)
 except Exception as exc: print('bad PNG:',type(exc).__name__,'call_count:',adapter.call_count,'actual callbacks:',len(calls),'records:',list((root/'invalid').glob('*.json')))
 raw=base64.b64decode(payload['observation']['rgb_png_base64'])
 truncated=copy.deepcopy(payload);data=raw[:100]
 truncated['observation']['rgb_png_base64']=base64.b64encode(data).decode()
 truncated['observation']['rgb_sha256']=hashlib.sha256(data).hexdigest()
 try:
  build_responses_request(truncated,model='offline-fixture-model');print('truncated PNG accepted: True')
 except Exception as exc: print('truncated PNG rejected:',type(exc).__name__)
 destination=root/'same.json'
 export_request(SOURCE,destination,model='offline-fixture-model',manifest_path=destination)
 print('same output/manifest path kept request:', 'input' in json.loads(destination.read_text()))
print('omitted model defaults to:',build_responses_request(payload)['model'])

import json
from pathlib import Path
import tempfile
import unittest
import numpy as np

from humanoid_sim.environment import Environment
from humanoid_sim.interface import PolicyInterface
from humanoid_sim.llm_runner import Client, Session, payload, run_episode, response_schema


def reply(command=None,usage=True):
    result={'model':'gpt-5.6-sol','id':'fake-response','status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'command':command or {'action':'hold','arguments':{'seconds':2}}})}]}]}
    if usage:result['usage']={'input_tokens':100,'output_tokens':30,'input_tokens_details':{'cached_tokens':0}}
    return result,'fake-request'


class LLMTests(unittest.TestCase):
    def test_replay_labels_distinguish_llm_conventional_and_unknown(self):
        from humanoid_sim.render import controller_label
        self.assertIn('LLM: gpt-5.6-sol', controller_label({'controller':'llm','provenance':{'model':'gpt-5.6-sol'}}))
        self.assertNotIn('no LLM', controller_label({'controller':'llm'}))
        self.assertIn('no LLM', controller_label({'controller':'conventional_exact_state_guarded'}))
        self.assertIn('unclassified', controller_label({}))

    def test_public_payload_contains_no_scoring_or_recipe(self):
        api=PolicyInterface(Environment());body=payload(api.observe(),[])
        public=json.loads(body['input'][0]['content'])
        self.assertEqual(set(public),{'instruction_version','remaining_time_s','remaining_actions','observation','history'})
        self.assertNotIn('score',public['observation'])
        self.assertNotIn('tools',body)
        self.assertNotIn('0.88',body['instructions'])
        self.assertNotIn('release_target',json.dumps(body))
        self.assertEqual(len(response_schema()['properties']['command']['anyOf']),3)

    def test_strict_schema_discriminators_have_explicit_types(self):
        # API rejected L1's const-only action discriminator before model inference.
        for variant in response_schema()['properties']['command']['anyOf']:
            self.assertEqual(variant['properties']['action']['type'], 'string')
            self.assertIn(variant['properties']['action']['const'], ('move','hand','hold'))

    def test_deadline_rejection_does_not_advance_or_resize(self):
        env=Environment();session=Session(PolicyInterface(env));env.hold(10);env.hold(10)
        before=env.data.qpos.copy();timestamp=env.data.time
        r=session.execute({'action':'hold','arguments':{'seconds':5}})
        self.assertEqual(r['status'],'rejected')
        self.assertEqual(env.data.time,timestamp);np.testing.assert_array_equal(env.data.qpos,before)

    def test_client_logs_raw_result_usage_and_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);client=Client(root,budget=.1,transport=lambda body:reply())
            result=client.call({'model':'gpt-5.6-sol'},root/'call_001.json')
            self.assertEqual(result['status'],'completed');self.assertEqual(result['request_id'],'fake-request')
            self.assertGreater(result['estimated_cost_usd'],0)
            with self.assertRaises(ValueError):client.call({},root/'call_001.json')
            client.budget=.00001
            with self.assertRaisesRegex(ValueError,'budget'):client.call({},root/'call_002.json')
            self.assertFalse((root/'call_002.json').exists())

    def test_unknown_usage_and_timeout_keep_reserve(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);client=Client(root,transport=lambda body:reply(usage=False))
            record=client.call({},root/'call_001.json')
            self.assertIsNone(record['estimated_cost_usd'])
            self.assertEqual(record['charged_estimate_usd'],record['reserved_usd'])
            def timeout(_):raise TimeoutError('sensitive text must not be logged')
            client.transport=timeout;r=client.call({},root/'call_002.json')
            self.assertEqual(r['status'],'transport_error');self.assertEqual(r['error'],'TimeoutError')
            self.assertGreater(client.used(),record['reserved_usd'])

    def test_model_action_executes_and_rejection_is_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);calls=[]
            def transport(body):
                calls.append(body)
                if len(calls)==1:return reply({'action':'hold','arguments':{'seconds':.02}})
                return reply({'action':'move','arguments':{'xyz_m':[5,0,1],'quaternion_wxyz':[1,0,0,0],'seconds':2}})
            r=run_episode(root/'episode',300,'llm',Client(root,transport=transport))
            self.assertFalse(r['gate_success']);self.assertEqual(r['model_calls'],2)
            self.assertEqual(r['termination'],'rejected');self.assertAlmostEqual(r['final']['time_s'],.52)
            self.assertEqual(json.loads((root/'episode/report.json').read_text())['model_calls'],2)
            sent=json.loads(calls[1]['input'][0]['content'])
            self.assertEqual(len(sent['history']),1)
            self.assertNotIn('score',sent['history'][0]['response'])

    def test_refusal_and_nonfinite_response_never_become_actions(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def refusal(_):return {'model':'x','status':'completed','output':[{'type':'message','content':[{'type':'refusal','refusal':'no'}]}]},'id'
            client=Client(root,transport=refusal)
            self.assertEqual(client.call({},root/'call_001.json')['status'],'invalid_response')
            def invalid(_):
                r,ident=reply();r['output'][0]['content'][0]['text']='{"command":NaN}';return r,ident
            client.transport=invalid
            self.assertEqual(client.call({},root/'call_002.json')['status'],'invalid_response')


if __name__=='__main__':unittest.main()

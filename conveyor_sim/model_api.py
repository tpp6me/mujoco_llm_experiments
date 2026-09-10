"""Shared image-to-selection Responses API client; no simulator truth is sent."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

MODELS = ['gpt-5.6-sol', 'gpt-6-astra']
# Standard token prices verified in official model documentation, 2026-09-09.
PRICES = {'gpt-5.6-sol': (4.0, .4, 20.0), 'gpt-6-astra': (10.0, 1.0, 50.0)}
MAX_OUTPUT = 4096
PROMPT = '''You select cubes for a simulated conveyor robot from an overhead image.
Follow the CURRENT instruction exactly. Return every visible cube it requires
rejecting, ordered by arrival at the robot (largest world Y first). For "next two",
select the first two matching cubes in arrival order, not every matching cube.
Use the supplied camera calibration to interpret arrival direction when the view
is rotated. Estimate the center of each selected cube's TOP FACE in original image
pixels (u right, v down). Static pixel rulers are not objects. Return only the
required JSON selections, with perceived color. Do not supply motion or timings.
Select the requested objects even if a command might now be late; the runtime
independently checks deadlines. At most three cubes are present. No prior episode
history is available or needed; the supplied instruction is the active rule.'''
SCHEMA = {'type': 'object', 'properties': {'selections': {'type': 'array', 'items': {
    'type': 'object', 'properties': {'u': {'type': 'number'}, 'v': {'type': 'number'},
                                   'color': {'type': 'string', 'enum': ['red', 'blue', 'green']}},
    'required': ['u', 'v', 'color'], 'additionalProperties': False}}},
    'required': ['selections'], 'additionalProperties': False}
PUBLIC_FIELDS = ['instruction', 'time_s', 'rule_version', 'belt_velocity_m_s', 'calibration']


def validate_selection(value):
    if not isinstance(value, dict) or set(value) != {'selections'} or not isinstance(value['selections'], list):
        raise ValueError('Expected a selections object')
    if len(value['selections']) > 3:
        raise ValueError('More than three selected cubes')
    selections = []
    for item in value['selections']:
        if not isinstance(item, dict) or set(item) != {'u', 'v', 'color'}:
            raise ValueError('Invalid selection fields')
        if item['color'] not in {'red', 'blue', 'green'}:
            raise ValueError('Invalid perceived color')
        for key, bound in [('u', 960), ('v', 720)]:
            number = item[key]
            if isinstance(number, bool) or not isinstance(number, (float, int)) or not math.isfinite(number) or not 0 <= number < bound:
                raise ValueError('Invalid image coordinate')
        selections.append({'pixel_xy': [item['u'], item['v']], 'perceived_color': item['color']})
    return selections


def payload(model, observation):
    if model not in MODELS:
        raise ValueError('Model outside the frozen comparison')
    image = Path(observation['image_path']).read_bytes()
    public = {key: observation[key] for key in PUBLIC_FIELDS}
    return {'model': model, 'store': False, 'reasoning': {'effort': 'low'}, 'max_output_tokens': MAX_OUTPUT,
            'instructions': PROMPT,
            'input': [{'role': 'user', 'content': [
                {'type': 'input_text', 'text': json.dumps(public, sort_keys=True)},
                {'type': 'input_image', 'image_url': 'data:image/png;base64,' + base64.b64encode(image).decode(), 'detail': 'high'}]}],
            'text': {'format': {'type': 'json_schema', 'name': 'cube_selection', 'strict': True, 'schema': SCHEMA}}}


def cost_estimate(model, usage):
    rate, cached_rate, output_rate = PRICES[model]
    inputs = usage.get('input_tokens', 0)
    cached = usage.get('input_tokens_details', {}).get('cached_tokens', 0)
    return ((inputs-cached)*rate + cached*cached_rate + usage.get('output_tokens', 0)*output_rate)/1e6


def call(model, observation, destination, *, transport=None):
    """One attempt only. Preserve failures and usage without logging credentials."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise ValueError('Refusing to overwrite a model attempt')
    body = payload(model, observation)
    record = {'requested_model': model, 'settings': {'reasoning_effort': 'low', 'max_output_tokens': MAX_OUTPUT, 'image_detail': 'high'},
              'observation': {k: observation[k] for k in PUBLIC_FIELDS}, 'image_sha256': hashlib.sha256(Path(observation['image_path']).read_bytes()).hexdigest(),
              'prompt_sha256': hashlib.sha256(PROMPT.encode()).hexdigest(),
              'schema_sha256': hashlib.sha256(json.dumps(SCHEMA, sort_keys=True).encode()).hexdigest(),
              'status': 'pending', 'selections': [], 'usage': {}, 'estimated_cost_usd': 0}
    started = time.monotonic()
    try:
        if transport is None:
            key = os.environ.get('OPENAI_API_KEY')
            if not key:
                raise ValueError('OPENAI_API_KEY is not configured')
            request = urllib.request.Request('https://api.openai.com/v1/responses',
                data=json.dumps(body).encode(), headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=45) as response:
                result = json.load(response)
                record['request_id'] = response.headers.get('x-request-id')
        else:
            result = transport(body)
        record.update(returned_model=result.get('model'), response_id=result.get('id'), usage=result.get('usage') or {},
                      service_tier=result.get('service_tier'), response_status=result.get('status'), raw_response=result)
        record['estimated_cost_usd'] = cost_estimate(model, record['usage'])
        if result.get('status') != 'completed':
            raise ValueError('Response did not complete')
        chunks = [c for item in result.get('output', []) if item.get('type') == 'message' for c in item.get('content', [])]
        if any(c.get('type') == 'refusal' for c in chunks):
            raise ValueError('Model refused the request')
        text = ''.join(c['text'] for c in chunks if c.get('type') == 'output_text')
        record['selections'] = validate_selection(json.loads(text))
        record['status'] = 'completed'
    except urllib.error.HTTPError as error:
        # Do not echo provider error bodies: an auth error can contain key fragments.
        record.update(status='api_error', error=f'HTTP {error.code}', http_status=error.code)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        record.update(status='transport_error', error=type(error).__name__)
    except (ValueError, TypeError, KeyError) as error:
        record.update(status='invalid_response', error=str(error))
    finally:
        record['api_round_trip_wall_s'] = time.monotonic()-started
        destination.write_text(json.dumps(record, indent=2)+'\n')
    return record


def check_budget(model, log_root, limit=5.0):
    files = Path(log_root).glob(f'**/{model}/**/call_*.json')
    calls = [json.loads(p.read_text()) for p in files]
    # Charge uncertain attempts their conservative reserve so timeouts cannot
    # silently bypass the local budget. This is not an API billing guarantee.
    reserve = (20000*PRICES[model][0] + MAX_OUTPUT*PRICES[model][2])/1e6
    used = sum(c['estimated_cost_usd'] if c.get('usage') else reserve for c in calls)
    if used + reserve > limit:
        raise ValueError(f'Local estimated ${limit:g} per-model budget reached')

"""Responses API visual provider adapter with injected offline transport.

Translates provider-neutral visual policy public payloads into OpenAI Responses API
wire format with image content items and strict structured output. Requires an
explicitly injected offline transport; does not instantiate network clients or access
credentials.
"""
import argparse
import base64
import binascii
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import time

from PIL import Image

from .scene import ROOT
from .interface import VERSION, INSTRUCTION_VERSION
from .visual_policy_runner import (
    VISUAL_PROMPT,
    VisualPolicyError,
    ModelRefusalError,
    MalformedResponseError,
    strict_json,
    to_json_safe,
    write_json,
    action_schema,
    allowlist_camera,
    allowlist_robot_state,
    sanitize_action_for_history,
    sanitize_response_for_history,
    parse_and_validate_response,
    _validate_finite_float,
    _validate_int,
    build_public_payload
)

DEFAULT_MAX_OUTPUT = 2048
DEFAULT_DETAIL = 'high'
DEFAULT_REASONING_EFFORT = 'low'
ALLOWED_DETAILS = ('high', 'low', 'auto', 'original')
PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


class VisualAdapterError(VisualPolicyError):
    """Base exception for visual provider adapter."""
    pass


class MalformedEnvelopeError(MalformedResponseError):
    """Raised when provider envelope is incomplete, failed, or structurally invalid."""
    pass


class ProviderRefusalError(ModelRefusalError):
    """Raised when provider envelope indicates a refusal."""
    pass


def validate_png_base64(b64_png, expected_sha256=None):
    """Validate base64 string and decode/verify complete PNG image data.

    Returns (raw_bytes, sha256_hex, (width, height)).
    Raises ValueError on invalid base64, non-PNG magic, hash mismatch,
    or truncated/corrupted raster image data.
    """
    if not isinstance(b64_png, str) or not b64_png:
        raise ValueError('b64_png must be a non-empty string')
    try:
        raw_bytes = base64.b64decode(b64_png, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f'Malformed base64 string: {exc}')

    if len(raw_bytes) < 8 or raw_bytes[:8] != PNG_MAGIC:
        raise ValueError('Decoded bytes do not match PNG magic signature')

    sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
    if expected_sha256 is not None and str(expected_sha256).lower() != sha256_hex.lower():
        raise ValueError(f'Image SHA-256 mismatch: expected {expected_sha256}, got {sha256_hex}')

    # Fully verify and load/decode the raster data to catch truncated or corrupted pixel chunks
    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            if img.format != 'PNG':
                raise ValueError(f'Image format is not PNG, got {img.format}')
            img.load()  # Force decompression and decoding of all pixel chunks
            size = (img.width, img.height)
    except Exception as exc:
        raise ValueError(f'Corrupted or truncated PNG image data: {exc}')

    return raw_bytes, sha256_hex, size


def build_responses_request(
    public_payload,
    model,
    detail=DEFAULT_DETAIL,
    max_output_tokens=DEFAULT_MAX_OUTPUT,
    reasoning_effort=DEFAULT_REASONING_EFFORT
):
    """Pure public-payload-to-request builder for OpenAI Responses wire format.

    Requires an explicit model identifier. Sanitizes public payload against allowlists,
    excludes planted private fields, encodes the image as an input_image item (data URL),
    encodes observation text without the base64 image, and attaches strict structured output schema.
    """
    if not isinstance(public_payload, dict):
        raise ValueError(f'public_payload must be a dict, got {type(public_payload).__name__}')
    if not isinstance(model, str) or not model.strip():
        raise ValueError(f'Explicit non-empty model identifier is required, got {model!r}')
    if detail not in ALLOWED_DETAILS:
        raise ValueError(f'detail must be one of {ALLOWED_DETAILS}, got {detail!r}')
    max_output_tokens = _validate_int(max_output_tokens, 'max_output_tokens')
    if max_output_tokens <= 0:
        raise ValueError(f'max_output_tokens must be positive, got {max_output_tokens}')

    obs = public_payload.get('observation')
    if not isinstance(obs, dict):
        raise ValueError('public_payload missing observation dictionary')

    b64_png = obs.get('rgb_png_base64')
    expected_sha256 = obs.get('rgb_sha256')
    raw_bytes, image_sha256, (img_w, img_h) = validate_png_base64(b64_png, expected_sha256)

    # Allowlist camera and robot proprioception, excluding any private truth
    clean_camera = allowlist_camera(obs.get('camera'))
    clean_robot_state = allowlist_robot_state(obs.get('robot_state'))
    obs_time_s = _validate_finite_float(obs.get('time_s'), 'observation.time_s')
    obs_id = str(obs.get('observation_id', ''))
    if not obs_id:
        raise ValueError('observation missing observation_id')
    schema_version = str(obs.get('schema_version', 'humanoid-visual-v1'))

    # Sanitize observation for the text payload:
    # Explicitly excludes rgb_png_base64 so image is not duplicated in text JSON.
    text_observation = {
        'schema_version': schema_version,
        'observation_id': obs_id,
        'time_s': obs_time_s,
        'camera': clean_camera,
        'robot_state': clean_robot_state,
        'rgb_sha256': image_sha256
    }

    # Bounded history (at most 20 preceding steps)
    raw_history = public_payload.get('history', [])
    if not isinstance(raw_history, list):
        raise ValueError('history must be a list')
    history_slice = raw_history[-20:] if len(raw_history) > 20 else raw_history
    sanitized_history = [
        {
            'action': sanitize_action_for_history(h.get('action') if isinstance(h, dict) else None),
            'response': sanitize_response_for_history(h.get('response') if isinstance(h, dict) else None)
        }
        for h in history_slice
    ]

    instruction_version = _validate_int(public_payload.get('instruction_version', INSTRUCTION_VERSION), 'instruction_version')
    remaining_time_s = _validate_finite_float(public_payload.get('remaining_time_s', 0.0), 'remaining_time_s')
    remaining_actions = _validate_int(public_payload.get('remaining_actions', 0), 'remaining_actions')

    text_public = {
        'instruction_version': instruction_version,
        'remaining_time_s': remaining_time_s,
        'remaining_actions': remaining_actions,
        'observation': text_observation,
        'history': sanitized_history
    }
    text_json_str = json.dumps(text_public, sort_keys=True, allow_nan=False)

    instruction_text = str(public_payload.get('instruction', VISUAL_PROMPT))

    request_body = {
        'model': model.strip(),
        'store': False,
        'max_output_tokens': max_output_tokens,
        'instructions': instruction_text,
        'input': [
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'input_text',
                        'text': text_json_str
                    },
                    {
                        'type': 'input_image',
                        'image_url': f'data:image/png;base64,{b64_png}',
                        'detail': detail
                    }
                ]
            }
        ],
        'text': {
            'format': {
                'type': 'json_schema',
                'name': 'humanoid_primitive',
                'strict': True,
                'schema': action_schema()
            }
        }
    }

    if reasoning_effort:
        request_body['reasoning'] = {'effort': str(reasoning_effort)}

    # Ensure full serializability without NaN/Infinity
    json.dumps(request_body, allow_nan=False)
    return request_body


def validate_response_envelope(raw_response):
    """Validate OpenAI Responses envelope and extract structured primitive command.

    Rejects incomplete/failed envelopes even if valid command is nested inside.
    Rejects refusals, missing/multiple messages, and unexpected tool outputs.
    Ignores reasoning metadata. Reuses primitive validator.
    """
    if isinstance(raw_response, str):
        try:
            raw_response = strict_json(raw_response)
        except ValueError as exc:
            raise MalformedResponseError(f'Invalid JSON in provider envelope: {exc}')
    if not isinstance(raw_response, dict):
        raise MalformedResponseError(f'Provider response must be dict, got {type(raw_response).__name__}')

    # Check top-level refusal
    if raw_response.get('refusal'):
        raise ModelRefusalError(f'Model refused: {raw_response["refusal"]}')
    if raw_response.get('status') == 'refusal':
        raise ModelRefusalError(f'Model status is refusal: {raw_response.get("error", "refusal")}')

    # Envelope status MUST be 'completed'
    status = raw_response.get('status')
    if status != 'completed':
        # An incomplete, failed or malformed envelope must never execute an apparently valid command nested inside
        raise MalformedResponseError(f'Provider envelope status is not completed: {status!r}')

    # Check for error at root
    if raw_response.get('error'):
        raise MalformedResponseError(f'Provider returned error: {raw_response["error"]}')

    output = raw_response.get('output')
    if not isinstance(output, list) or len(output) == 0:
        raise MalformedResponseError('Provider response missing or empty output list')

    message_items = []
    for item in output:
        if not isinstance(item, dict):
            raise MalformedResponseError(f'Output item must be dict, got {type(item).__name__}')
        item_type = item.get('type')
        if item_type == 'reasoning':
            # Reasoning metadata may be ignored, never interpreted as a command
            continue
        elif item_type in ('tool_call', 'function_call', 'call', 'tool_output'):
            raise MalformedResponseError(f'Unexpected tool output in provider response: {item_type!r}')
        elif item_type == 'message':
            message_items.append(item)
        else:
            raise MalformedResponseError(f'Unexpected output item type: {item_type!r}')

    if len(message_items) == 0:
        raise MalformedResponseError('No message items found in provider output')
    if len(message_items) > 1:
        raise MalformedResponseError(f'Multiple action messages in provider output: {len(message_items)}')

    msg = message_items[0]
    contents = msg.get('content')
    if not isinstance(contents, list) or len(contents) == 0:
        raise MalformedResponseError('Message item missing or empty content list')

    output_text_parts = []
    for c in contents:
        if not isinstance(c, dict):
            raise MalformedResponseError(f'Message content item must be dict, got {type(c).__name__}')
        c_type = c.get('type')
        if c_type == 'refusal':
            raise ModelRefusalError(f'Model refusal: {c.get("refusal", "refusal")}')
        elif c_type == 'output_text':
            text = c.get('text')
            if not isinstance(text, str):
                raise MalformedResponseError('output_text text must be a string')
            output_text_parts.append(text)
        elif c_type in ('tool_call', 'function_call'):
            raise MalformedResponseError(f'Unexpected tool content in message: {c_type!r}')
        else:
            raise MalformedResponseError(f'Unexpected message content type: {c_type!r}')

    if len(output_text_parts) == 0:
        raise MalformedResponseError('No output_text part found in message content')
    if len(output_text_parts) > 1:
        raise MalformedResponseError(f'Multiple output_text parts in message content: {len(output_text_parts)}')

    raw_text = output_text_parts[0]
    try:
        decision = strict_json(raw_text)
    except ValueError as exc:
        raise MalformedResponseError(f'Failed to parse output text JSON: {exc}')

    if not isinstance(decision, dict) or set(decision.keys()) != {'command'} or not isinstance(decision['command'], dict):
        raise MalformedResponseError('Expected JSON object with single key "command"')

    # Reuse runner's primitive validator
    return parse_and_validate_response(decision)


class VisualProviderAdapter:
    """Multimodal adapter connecting visual policy loop to injected Responses wire transport."""

    def __init__(
        self,
        transport,
        model,
        max_output_tokens=DEFAULT_MAX_OUTPUT,
        detail=DEFAULT_DETAIL,
        reasoning_effort=DEFAULT_REASONING_EFFORT,
        record_dir=None,
        clock=time.monotonic
    ):
        if transport is None or not callable(transport):
            raise ValueError('Explicit callable transport required; network access is disabled in offline mode')
        if not isinstance(model, str) or not model.strip():
            raise ValueError(f'Explicit non-empty model identifier is required, got {model!r}')
        if detail not in ALLOWED_DETAILS:
            raise ValueError(f'detail must be one of {ALLOWED_DETAILS}, got {detail!r}')

        self.transport = transport
        self.model = str(model).strip()
        self.max_output_tokens = _validate_int(max_output_tokens, 'max_output_tokens')
        self.detail = detail
        self.reasoning_effort = str(reasoning_effort) if reasoning_effort else None
        self.record_dir = Path(record_dir) if record_dir is not None else None
        self.clock = clock
        self.invocation_count = 0
        self.transport_call_count = 0

    @property
    def call_count(self):
        """Number of actual transport calls executed."""
        return self.transport_call_count

    def __call__(self, public_payload):
        self.invocation_count += 1
        inv_num = self.invocation_count

        record_file = None
        if self.record_dir is not None:
            self.record_dir.mkdir(parents=True, exist_ok=True)
            record_file = self.record_dir / f'provider_call_{inv_num:03}.json'
            if record_file.exists():
                raise ValueError(f'Adapter attempt record already exists: {record_file}')

        # 1. Preflight preparation & request building
        try:
            request_body = build_responses_request(
                public_payload,
                model=self.model,
                detail=self.detail,
                max_output_tokens=self.max_output_tokens,
                reasoning_effort=self.reasoning_effort
            )
        except Exception as exc:
            # Retain preparation failures without pretending a callback occurred
            if record_file is not None:
                prep_record = {
                    'invocation': inv_num,
                    'call': 0,
                    'status': 'preparation_error',
                    'offline_evidence': True,
                    'injected_transport': False,
                    'transport_invoked': False,
                    'model': self.model,
                    'detail': self.detail,
                    'error': f'{type(exc).__name__}: {exc}',
                    'request': None,
                    'raw_response': None,
                    'wall_latency_s': 0.0,
                    'usage': {'status': 'unknown'}
                }
                write_json(record_file, prep_record)
            raise

        obs = public_payload.get('observation', {})
        image_sha256 = obs.get('rgb_sha256')
        req_bytes = json.dumps(request_body, sort_keys=True, allow_nan=False).encode('utf-8')
        request_sha256 = hashlib.sha256(req_bytes).hexdigest()
        start_wall = self.clock()

        # 2. Persist pending request record before invoking transport
        # Note: If record cannot be written, transport MUST NOT be invoked!
        if record_file is not None:
            pending_record = {
                'invocation': inv_num,
                'call': self.transport_call_count + 1,
                'status': 'pending',
                'offline_evidence': True,
                'injected_transport': True,
                # A process can exit between writing this record and dispatching.
                # Pending records cannot prove whether a request reached transport.
                'transport_invoked': None,
                'model': self.model,
                'detail': self.detail,
                'image_sha256': image_sha256,
                'request_sha256': request_sha256,
                'request': request_body,
                'raw_response': None,
                'wall_latency_s': 0.0,
                'usage': {'status': 'unknown'}
            }
            write_json(record_file, pending_record)

        # 3. Invoke transport
        self.transport_call_count += 1
        call_num = self.transport_call_count

        attempt_record = {
            'invocation': inv_num,
            'call': call_num,
            'status': 'pending',
            'offline_evidence': True,
            'injected_transport': True,
            'transport_invoked': True,
            'model': self.model,
            'detail': self.detail,
            'image_sha256': image_sha256,
            'request_sha256': request_sha256,
            'request': request_body,
            'raw_response': None,
            'wall_latency_s': 0.0,
            'usage': {'status': 'unknown'}
        }

        try:
            raw_response = self.transport(request_body)
            wall_s = self.clock() - start_wall
            attempt_record['wall_latency_s'] = wall_s
            attempt_record['raw_response'] = raw_response
        except (KeyboardInterrupt, SystemExit) as exc:
            attempt_record['status'] = 'interrupted'
            attempt_record['error'] = type(exc).__name__
            if record_file is not None:
                write_json(record_file, attempt_record)
            raise
        except Exception as exc:
            wall_s = self.clock() - start_wall
            attempt_record['wall_latency_s'] = wall_s
            attempt_record['status'] = 'transport_exception'
            attempt_record['error'] = f'{type(exc).__name__}: {exc}'
            if record_file is not None:
                write_json(record_file, attempt_record)
            raise

        # 4. Enclose metadata extraction and envelope validation in the same failure-accounting boundary
        try:
            if isinstance(raw_response, tuple):
                if len(raw_response) != 2 or not (
                    raw_response[1] is None or isinstance(raw_response[1], str)
                ):
                    raise MalformedResponseError('Transport tuple must be (envelope, request ID string or null)')
                raw_dict, req_id = raw_response
            else:
                raw_dict = raw_response
                req_id = None

            if isinstance(raw_dict, str):
                try:
                    raw_dict = strict_json(raw_dict)
                except ValueError as exc:
                    raise MalformedResponseError(f'Invalid JSON in provider envelope: {exc}')

            if not isinstance(raw_dict, dict):
                raise MalformedResponseError(f'Provider response must be dict, got {type(raw_dict).__name__}')

            attempt_record['response_id'] = raw_dict.get('id')
            if req_id is not None:
                attempt_record['request_id'] = req_id
            attempt_record['provider_status'] = raw_dict.get('status')
            attempt_record['returned_model'] = raw_dict.get('model')
            usage = raw_dict.get('usage')
            if isinstance(usage, dict):
                # Retain usage as reported; do not claim estimated dollar costs or invoice amounts from fixtures
                attempt_record['usage'] = usage
            else:
                attempt_record['usage'] = {'status': 'unknown'}

            command = validate_response_envelope(raw_dict)
            attempt_record['status'] = 'completed'
            attempt_record['command'] = command
            if record_file is not None:
                write_json(record_file, attempt_record)
            return {'command': command}

        except ModelRefusalError as exc:
            attempt_record['status'] = 'refusal'
            attempt_record['error'] = str(exc)
            if record_file is not None:
                write_json(record_file, attempt_record)
            raise
        except MalformedResponseError as exc:
            attempt_record['status'] = 'malformed_envelope'
            attempt_record['error'] = str(exc)
            if record_file is not None:
                write_json(record_file, attempt_record)
            raise
        except Exception as exc:
            attempt_record['status'] = 'malformed_envelope'
            attempt_record['error'] = f'{type(exc).__name__}: {exc}'
            if record_file is not None:
                write_json(record_file, attempt_record)
            raise MalformedResponseError(f'Failed to process response envelope: {exc}') from exc


def export_request(
    source_path,
    output_path,
    model,
    manifest_path=None,
    detail=DEFAULT_DETAIL,
    max_output_tokens=DEFAULT_MAX_OUTPUT,
    reasoning_effort=DEFAULT_REASONING_EFFORT
):
    """Dry request-export utility: reads observation/payload and writes request.

    Cannot send requests. Requires explicit model configuration. Refuses to overwrite.
    Optionally emits compact manifest describing hashes, field layout, source, and image size.
    """
    if not isinstance(model, str) or not model.strip():
        raise ValueError('Explicit non-empty model configuration is required')
    source_path = Path(source_path).resolve()
    output_path = Path(output_path).resolve()

    if output_path.exists():
        raise FileExistsError(f'Output path already exists: {output_path}')
    if output_path == source_path:
        raise ValueError(f'Output path cannot overwrite source path: {output_path}')

    if manifest_path is not None:
        manifest_path = Path(manifest_path).resolve()
        if manifest_path == output_path:
            raise ValueError(f'Output path and manifest path must be distinct, got {output_path}')
        if manifest_path == source_path:
            raise ValueError(f'Manifest path cannot overwrite source path: {manifest_path}')
        if manifest_path.exists():
            raise FileExistsError(f'Manifest path already exists: {manifest_path}')

    source_data = json.loads(source_path.read_text(encoding='utf-8'))
    # Check if source is a public payload or a raw observation
    if 'observation' in source_data and isinstance(source_data['observation'], dict):
        payload = source_data
    elif 'camera' in source_data and 'robot_state' in source_data and 'rgb_png_base64' in source_data:
        payload = build_public_payload(source_data, history=[])
    else:
        raise ValueError(f'Unrecognized observation/payload format in {source_path}')

    request_body = build_responses_request(
        payload,
        model=model,
        detail=detail,
        max_output_tokens=max_output_tokens,
        reasoning_effort=reasoning_effort
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(output_path, request_body)

    # Extract manifest data
    obs = payload['observation']
    raw_bytes, img_sha256, (w, h) = validate_png_base64(obs['rgb_png_base64'], obs.get('rgb_sha256'))
    req_bytes = json.dumps(request_body, sort_keys=True, allow_nan=False).encode('utf-8')
    req_sha256 = hashlib.sha256(req_bytes).hexdigest()

    manifest = {
        'manifest_version': 1,
        'task': 'AGY-005',
        'offline_evidence': True,
        'fixture_source': str(source_path.relative_to(ROOT)) if ROOT in source_path.parents or source_path == ROOT else str(source_path),
        'model': model.strip(),
        'detail': detail,
        'max_output_tokens': max_output_tokens,
        'store': False,
        'image_size': [w, h],
        'image_bytes_len': len(raw_bytes),
        'image_sha256': img_sha256,
        'request_sha256': req_sha256,
        'field_layout': {
            'top_level_keys': sorted(list(request_body.keys())),
            'instructions_present': True,
            'input_items': [
                {
                    'role': request_body['input'][0]['role'],
                    'content_types': [c['type'] for c in request_body['input'][0]['content']],
                    'text_keys': sorted(list(json.loads(request_body['input'][0]['content'][0]['text']).keys())),
                    'image_data_url_prefix': request_body['input'][0]['content'][1]['image_url'][:30] + '...'
                }
            ],
            'text_format': {
                'type': request_body['text']['format']['type'],
                'name': request_body['text']['format']['name'],
                'strict': request_body['text']['format']['strict']
            }
        },
        'notes': 'Compact dry-run manifest. Base64 image payload omitted from Git manifest to prevent redundant duplicate storage.'
    }

    if manifest_path is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(manifest_path, manifest)

    return manifest


def provenance(model='gpt-5.6-sol', detail=DEFAULT_DETAIL):
    """Provenance metadata for visual provider adapter."""
    from .visual_policy_runner import provenance as runner_provenance
    result = runner_provenance(controller_name='visual_provider_adapter')
    adapter_py = ROOT / 'humanoid_sim/visual_provider_adapter.py'
    if adapter_py.exists():
        result['source_sha256'][str(adapter_py.relative_to(ROOT))] = hashlib.sha256(adapter_py.read_bytes()).hexdigest()
    result.update(
        task='AGY-005',
        adapter_model=model,
        image_detail=detail,
        injected_transport=True,
        offline_only=True
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='Path to saved observation or public payload JSON')
    parser.add_argument('--output', type=Path, required=True, help='Path to write exported request JSON (must not exist)')
    parser.add_argument('--model', type=str, required=True, help='Explicit model identifier (e.g. gpt-5.6-sol)')
    parser.add_argument('--manifest', type=Path, default=None, help='Optional path to write compact request manifest')
    parser.add_argument('--detail', choices=ALLOWED_DETAILS, default=DEFAULT_DETAIL, help='Image detail level (default: high)')
    args = parser.parse_args()

    if args.output.exists():
        parser.error(f'Output path already exists: {args.output}')
    if args.manifest and args.manifest.exists():
        parser.error(f'Manifest path already exists: {args.manifest}')

    manifest = export_request(
        source_path=args.input,
        output_path=args.output,
        model=args.model,
        manifest_path=args.manifest,
        detail=args.detail
    )
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()

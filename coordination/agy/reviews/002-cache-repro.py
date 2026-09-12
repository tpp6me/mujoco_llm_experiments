import json, shutil, tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from humanoid_sim.temporal_reacquisition_evaluation import is_augmented_cache_valid, render_augmented_dataset
original=Path('/Users/praveen/work/github/mujoco-llms/runtime/humanoid/temporal-P4/capture')
augmented=Path('/private/tmp/mujoco-llms-agy-002/runtime/humanoid/temporal-P4-augmented/capture')
with tempfile.TemporaryDirectory() as tmp:
    source=Path(tmp)/'source';output=Path(tmp)/'output'
    shutil.copytree(original/'seed-820',source/'seed-820')
    shutil.copytree(augmented/'seed-820',output/'seed-820')
    shutil.copy2(augmented/'augmented_manifest.json',output/'augmented_manifest.json')
    print('Initial cache valid:',is_augmented_cache_valid(source,output,[820]))
    midpoint=output/'seed-820/06b-observation.json'
    midpoint_before=midpoint.read_bytes()
    source_records=source/'seed-820/private_records.json'
    records=json.loads(source_records.read_text())
    transport=next(r for r in records if r['stage']=='transport')
    transport['time_s']+=0.2
    source_records.write_text(json.dumps(records))
    print('After source timestamp change valid:',is_augmented_cache_valid(source,output,[820]))
    with patch('humanoid_sim.visual.RGBRenderer',return_value=MagicMock()) as renderer:
        render_augmented_dataset(source,output,[820])
        print('Renderer capture calls:',renderer.return_value.capture.call_count)
    manifest=json.loads((output/'augmented_manifest.json').read_text())
    print('After regeneration cache valid:',is_augmented_cache_valid(source,output,[820]))
    print('Old midpoint bytes retained:',midpoint.read_bytes()==midpoint_before)
    lower=next(r for r in records if r['stage']=='lower')
    print('Expected source requested midpoint:',(transport['time_s']+lower['time_s'])/2)
    print('Manifest requested midpoint:',manifest['seeds']['820']['requested_time_s'])
    manifest['generation_revision']='wrong-generation'
    manifest['schedule_rule']='wrong-schedule'
    (output/'augmented_manifest.json').write_text(json.dumps(manifest))
    print('Wrong revision/schedule accepted:',is_augmented_cache_valid(source,output,[820]))

"""Post-hoc Phase 6 replay overlay; never an agent observation."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def annotation(env):
    font=ImageFont.load_default(size=18)
    small=ImageFont.load_default(size=15)
    tiny=ImageFont.load_default(size=12)
    observations=env.live_report['observations']
    snapshots={o['observation_id']:Image.open(o['image_path']).convert('RGB').resize((240,180)) for o in observations}
    times=np.asarray(env.frame_times)

    def draw(pixels,timestamp):
        image=Image.fromarray(pixels)
        canvas=ImageDraw.Draw(image)
        index=max(0,int(np.searchsorted(times,timestamp,side='right'))-1)
        score=env.score_frames[index]['outcomes']
        switched=bool(env.config.switch_at_s and timestamp>=env.config.switch_at_s)
        instruction=env.config.next_instruction if switched else env.config.instruction
        actor='Codex' if env.config.actor=='codex_session' else 'Conventional vision'
        canvas.rectangle((0,0,960,102),fill=(18,24,31))
        canvas.text((18,12),f'PHASE 6 | {actor} | Camera input | Continuous wall clock',font=font,fill='white')
        canvas.text((18,40),f'Time {timestamp:05.1f}s | Belt {env.config.belt_speed*100:g} cm/s | '
                    f'Rejected {score.get("correct_reject",0)}/{len(env.target_ids)} | '
                    f'Passed {score.get("correct_pass",0)} | Rule version {int(switched)}',font=small,fill=(170,220,230))
        events=[e for e in env.live_report['events'] if e['received_at_sim_s']<=timestamp]
        if not events:
            state='Waiting for command; belt continues'
        else:
            event=events[-1]
            status=event['status']
            if status=='cancelled_rule_change' and not switched:
                state='Old-rule motion queued'
            elif status=='cancelled_rule_change':
                state='Instruction changed: pending old-rule motion cancelled'
            elif event['error']:
                state=f'{status.upper()}: {event["error"]}'
            elif event['actual_start_s'] is not None and timestamp>=event['actual_start_s']:
                state='Motion complete; belt continues' if timestamp>=event['actual_end_s'] else 'Executing scheduled motion'
            else:
                state=f'Command queued for {event["command"]["start_at_s"]:.2f}s'
            if 'observation_to_submission_wall_s' in event:
                state+=f' | Response gap {event["observation_to_submission_wall_s"]:.2f}s'
        canvas.text((18,76),state,font=small,fill=(235,210,145))
        captured=[o for o in observations if o['time_s']<=timestamp]
        if captured:
            o=captured[-1]
            image.paste(snapshots[o['observation_id']],(700,130))
            canvas.rectangle((700,108,940,130),fill=(18,24,31))
            canvas.text((704,112),f'Input snapshot at {o["time_s"]:.1f}s (not live)',font=tiny,fill='white')
        canvas.rectangle((0,682,960,720),fill=(18,24,31))
        canvas.text((18,693),instruction,font=small,fill='white')
        return np.asarray(image)
    return draw

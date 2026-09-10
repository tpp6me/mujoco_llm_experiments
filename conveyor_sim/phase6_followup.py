"""Launch the separately declared, low-concurrency instruction-change check."""
import argparse
import json
from pathlib import Path

from .environment import ROOT
from .phase6 import launch

FOLDER=ROOT/'experiments/conveyor-color-sorting/phase6/confirmatory'
OUTPUT=ROOT/'runtime/conveyor/phase6_confirmatory'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['launch'])
    parser.add_argument('--actor',required=True,choices=['codex_session','conventional'])
    parser.add_argument('--case',required=True,choices=['confirm_switch_01','confirm_switch_02'])
    args=parser.parse_args(argv)
    # Enforce the declared concurrency bound using public status only.
    for root in [ROOT/'runtime/conveyor/phase6',OUTPUT]:
        for path in root.glob('*/*/status.json'):
            status=json.loads(path.read_text())
            if not status.get('completed') and path.parent.name!=args.case:
                raise ValueError(f'Wait for the active episode before launching another pair: {path.parent}')
    cases=json.loads((FOLDER/'cases.json').read_text())
    print(json.dumps(launch(next(c for c in cases if c['id']==args.case),args.actor,OUTPUT)),flush=True)


if __name__=='__main__': main()

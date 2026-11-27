#!/usr/bin/env python3
"""Generate and preflight one develop CLI input set, without RF forwards."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.minimax_profile import load_minimax_profile
from lpf.search.component_constraints import physical_bounds, validate_search_box
from lpf.search.development_plan import freeze_run
from lpf.search.plan import Loader, ROOT, fields
from lpf.search.proposals import definition_from_data
from lpf.search.starts import generate_for_definition
from lpf.search.storage import sha, vector_sha


def prepare(config, settings, spots, checkpoint_interval=1000):
    fields(settings, 'search_limits')
    limits = settings['search_limits']
    if not isinstance(limits, dict) or set(limits) - {'GJM01'}:
        raise ValueError('Only search_limits.GJM01 is supported')
    maximum = None
    if 'GJM01' in limits:
        fields(limits['GJM01'], 'max')
        maximum = limits['GJM01']['max']
        if type(maximum) not in (int, float) or not math.isfinite(maximum) or maximum <= 0:
            raise ValueError('GJM01 max must be a finite positive number in pF')

    rf = config['rf']
    if set(rf) != {'constraint_id', 'allow_trial'} or rf['allow_trial'] is not True:
        raise ValueError('Development requires explicit trial opt-in')
    ref = config['definition']
    if isinstance(ref, dict) and 'inductor_tree' in ref:
        data = ref
    else:
        fields(ref, 'path source_sha256 definition_sha256')
        path = (ROOT / ref['path']).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('Definition must be repository-local')
        blob = path.read_bytes()
        data = json.loads(blob)
        if hashlib.sha256(blob).hexdigest() != ref['source_sha256'] or sha(data) != ref['definition_sha256']:
            raise ValueError('Definition source SHA mismatch')
    definition = definition_from_data(data)
    profile = load_minimax_profile(rf['constraint_id'], root=ROOT, allow_trial=True)
    policy = json.loads(profile.base_json)
    physical = physical_bounds(definition, profile.build_model(definition).schema, policy)
    box = [list(pair) for pair in physical]
    if maximum is not None:
        for index, kind in enumerate(definition.fixed_c_types, len(definition.inductor_types)):
            if kind == 'GJM01':
                box[index][1] = min(box[index][1], maximum)
    box = validate_search_box(box, physical).tolist()

    seeds, arms = config['seeds'], config['arms']
    if (not isinstance(seeds, list) or not seeds or
            any(type(s) is not int or s < 0 for s in seeds) or len(set(seeds)) != len(seeds)):
        raise ValueError('Unique nonnegative seeds required')
    if not isinstance(arms, list) or not arms:
        raise ValueError('At least one arm required')
    names = [arm['name'] for arm in arms]
    if any(not isinstance(n, str) or not n.isidentifier() for n in names) or len(set(names)) != len(names):
        raise ValueError('Unique identifier arm names required')
    # Preserve the ordinary single-arm seed; allocate distinct extra Sobol seeds
    # in seed/arm order, skipping every configured seed.
    used = set(seeds)
    next_seed = 0
    starts, allocation = {}, {}
    for seed in seeds:
        starts[str(seed)], allocation[str(seed)] = {}, {}
        for i, name in enumerate(names):
            if i == 0:
                sobol_seed = seed
            else:
                while next_seed in used:
                    next_seed += 1
                sobol_seed = next_seed
                used.add(sobol_seed)
                next_seed += 1
            record = generate_for_definition(definition, policy, sobol_seed, bounds=box)
            starts[str(seed)][name] = {'vector': record['vector'], 'vector_sha256': vector_sha(record['vector'])}
            allocation[str(seed)][name] = sobol_seed
    plan, *_ = freeze_run(config, starts, root=ROOT, spot_checks=spots,
                           search_bounds=box, checkpoint_interval=checkpoint_interval)
    return box, starts, allocation, plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--settings', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='New directory for the input set')
    parser.add_argument('--spot-checks', required=True, help='Same JSON as develop CLI')
    parser.add_argument('--checkpoint-interval-forwards', type=int, default=1000)
    args = parser.parse_args(argv)
    try:
        config = yaml.load(args.config.read_text(), Loader=Loader)
        settings = yaml.load(args.settings.read_text(), Loader=Loader)
        spots = json.loads(args.spot_checks)
        box, starts, allocation, plan = prepare(config, settings, spots, args.checkpoint_interval_forwards)
        files = {
            'config.yaml': yaml.safe_dump(config, sort_keys=False),
            'settings.yaml': yaml.safe_dump(settings, sort_keys=False),
            'starts.json': json.dumps(starts, indent=2, allow_nan=False) + '\n',
            'bounds.json': json.dumps(box, indent=2, allow_nan=False) + '\n',
        }
        manifest = dict(files_sha256={name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()},
                        sobol_seeds=allocation, spot_checks=spots,
                        checkpoint_interval_forwards=args.checkpoint_interval_forwards,
                        plan_sha256=plan.sha256, search_bounds_sha256=plan.data['search_bounds_sha256'])
        args.output.mkdir(parents=True, exist_ok=False)
        for name, text in files.items():
            (args.output / name).write_bytes(text.encode('utf-8'))
        (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        print(f'PASS: input preflight (no RF forwards): {args.output}')
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        print(f'STOP: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

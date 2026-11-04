"""Fixed order only; no RF-dependent decisions or resource scheduling."""
from dataclasses import dataclass


@dataclass(frozen=True)
class NextAction:
    seed: int
    arm_index: int
    reason: str = 'fixed_seed_then_arm_order'


def actions(plan):
    config = plan.data['config']
    for seed in config['seeds']:
        for index in range(len(config['arms'])):
            yield NextAction(seed, index)

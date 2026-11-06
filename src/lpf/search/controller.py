"""Fixed order only; no RF-dependent decisions or resource scheduling."""
from dataclasses import dataclass


@dataclass(frozen=True)
class NextAction:
    seed: int
    arm_index: int
    reason: str = 'fixed_seed_then_arm_order'


def topology_action(plan, proposal):
    """A topology proposal supplies structure only, never solver/seed/budget."""
    config = plan.data['config']
    if len(config['seeds']) != 1 or len(config['arms']) != 1:
        raise ValueError('Campaign v1 requires one fixed seed/arm rule')
    return NextAction(config['seeds'][0], 0, proposal['reason'])


def actions(plan):
    config = plan.data['config']
    for seed in config['seeds']:
        for index in range(len(config['arms'])):
            yield NextAction(seed, index)

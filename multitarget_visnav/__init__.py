import gym
import os
from .vizdoom_gym import VizDoom

prefix = os.path.dirname(__file__)
maze_paths = {
    'exp1': '/maps/V1/0',
    'exp2-seen': '/maps/V2/0',
    'exp2-unseen': '/maps/V2/1',
    'exp3': '/maps/V3/0',
    'exp4-seen': '/maps/V4/0',
    'exp4-unseen': '/maps/V4/1'
}
living_reward = -0.0025
goal_reward = 10.0
non_goal_penalty = 1.0
non_goal_break = True
timeout_penalty = 0.1


for key in maze_paths.keys():
    gym.register(
        id=f'multitarget-visnav-{key}-v1',
        entry_point='multitarget_visnav.vizdoom_gym:VizDoom',
        kwargs={
            'maze_path': prefix + maze_paths[key],
            'scaled_resolution': (42, 42),
            'living_reward': living_reward,
            'goal_reward': goal_reward,
            'non_goal_penalty': non_goal_penalty,
            'timeout_penalty': timeout_penalty,
            'non_goal_break': non_goal_break
        }
    )

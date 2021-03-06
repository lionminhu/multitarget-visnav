# Modified from https://github.com/microsoft/MazeExplorer/blob/5c80af318e9497792034b05f2ee7374d70ad45ae/mazeexplorer/vizdoom_gym.py

import logging
import os
import random

import gym
import gym.spaces
import numpy as np
from pathlib import Path

from vizdoom import DoomGame, Button, GameVariable

try:
    import cv2

    OPENCV_AVAILABLE = True
    logging.info('OpenCV found, setting as default backend.')
except ImportError:
    pass

try:
    import PIL

    PILLOW_AVAILABLE = True

    if not OPENCV_AVAILABLE:
        logging.info('Pillow found, setting as default backend.')
except ImportError:
    pass


class VizDoom(gym.Env):
    """
    Wraps a VizDoom environment
    """

    def __init__(self, maze_path, scaled_resolution=(42, 42),
        living_reward=-0.0025, goal_reward=5.0, non_goal_penalty=1.0,
        timeout_penalty=1.0, non_goal_break=False):
        """
        Gym environment for training reinforcement learning agents.
        :param maze_path: directory containing the map files (directory
         containing .cfg file)
        :param scaled_resolution: resolution (height, width) of the observation
         to be returned with each step
        :param living_reward: reward received every time step. Set to negative
         if you desire to set time step penalty
        :param goal_reward: reward for reaching the goal
        :param non_goal_penalty: penalty (negative reward) for reaching non-goal
         target object
        :param timeout_penalty: penalty (negative reward) for reaching end of
         episode
        :param non_goal_break: whether to end the episode upon reaching non-goal
         target
        """

        cfg_paths = list(Path(maze_path).glob("*.cfg"))
        if len(cfg_paths) != 1:
            raise ValueError("Invalid number of cfgs within the mazes path: ",
                             len(cfg_paths))
        cfg_path = cfg_paths[0]
        self.cfg_path = str(cfg_path)

        if not os.path.exists(self.cfg_path):
            raise ValueError("Cfg file not found", cfg_path)

        if not self.cfg_path.endswith('.cfg'):
            raise ValueError("cfg_path must end with .cfg")

        self.scaled_resolution = scaled_resolution
        self.action_frame_repeat = 4
        self.last_obj_picked = -1
        self.living_reward = living_reward
        self.goal_reward = goal_reward
        self.non_goal_penalty = non_goal_penalty
        self.timeout_penalty = timeout_penalty
        self.non_goal_break = non_goal_break
        self.num_obj_to_spawn = 4

        super(VizDoom, self).__init__()
        self._logger = logging.getLogger(__name__)
        self._logger.info("Creating environment: VizDoom (%s)", self.cfg_path)

        # Create an instace on VizDoom game, initalise it from a scenario config
        # file
        self.env = DoomGame()
        self.env.load_config(self.cfg_path)
        self.env.init()

        # Perform config validation:
        # Only RGB format with a seperate channel per colour is supported
        # assert self.env.get_screen_format() == ScreenFormat.RGB24
        # Only discrete actions are supported (no delta actions)
        available_actions = self.env.get_available_buttons()
        not_supported_actions = [Button.LOOK_UP_DOWN_DELTA,
                                 Button.TURN_LEFT_RIGHT_DELTA,
                                 Button.MOVE_LEFT_RIGHT_DELTA,
                                 Button.MOVE_UP_DOWN_DELTA,
                                 Button.MOVE_FORWARD_BACKWARD_DELTA]
        assert len((set(available_actions) - set(not_supported_actions))) == \
            len(available_actions)

        # Allow only one button to be pressed at a given step
        self.action_space = gym.spaces.Discrete(
            self.env.get_available_buttons_size()
        )

        rows = scaled_resolution[1]
        columns = scaled_resolution[0]
        self.observation_space = gym.spaces.Box(0.0,
                                                255.0,
                                                shape=(columns, rows, 3),
                                                dtype=np.float32)
        self._rgb_array = None
        self.reset()


    def _process_image(self, shape=None):
        """
        Convert the vizdoom environment observation numpy are into the desired
        resolution and shape
        :param shape: desired shape in the format (rows, columns)
        :return: resized and rescaled image in the format (rows, columns,
         channels)
        """
        if shape is None:
            rows, columns, _ = self.observation_space.shape
        else:
            rows, columns = shape
        # PIL resize has indexing opposite to numpy array
        img = VizDoom._resize(self._rgb_array.transpose(1, 2, 0),
                              (columns, rows))
        img = np.transpose(img, (2, 0, 1))
        return img


    @staticmethod
    def _augment_data(img):
        """
        Augment input image with N randomly colored boxes of dimension x by y
        where N is randomly sampled between 0 and 6
        and x and y are randomly sampled from between 0.1 and 0.35
        :param img: input image to be augmented - format (rows, columns,
         channels)
        :return img: augmented image - format (rows, columns, channels)
        """
        dimx = img.shape[0]
        dimy = img.shape[1]
        max_rand_dim = .25
        min_rand_dim = .1
        num_blotches = np.random.randint(0, 6)

        for _ in range(num_blotches):
            # locations in [0,1]
            rand = np.random.rand
            rx = rand()
            ry = rand()
            rdx = rand() * max_rand_dim + min_rand_dim
            rdy = rand() * max_rand_dim + min_rand_dim

            rx, rdx = [round(r * dimx) for r in (rx, rdx)]
            ry, rdy = [round(r * dimy) for r in (ry, rdy)]
            for c in range(3):
                img[rx:rx + rdx, ry:ry + rdy, c] = np.random.randint(0, 255)
        return img


    @staticmethod
    def _resize(img, shape):
        """Resize the specified image.
        :param img: image to resize
        :param shape: desired shape in the format (rows, columns)
        :return: resized image
        """
        if not (OPENCV_AVAILABLE or PILLOW_AVAILABLE):
            raise ValueError('No image library backend found.'' Install either '
                             'OpenCV or Pillow to support image processing.')

        if OPENCV_AVAILABLE:
            return cv2.resize(img, shape, interpolation=cv2.INTER_AREA)

        if PILLOW_AVAILABLE:
            return np.array(PIL.Image.fromarray(img).resize(shape))

        raise NotImplementedError


    def check_player_spawn_ok(self):
        """
        Check if this map can spawn player (at the specified position, if
        provided)
        """
        self.env.new_episode()
        return int(self.env.get_game_variable(GameVariable.USER8))


    def spawn_obj_check(self, iter=-1):
        """
        Run new episodes until either all objects are spawned properly or
        `iter` iterations are reached.
        :param iter: (int) number of maximum iterations, or -1 if running
         infinite iterations
        :return: (bool) whether the map can spawn correct number of objects
        """
        i = 0
        while iter == -1 or i < iter:
            self.env.new_episode()
            num_obj_spawn = int(self.env.get_game_variable(GameVariable.USER7))
            if num_obj_spawn == self.num_obj_to_spawn:
                return True
            i += 1
        return False


    def reset(self):
        """
        Resets environment to start a new mission.
        If there is more than one maze it will randomly select a new maze.
        :return: initial observation of the environment as an rgb array in the
         format (rows, columns, channels)
        """
        self.env.set_doom_map('map00')

        self.spawn_obj_check(iter=-1)

        self._rgb_array = self.env.get_state().screen_buffer
        depth = self.env.get_state().depth_buffer
        depth = np.expand_dims(depth, 0)
        self._rgb_array = np.concatenate((self._rgb_array, depth), axis=0)
        self.last_obj_picked = -1
        observation = self._process_image()
        observation = np.array([list(observation)] * self.action_frame_repeat)

        # select a target object for instruction
        self.goal = random.randrange(self.num_obj_to_spawn)

        return observation


    def get_goal_idx(self):
        """
        Returns the index of the goal
        """
        return self.goal


    def set_goal(self, goal):
        """
        Manually select the goal object for the current episode.
        :param target: index (int), or the name of goal object type (str).
         The possible arguments are
           {0, 1, 2, 3, "Card", "Armor", "Skull", "Bonus"}.
         The indices 0, 1, 2, 3 respectively refer to "Card", "Armor",
         "Skull", and "Bonus".
        """
        targets = ['Card', 'Armor', 'Skull', 'Bonus']
        assert isinstance(goal, str) or isinstance(goal, int), \
            "`goal` must be type `str` or `int`."
        assert (goal in range(len(targets))) or (goal in targets), \
            f"Invalid goal provided: {goal}"
        if isinstance(goal, str):
            self.goal = targets.index(goal)
        else:
            self.goal = goal


    def step(self, action):
        """
        Perform the specified action for the self.action_frame_repeat ticks
        within the environment.
        :param action: the index of the action to perform. The actions are
         specified when the cfg is created. The defaults are "MOVE_FORWARD
         TURN_LEFT TURN_RIGHT"
        :return: tuple following the gym interface, containing:
            - observation as a numpy array of shape (rows, height, channels)
            - scalar reward
            - boolean which is true when the environment is done
            - {'goal': index of goal object,
               'last_obj_picked': index of last object picked or -1 if not yet
                                  picked anything,
                'just_picked": index of object just picked up in the previous
                               frame,
                'x_pos': current x position,
                'y_pos': current y position}
        """
        one_hot_action = np.zeros(self.action_space.n, dtype=int)
        one_hot_action[action] = 1

        obs_batch = []
        total_reward = 0.0
        done = False
        info_batch = []

        for _ in range(self.action_frame_repeat):
            _ = self.env.make_action(list(one_hot_action), 1)

            done = self.env.is_episode_finished()

            if not done:
                self._rgb_array = self.env.get_state().screen_buffer
                depth = self.env.get_state().depth_buffer
                depth = np.expand_dims(depth, 0)
                self._rgb_array = np.concatenate((self._rgb_array, depth),
                                                 axis=0)
            observation = self._process_image()
            obs_batch.append(observation)

            last_obj_picked = int(
                self.env.get_game_variable(GameVariable.USER6)
            )
            just_picked = None

            reward = self.living_reward

            # penalty when timeout without picking up anything
            if done:
                reward += (-1.0) * self.timeout_penalty

            if self.last_obj_picked != last_obj_picked:
                # break when reaching goal or non-goal
                if self.non_goal_break:
                    done = True
                self.last_obj_picked = last_obj_picked
                just_picked = last_obj_picked
                if just_picked == self.goal:
                    reward = self.goal_reward
                else:
                    reward = (-1.0) * self.non_goal_penalty

            total_reward += reward

            x_pos = self.env.get_game_variable(GameVariable.POSITION_X)
            y_pos = self.env.get_game_variable(GameVariable.POSITION_Y)

            info = {'goal': self.goal, 'last_obj_picked': last_obj_picked,
                    'just_picked': just_picked, 'x_pos': x_pos, 'y_pos': y_pos}
            info_batch.append(info)

            if done:
                break

        while len(obs_batch) < self.action_frame_repeat:
            last_obs = obs_batch[len(obs_batch) - 1]
            obs_batch.append(last_obs)
            last_info = info_batch[len(info_batch) - 1]
            info_batch.append(last_info)

        obs_batch = np.array(obs_batch)

        return obs_batch, total_reward, done, info_batch

    def close(self):
        """Close environment"""
        self.env.close()


    def render(self, mode='rgb_array'):
        """Render frame"""
        if mode == 'rgb_array':
            return self._rgb_array

        raise NotImplementedError

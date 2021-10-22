# from mazeenv.vizdoom_gym import VizDoom
import gym
import multitarget_visnav
import numpy as np
from itertools import count
import cv2
import os


output_folder = './interactive_img'


targets = ['Card', 'Armor', 'Skull', 'Bonus']

if __name__ == '__main__':
    env = gym.make('multitarget-visnav-exp1-v1', scaled_resolution=(240, 320))

    os.makedirs(output_folder, exist_ok=True)

    obs = env.reset()
    goal = targets[env.get_goal_idx()]
    print('start, goal {}'.format(goal))
    total_reward = 0.0
    convert_img = True
    save_img_idx = 0
    for t in count():
        if convert_img:
            obs = obs[-1,:-1]
            obs = np.transpose(obs, (1, 2, 0))
            obs = cv2.cvtColor(obs, cv2.COLOR_BGR2RGB)
            cv2.imshow('window', obs)

        convert_img = True
        key = cv2.waitKey(0)
        if key == ord('q'):    # Press 'q' to quit
            break
        elif key == ord('1'):  # Press '1' to move forward
            obs, reward, dones, info = env.step(0)
        elif key == ord('2'):  # Press '2' to rotate left
            obs, reward, dones, info = env.step(1)
        elif key == ord('3'):  # Press '3' to rotate right
            obs, reward, dones, info = env.step(2)
        elif key == ord('r'):  # Press 'r' to start new episode
            obs = env.reset()
            goal = targets[env.get_goal_idx()]
            print('manual reset, goal {}'.format(goal))
            continue
        elif key == ord('s'):  # Press 's' to take a screenshot
            path = '{}/{}.png'.format(output_folder, save_img_idx)
            cv2.imwrite(path, obs)
            print('image saved to path {}'.format(path))
            save_img_idx += 1
            convert_img = False
            continue
        else:
            convert_img = False
            continue
        total_reward += reward
        print('total reward: {}, dones: {}, info: {}'.format(total_reward, dones, info))
        if dones:
            obs = env.reset()
            goal = targets[env.get_goal_idx()]
            print('new episode, goal {}'.format(goal))

    env.close()

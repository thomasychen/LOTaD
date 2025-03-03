import yaml
from stable_baselines3.common.noise import OrnsteinUhlenbeckActionNoise
from stable_baselines3 import DQN, PPO, SAC, DDPG, HER, HerReplayBuffer
# from stable_baselines3.ddpg import MlpPolicy
from stable_baselines3.ppo import MlpPolicy
# from stable_baselines3.sac import MlpPolicy
import supersuit as ss
import numpy as np
from wandb.integration.sb3 import WandbCallback
import wandb
from stable_baselines3.common.logger import configure, read_csv
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.vec_env.vec_monitor import VecMonitor
from manager.manager import Manager
from stable_baselines3.common.callbacks import EvalCallback, CallbackList
from mdp_label_wrappers.cooperative_buttons_mdp_labeled import CooperativeButtonsLabeled
from mdp_label_wrappers.four_buttons_mdp_labeled import FourButtonsLabeled
from mdp_label_wrappers.repairs_task_mdp_labeled import RepairsTaskLabeled
from reward_machines.sparse_reward_machine import SparseRewardMachine
from reward_machines.rm_generator import generate_rm_decompositions
from stable_baselines3.common.monitor import Monitor
from pettingzoo.test import parallel_seed_test
from stable_baselines3.common.utils import set_random_seed
import argparse
from datetime import datetime
import matplotlib.pyplot as plt
import os
from collections import defaultdict
import pandas as pd
from utils.plot_utils import generate_plots
import re
import torch as th
from pettingzoo_product_env.overcooked_product_env import OvercookedProductEnv
from pettingzoo_product_env.buttons_product_env import ButtonsProductEnv
from jaxmarl.environments.overcooked import overcooked_layouts
from mdp_label_wrappers.overcooked_asymmetric_advantages_labeled import OvercookedAsymmetricAdvantagesLabeled
from mdp_label_wrappers.overcooked_cramped_corridor_labeled import OvercookedCrampedCorridorLabeled

## WANDB KILL SWITCH
# ps aux|grep wandb|grep -v grep | awk '{print $2}'|xargs kill -9

def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

# Function to extract states connected to 0
def extract_states_from_text(text):
    pattern = re.compile(r'\(0, (\d+),')
    matches = pattern.findall(text)
    return list(map(int, matches))

# Function to read file and extract states
def extract_states_from_file(file_path):
    try:
        with open(file_path, 'r') as file:
            content = file.read()
        return extract_states_from_text(content)
    except Exception as e:
        print(f"Error reading file: {e}")
        return []

parser = argparse.ArgumentParser(description="Run reinforcement learning experiments with PettingZoo and Stable Baselines3.")
parser.add_argument('--assignment_methods', type=str, default="ground_truth naive random add multiply UCB", help='The assignment method for the manager. Default is "ground_truth".')
parser.add_argument('--num_iterations', type=int, default=5, help='Number of iterations for the experiment. Default is 5.')
parser.add_argument('--wandb', type=str2bool, default=False, help='Turn Wandb logging on or off. Default is off')
parser.add_argument('--timesteps', type=int, default=2000000, help='Number of timesteps to train model. Default is 2000000')
parser.add_argument('--decomposition_file', type=str, default="aux_buttons.txt",  help="The reward machine file for this decomposition")
parser.add_argument('--experiment_name', type=str, default="buttons", help="Name of config file for environment eg: ")
parser.add_argument('--is_monolithic', type=str2bool, default=False, help="If monolothic RM")
parser.add_argument('--num_candidates', type=int, default=0, help="Use automated decomposition for a monolithic reward machine. If 0, run the monolithic RM as is.")
parser.add_argument('--env', type=str, default="buttons", help="Specify between the buttons grid world or overcooked")
parser.add_argument('--add_mono_file', type=str, default="None", help="Provide a monolithic file for global statekeeping along with a decomposed strategy")
parser.add_argument('--render', type=str2bool, default=False, help='Enable rendering during training. Default is off')
parser.add_argument('--video', type=str2bool, default=False, help='Turn on gifs for eval')
parser.add_argument('--seed', type=int, default=-1, help='Seed the runs')
parser.add_argument('--ucb_c', type=float, default=-1, help='c value for ucb')
parser.add_argument('--ucb_gamma', type=float, default=-1, help='discount value for ucb_gamma')
parser.add_argument('--handpicked_decomp',type=str, default="None", help = "Provide an optional handpicked decomposition to be inserted into the generated candidates" )

# Add the sweep flag
parser.add_argument('--sweep', type=str2bool, default=False, help='Set to True when running a W&B sweep.')

args = parser.parse_args()

if __name__ == "__main__":

    assignment_methods = args.assignment_methods.split()
    real_base = "./logs/"
    os.makedirs(real_base, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    log_dir_base = os.path.join(real_base, f"{timestamp}")
    os.makedirs(log_dir_base, exist_ok=True)
    for method in assignment_methods:

        with open(f'config/{args.env}/{args.experiment_name}.yaml', 'r') as file:
            run_config = yaml.safe_load(file)

        candidates = args.num_candidates
        mono_string = "mono_off"
        if args.add_mono_file != "None":
            mono_string = "mono_on"
        
        experiment_name = args.experiment_name # buttons or overcooked
        ucb_param = run_config['ucb_c'] if "ucb_c" in run_config else 1.5
        ucb_param = float(args.ucb_c) if float(args.ucb_c) != -1 else ucb_param


        ucb_gamma = run_config['ucb_gamma'] if "ucb_gamma" in run_config else 0.99
        ucb_gamma = float(args.ucb_gamma) if float(args.ucb_gamma) != -1 else ucb_gamma

        print("UCB_C PARAM", ucb_param)
        print("UCB_GAMA PARAM", ucb_gamma)

        
        local_dir_name = f"{experiment_name}_{method}_ucb_param{ucb_param}_gamma{ucb_gamma}_{candidates}_candidates_{mono_string}"

        method_log_dir_base = os.path.join(log_dir_base, f"{local_dir_name}")
        os.makedirs(method_log_dir_base, exist_ok=True)

        for i in range(1, args.num_iterations + 1):
            curr_seed = int(args.seed) if int(args.seed) != -1 else i
            set_random_seed(curr_seed)    

            # Initialize W&B if wandb logging is enabled
            if args.wandb:
                experiment = "test_pettingzoo_sb3"
                config = {
                    "policy_type": "MlpPolicy",
                    "total_timesteps": args.timesteps,
                    "env_name": f"{args.env}",
                }

                wandb_timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

                run_name = f"{experiment_name}_{method}__ucb_param{ucb_param}_gamma{ucb_gamma}_iteration_{i}_{candidates}_candidates_{mono_string}_seed_{curr_seed}_{wandb_timestamp}"
                if args.sweep:
                    # Only override args with wandb.config when sweep flag is True
                    run=wandb.init(
                        project=experiment,
                        entity="reinforce-learn",
                        config=config,
                        sync_tensorboard=True,
                        name=run_name)
                    # Update args with values from wandb.config if they exist
                    args.add_mono_file = wandb.config.get('add_mono_file', args.add_mono_file)
                    args.handpicked_decomp = wandb.config.get('handpicked_decomp', args.handpicked_decomp)
                    args.num_candidates = wandb.config.get('num_candidates', args.num_candidates)
                    # Update any other parameters you want to control via sweep
                    # args.ucb_c = wandb.config.get('ucb_c', args.ucb_c)
                    # args.ucb_gamma = wandb.config.get('ucb_gamma', args.ucb_gamma)
                    # Optionally, log all args to W&B config
                    wandb.config.update(vars(args))
                else:
                    # Regular W&B initialization without overriding args

                    run = wandb.init(
                        project=experiment,
                        entity="reinforce-learn",
                        config=config,
                        sync_tensorboard=True,
                        name=run_name
                    )
                    wandb.config.update(vars(args))
            else:
                run = None  # Ensure 'run' variable is defined

            print(run_config)

            # print("TEST", args.decomposition_file.split("_")[0])
            if args.decomposition_file.split("_")[0] != "mono" and args.decomposition_file.split("_")[0] != "individual":
                raise Exception("ERROR: ONLY PROVIDE MONOLITHIC RMS FOR RUNS")
            train_rm = SparseRewardMachine(f"reward_machines/{args.env}/{args.experiment_name}/{args.decomposition_file}")
            train_rm.is_monolithic = True
            mono_rm = SparseRewardMachine(f"reward_machines/{args.env}/{args.experiment_name}/{args.add_mono_file}") if args.add_mono_file != "None" else None
            if mono_rm is not None:
                mono_rm.is_monolithic = True
            if args.num_candidates > 0:  # generate automatic decompositions
                handpicked_decomp = f"reward_machines/{args.env}/{args.experiment_name}/{args.handpicked_decomp}" if args.handpicked_decomp != "None" else None
                # TODO: look for forbidden events or required events in config
                forbidden = {}
                for idx, fb in enumerate(run_config["forbidden_events"]):
                    forbidden[idx] = fb
                required = {}
                for idx, req in enumerate(run_config["required_events"]):
                    required[idx] = req
                new_initial_rm_states = []
                train_rm, rm_initial_states = generate_rm_decompositions(
                    train_rm, run_config['num_agents'], top_k=args.num_candidates,
                    enforced_dict=required, forbidden_dict=forbidden, handpicked_decomp=handpicked_decomp, config=run_config)
                # import pdb; pdb.set_trace()
                for rm in rm_initial_states:
                    istates = []
                    for agentidx in range(run_config['num_agents']):
                        istates.append(rm_initial_states[rm][agentidx])
                    new_initial_rm_states.append(istates)
                run_config["initial_rm_states"] = new_initial_rm_states
                train_rm.find_max_subgraph_size_and_assign_subtasks()
                # import pdb; pdb.set_trace()
            manager = Manager(num_agents=run_config['num_agents'], num_decomps=len(run_config["initial_rm_states"]),
                              assignment_method=method, wandb=args.wandb, seed=curr_seed, ucb_c=ucb_param, ucb_gamma=ucb_gamma)
            render_mode = "human" if args.render else None
            run_config["render_mode"] = render_mode

            log_dir = os.path.join(method_log_dir_base, f"iteration_{i}_seed_{curr_seed}")
            os.makedirs(log_dir, exist_ok=True)

            train_kwargs = {
                'manager': manager,
                'labeled_mdp_class': eval(run_config['labeled_mdp_class']),
                'reward_machine': train_rm,
                'config': run_config,
                'max_agents': run_config['num_agents'],
                'is_monolithic': args.is_monolithic,
                'render_mode': render_mode,
                'addl_mono_rm': mono_rm,
            }

            if args.env == "buttons":
                env = ButtonsProductEnv(**train_kwargs)
            elif args.env == "overcooked":
                env = OvercookedProductEnv(**train_kwargs)

            env = ss.black_death_v3(env)
            env = ss.pettingzoo_env_to_vec_env_v1(env)
            env = ss.concat_vec_envs_v1(env, 1, num_cpus=1, base_class="stable_baselines3")
            env = VecMonitor(env)

            eval_kwargs = train_kwargs.copy()
            eval_kwargs['test'] = True
            eval_kwargs["render_mode"] = render_mode
            eval_kwargs['log_dir'] = log_dir
            eval_kwargs['video'] = args.video

            if args.env == "buttons":
                eval_env = ButtonsProductEnv(**eval_kwargs)
            elif args.env == "overcooked":
                eval_env = OvercookedProductEnv(**eval_kwargs)

            eval_env = ss.black_death_v3(eval_env)
            eval_env = ss.pettingzoo_env_to_vec_env_v1(eval_env)
            eval_env = ss.concat_vec_envs_v1(eval_env, 1, num_cpus=1, base_class="stable_baselines3")
            eval_env = VecMonitor(eval_env)

            eval_callback = EvalCallback(eval_env, best_model_save_path=f"{log_dir}/best/",
                                         log_path=log_dir, eval_freq=run_config["eval_freq"],
                                         n_eval_episodes=1, deterministic=False)
            policy_kwargs = None
            if "activation_fn" in run_config:
                if run_config["activation_fn"] == "relu":
                    fn = th.nn.ReLU
                elif run_config["activation_fn"] == "tanh":
                    fn = th.nn.Tanh
                policy_kwargs = dict(activation_fn=fn)

            model = PPO(
                MlpPolicy,
                env,
                verbose=1,
                batch_size=256,
                learning_rate=run_config['learning_rate'] if "learning_rate" in run_config else 0.0003,
                gamma=run_config['gamma'] if "gamma" in run_config else 0.99,
                n_epochs=run_config["n_epochs"] if "n_epochs" in run_config else 10,
                tensorboard_log=f"runs/{run.id}" if args.wandb else None,
                max_grad_norm=run_config['max_grad_norm'] if "max_grad_norm" in run_config else 0.5,
                vf_coef=run_config['vf_coef'] if "vf_coef" in run_config else 0.5,
                target_kl=run_config['target_kl'] if "target_kl" in run_config else None,
                ent_coef=run_config['ent_coef'] if "ent_coef" in run_config else 0,
                policy_kwargs=policy_kwargs,
            )

            if "env" == "overcooked":
                model.learning_rate = lambda frac: 2.5e-4 * frac

            manager.set_model(model)
            env.reset()
            eval_env.reset()

            if args.wandb:
                callback_list = CallbackList([eval_callback, WandbCallback(verbose=2,)])
                # callback_list = CallbackList([WandbCallback(verbose=2,)])
                print("Wandb Enabled")

            else:
                callback_list = CallbackList([eval_callback])
                print("Wandb Disabled")

            model.learn(total_timesteps=args.timesteps, callback=callback_list, log_interval=10, progress_bar=False)
            env.close()
            eval_env.close()
            # Finish your run
            if args.wandb and not args.sweep:
                wandb.finish()


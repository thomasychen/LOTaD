import random
import numpy as np
from enum import Enum
import copy
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.colors as mcolors
import matplotlib.animation as animation


"""
Enum with the actions that the agent can execute
"""
class Actions(Enum):
    up    = 0 # move up
    right = 1 # move right
    down  = 2 # move down
    left  = 3 # move left
    none  = 4 # none 

class CooperativeButtonsEnv:

    def __init__(self, env_config):
        """
        Initialize environment.

        Parameters
        ----------
        rm_file : string
            File path leading to the text file containing the reward machine
            encoding this environment's reward function.
        agent_id : int
            Index {0,1} indicating which agent
        env_settings : dict
            Dictionary of environment settings
        """

        env_settings = copy.deepcopy(env_config)
        env_settings['Nr'] = 10
        env_settings['Nc'] = 10
        env_settings['initial_states'] = [0, 5, 8]
        env_settings['walls'] = [(0, 3), (1, 3), (2, 3), (3,3), (4,3), (5,3), (6,3), (7,3),
                                    (7,4), (7,5), (7,6), (7,7), (7,8), (7,9),
                                    (0,7), (1,7), (2,7), (3,7), (4,7) ]
        env_settings['goal_location'] = (8,9)
        env_settings['yellow_button'] = (0,2)
        env_settings['green_button'] = (5,6)
        env_settings['red_button'] = (6,9)
        env_settings['yellow_tiles'] = [(2,4), (2,5), (2,6), (3,4), (3,5), (3,6)]
        env_settings['green_tiles'] = [(2,8), (2,9), (3,8), (3,9)]
        env_settings['red_tiles'] = [(8,5), (8,6), (8,7), (8,8), (9,5), (9,6), (9,7), (9,8)]
        env_settings['p'] = 0.98
        self.env_settings = env_settings
        self.p = env_settings["p"]


        self._load_map()
        self.fig, self.ax = None, None

    def reset(self, decomp_idx):
        CooperativeButtonsEnv.a2_red_pressed = False
        CooperativeButtonsEnv.a3_red_pressed = False
        CooperativeButtonsEnv.yellow_pressed = False
        CooperativeButtonsEnv.green_pressed = False
        CooperativeButtonsEnv.red_pressed = False

        rm_state_array = copy.deepcopy(self.env_settings["initial_rm_states"]) if np.array(self.env_settings["initial_rm_states"]).ndim == 2 else [copy.deepcopy(self.env_settings["initial_rm_states"])]

        CooperativeButtonsEnv.u = {i+1:rm_state_array[decomp_idx][i] for i in range(len(self.env_settings["initial_states"]))}

    def _load_map(self):
        """
        Initialize the environment.
        """
        self.Nr = self.env_settings['Nr']
        self.Nc = self.env_settings['Nc']

        self.objects = {}
        self.objects[self.env_settings['goal_location']] = "g" # goal location
        self.objects[self.env_settings['yellow_button']] = 'yb'
        self.objects[self.env_settings['green_button']] = 'gb'
        self.objects[self.env_settings['red_button']] = 'rb'
        self.yellow_tiles = self.env_settings['yellow_tiles']
        self.green_tiles = self.env_settings['green_tiles']
        self.red_tiles = self.env_settings['red_tiles']

        self.num_states = self.Nr * self.Nc

        self.actions = [Actions.up.value, Actions.right.value, Actions.left.value, Actions.down.value, Actions.none.value]
        
        # Define forbidden transitions corresponding to map edges
        self.forbidden_transitions = set()
        
        wall_locations = self.env_settings['walls']

        for row in range(self.Nr):
            self.forbidden_transitions.add((row, 0, Actions.left)) # If in left-most column, can't move left.
            self.forbidden_transitions.add((row, self.Nc - 1, Actions.right)) # If in right-most column, can't move right.
        for col in range(self.Nc):
            self.forbidden_transitions.add((0, col, Actions.up)) # If in top row, can't move up
            self.forbidden_transitions.add((self.Nr - 1, col, Actions.down)) # If in bottom row, can't move down

        # Restrict agent from having the option of moving "into" a wall
        for i in range(len(wall_locations)):
            (row, col) = wall_locations[i]
            self.forbidden_transitions.add((row, col + 1, Actions.left))
            self.forbidden_transitions.add((row, col-1, Actions.right))
            self.forbidden_transitions.add((row+1, col, Actions.up))
            self.forbidden_transitions.add((row-1, col, Actions.down))

    def environment_step(self, s, a, agent_id):
        """
        Execute action a from state s.

        Parameters
        ----------
        s : int
            Index representing the current environment state.
        a : int
            Index representing the action being taken.

        Outputs
        -------
        r : float
            Reward achieved by taking action a from state s.
        l : list
            List of events occuring at this step.
        s_next : int
            Index of next state.
        """
        s_next, _ = self.get_next_state(s,a, agent_id)

        return s_next

    def get_next_state(self, s, a, agent_id):
        """
        Get the next state in the environment given action a is taken from state s.
        Update the last action that was truly taken due to MDP slip.

        Parameters
        ----------
        s : int
            Index of the current state.
        a : int
            Action to be taken from state s.

        Outputs
        -------
        s_next : int
            Index of the next state.
        last_action :int
            Last action taken by agent due to slip proability.
        """
        slip_p = [self.p, (1-self.p)/2, (1-self.p)/2]
        check = random.random()

        row, col = self.get_state_description(s)

        # up    = 0
        # right = 1 
        # down  = 2 
        # left  = 3 

        if (check<=slip_p[0]) or (a == Actions.none.value):
            a_ = a

        elif (check>slip_p[0]) & (check<=(slip_p[0]+slip_p[1])):
            if a == 0: 
                a_ = 3
            elif a == 2: 
                a_ = 1
            elif a == 3: 
                a_ = 2
            elif a == 1: 
                a_ = 0

        else:
            if a == 0: 
                a_ = 1
            elif a == 2: 
                a_ = 3
            elif a == 3: 
                a_ = 0
            elif a == 1: 
                a_ = 2

        action_ = Actions(a_)
        if (row, col, action_) not in self.forbidden_transitions:
            if action_ == Actions.up:
                row -= 1
            if action_ == Actions.down:
                row += 1
            if action_ == Actions.left:
                col -= 1
            if action_ == Actions.right:
                col += 1

        s_next = self.get_state_from_description(row, col)

        # If the appropriate button hasn't yet been pressed, don't allow the agent into the colored region
        if agent_id == 1:
            if (row, col) in self.red_tiles and not (CooperativeButtonsEnv.a2_red_pressed and CooperativeButtonsEnv.a3_red_pressed):
                s_next = s
        if agent_id == 2:
            if (row, col) in self.yellow_tiles and not CooperativeButtonsEnv.yellow_pressed:
                s_next = s
        if agent_id == 3:
            if (row, col) in self.green_tiles and not CooperativeButtonsEnv.green_pressed:
                s_next = s

        last_action = a_
        return s_next, last_action

    def get_state_from_description(self, row, col):
        """
        Given a (row, column) index description of gridworld location, return
        index of corresponding state.

        Parameters
        ----------
        row : int
            Index corresponding to the row location of the state in the gridworld.
        col : int
            Index corresponding to the column location of the state in the gridworld.
        
        Outputs
        -------
        s : int
            The index of the gridworld state corresponding to location (row, col).
        """
        return self.Nc * row + col

    def get_state_description(self, s):
        """
        Return the row and column indeces of state s in the gridworld.

        Parameters
        ----------
        s : int
            Index of the gridworld state.

        Outputs
        -------
        row : int
            The row index of state s in the gridworld.
        col : int
            The column index of state s in the gridworld.
        """
        row = np.floor_divide(s, self.Nr)
        col = np.mod(s, self.Nc)

        return (row, col)

    def get_actions(self):
        """
        Returns the list with the actions that the agent can perform
        """
        return self.actions

    # def get_last_action(self):
    #     """
    #     Returns agent's last action
    #     """
    #     return self.last_action

    # def get_initial_state(self):
    #     """
    #     Outputs
    #     -------
    #     s_i : int
    #         Index of agent's initial state.
    #     """
    #     return self.s_i

    def show(self, state_dict, show_plot = True):
        """
        Create a visual representation of the current state of the gridworld.

        Parameters
        ----------
        state_dict : dict
            Dictionary of agent names and their corresponding states.
        """

        if self.fig is None or self.ax is None:
            self.fig, self.ax = plt.subplots(figsize=(5, 5))
        else:
            self.ax.clear()

        self.ax.set_xlim(0, self.Nc)
        self.ax.set_ylim(0, self.Nr)
        self.ax.set_aspect('equal')

        # Draw the grid
        for x in range(self.Nc + 1):
            self.ax.axvline(x, color='black', linewidth=0.5)
        for y in range(self.Nr + 1):
            self.ax.axhline(y, color='black', linewidth=0.5)

        # Draw the walls
        for loc in self.env_settings['walls']:
            rect = patches.Rectangle((loc[1], self.Nr - loc[0] - 1), 1, 1, linewidth=1, edgecolor='black', facecolor='black')
            self.ax.add_patch(rect)

        # Draw colored tiles
        tile_colors = {
            'yellow': mcolors.to_rgba('yellow', 0.6),
            'green': mcolors.to_rgba('green', 0.6),
            'red': mcolors.to_rgba('red', 0.6),
        }
        for tile, color in zip([self.yellow_tiles, self.green_tiles, self.red_tiles], ['yellow', 'green', 'red']):
            for loc in tile:
                rect = patches.Rectangle((loc[1], self.Nr - loc[0] - 1), 1, 1, linewidth=1, edgecolor='black', facecolor=tile_colors[color])
                self.ax.add_patch(rect)

        # Draw buttons
        button_colors = {
            'yb': 'yellow',
            'gb': 'green',
            'rb': 'red'
        }
        for button in ['yellow_button', 'green_button', 'red_button']:
            loc = self.env_settings[button]
            temp = button.split('_')
            color = button_colors[temp[0][0] + temp[1][0]]
            rect = patches.Rectangle((loc[1], self.Nr - loc[0] - 1), 1, 1, linewidth=2, edgecolor='black', facecolor=color)
            self.ax.add_patch(rect)

        # Draw the goal location
        loc = self.env_settings['goal_location']
        rect = patches.Rectangle((loc[1], self.Nr - loc[0] - 1), 1, 1, linewidth=2, edgecolor='black', facecolor='blue')
        self.ax.add_patch(rect)

        # Draw the agents
        for agent in state_dict:
            row, col = self.get_state_description(state_dict[agent])
            rect = patches.Rectangle((col, self.Nr - row - 1), 1, 1, linewidth=1, edgecolor='black', facecolor='grey')
            self.ax.add_patch(rect)

        self.ax.set_xticks([])
        self.ax.set_yticks([])
        if show_plot:
            plt.pause(0.00001)

        
    def animate(self, state_dicts, filename):
        """
        Create a GIF animation of the gridworld over a sequence of states.

        Parameters
        ----------
        state_dicts : list of dict
            List of dictionaries of agent names and their corresponding states.
        gif_filename : str
            Filename for the output GIF file.
        """
        if not self.fig or not self.ax:
            self.fig, self.ax = plt.subplots(figsize=(5, 5))
            self.ax.set_xlim(0, self.Nc)
            self.ax.set_ylim(0, self.Nr)
            self.ax.set_aspect('equal')
        def update(frame):
            self.show(state_dicts[frame], show_plot=False)

        ani = animation.FuncAnimation(self.fig, update, frames=len(state_dicts), repeat=False)
        ani.save(filename, writer='imagemagick', fps=10)
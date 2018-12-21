from collections import defaultdict

import networkx as nx
import numpy as np
from termcolor import cprint
import propy.NetworkUtil as nu

from typing import List, Tuple, Dict, Sequence, Callable
from pprint import pprint
import os


class NetworkPropagation(nx.DiGraph):

    def __init__(self,
                 nodes: Sequence,
                 edges: List[Tuple],
                 num_info: int,
                 propagation: Dict[int, List[Tuple]] or float,
                 user_actions: List[str] = None,
                 seed: int = 42,
                 **attr):

        self.seed = seed
        super().__init__(**attr)

        self.add_nodes_from(nodes)
        self.add_edges_from(edges, follow=1)

        self.num_info = num_info

        self.user_actions, user_actions = [], user_actions if user_actions else []
        self.user_actions.append("follow")
        self._append_user_actions_with_info("propagate")
        for action_key in user_actions:
            self._append_user_actions_with_info(action_key)

        self.info_to_propagation: Dict[int, List[Tuple]] = self._get_info_to_propagation(num_info, propagation)
        self.info_to_attributes: Dict[int, Dict] = {info: {} for info in self.info_to_propagation.keys()}
        self.event_listeners = defaultdict(list)

    def _append_user_actions_with_info(self, action_key):
        for info in range(self.num_info):
            self.user_actions.append("{}_{}".format(action_key, info))

    def _get_info_to_propagation(self,
                                 num_info: int,
                                 propagation: Dict[int, List[Tuple]] or float) -> Dict[int, List[Tuple]]:

        propagation_dict = dict()

        # Generate propagation with probability p if propagation is probability (float)
        if isinstance(propagation, float):
            roots = nu.sample_propagation_roots(self, num_info, seed=self.seed)
            for i, root in enumerate(roots):
                events = nu.get_propagation_events(self, root, propagation, max_iter=len(self.nodes), seed=self.seed)
                propagation_dict[i] = events

        # Add edges with propagate
        propagation_dict = propagation_dict or propagation
        for info, propagation in propagation_dict.items():
            for t, parent_id, node_id in propagation[1:]:  # Exclude ROOT -> ...
                self.add_action(parent_id, node_id, f"propagate_{info}", t)

        return propagation_dict

    # Magic Methods

    def __repr__(self):
        return self.get_title()

    # Data Methods

    def get_action_matrix(self, action_key: str, time_stamp: int or float = None, is_binary_repr=False) -> np.ndarray:
        assert action_key in self.user_actions

        action_matrix = nu.to_numpy_matrix(self, weight=action_key, value_for_non_weight_exist=0)
        if time_stamp is not None:
            action_matrix = np.multiply(action_matrix, action_matrix <= time_stamp)

        if is_binary_repr:
            return (action_matrix != 0).astype(int)
        else:
            return action_matrix

    def dump(self, file_prefix, path=None):
        path = path or "."
        file_path_and_name = os.path.join(path, "{}_{}.pkl".format(file_prefix, self.get_title()))
        nx.write_gpickle(self, file_path_and_name)
        cprint("Dump: {}".format(file_path_and_name), "blue")

    @classmethod
    def load(cls, file_name_or_prefix, path=None):
        path = path or "."
        try:
            file_path_and_name = os.path.join(path, file_name_or_prefix)
            loaded: NetworkPropagation = nx.read_gpickle(file_path_and_name)
        except Exception as e:
            file_name = [f for f in os.listdir(path) if f.startswith(file_name_or_prefix) and f.endswith(".pkl")][-1]
            file_path_and_name = os.path.join(path, file_name)
            loaded: NetworkPropagation = nx.read_gpickle(file_path_and_name)
        cprint("Load: {}".format(file_path_and_name), "green")
        return loaded

    # Propagation Methods

    def get_last_time_of_propagation(self) -> int or float:
        last_times = []
        for _, propagation in self.info_to_propagation.items():
            last_times.append(propagation[-1][0])
        return max(last_times)

    def simulate_propagation(self):
        for info, propagation in self.info_to_propagation.items():
            for t, parent_id, node_id in propagation:
                self._run_event_listener("propagate", (t, parent_id, node_id), info=info)

    # Attributes Manipulation Methods

    def add_action(self, u, v, action_key, value):
        self.add_edge(u, v, **{action_key: value})

    def get_info_attr(self, info, attr=None):
        if attr is None:
            return self.info_to_attributes[info]
        else:
            return self.info_to_attributes[info][attr]

    def set_info_attr(self, info, attr, val):
        self.info_to_attributes[info][attr] = val

    def get_edge_of_attr(self, attr):
        return list(nx.get_edge_attributes(self, attr).keys())

    # Event Listener Methods

    def add_event_listener(self, event_type: str, callback_func: Callable, **kwargs):
        """
        :param event_type: str from ["propagate",]
        :param callback_func: some_func(network_propagation: NetworkPropagation, event: Tuple, info: int, **kwargs)
        :param kwargs: kwargs for callback_func
        :return:
        """
        self.event_listeners[event_type].append((callback_func, kwargs))

    def _run_event_listener(self, given_event_type: str, event: Tuple, info: int):
        for callback_func, kwargs in self.event_listeners[given_event_type]:
            callback_func(
                network_propagation=self,
                event=event,
                info=info,
                **kwargs
            )

    # NetworkX Overrides

    def predecessors(self, n, feature=None):
        if feature is None:
            return super().predecessors(n)
        else:
            return [p for p, features in self._pred[n].items() if feature in features]

    # Util Methods

    def get_roots(self) -> List[int]:
        roots = []
        for info, history in self.info_to_propagation.items():
            roots.append(history[0][-1])  # (t, p, n)
        return roots

    def draw_graph(self):
        roots = self.get_roots()
        node_color = nu.get_highlight_node_color(self.nodes, roots)
        nu.draw_graph(self, node_color=node_color)

    def get_title(self):
        key_attributes = {
            "num_info": self.num_info,
            "nodes": self.number_of_nodes(),
            "edges": self.number_of_edges(),
            "seed": self.seed,
        }
        return "_".join(["{}_{}".format(k, v) for k, v in key_attributes.items()])

    def pprint_propagation(self):
        pprint(self.info_to_propagation)
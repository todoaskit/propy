import os

import pickle
import math

from propy.prop import *
from propy.DataUtil import *

from sklearn.model_selection import KFold


def dump_batch(instance, path, name):
    with open(os.path.join(path, name), 'wb') as f:
        pickle.dump(instance, f)


def assign_or_concat(base_sequence, extra_sequence):

    if base_sequence is None:
        return extra_sequence

    if isinstance(base_sequence, list):
        return base_sequence + extra_sequence
    elif isinstance(base_sequence, np.ndarray):
        return np.concatenate((base_sequence, extra_sequence))
    else:
        raise TypeError


class ActionMatrixLoader:

    __slots__ = ["path", "actions", "edge_indices_list", "selected_node_indices", "x_features", "y_features", "ys",
                 "num_x_features", "num_y_features", "num_classes", "is_coo_repr", "is_x_indices_repr"]

    def __init__(self, path: str, actions: list, is_coo_repr=True, is_x_indices_repr=False, path_exist_ok=True):

        self.path: str = path
        os.makedirs(self.path, exist_ok=path_exist_ok)

        self.actions: list = actions

        # Meta information
        self.num_x_features = None
        self.num_y_features = None
        self.num_classes = None
        self.is_coo_repr = is_coo_repr
        self.is_x_indices_repr = is_x_indices_repr

        # (num_info, num_actions, num_edges, 3:[i, j, val])
        self.edge_indices_list: List[List[np.ndarray]] = None

        # (num_info, num_selected_nodes)
        self.selected_node_indices: List[np.ndarray] = None

        # (num_nodes, num_features)
        self.x_features: np.ndarray = None

        # (num_info, num_y_features)
        self.y_features: np.ndarray = None

        # (num_info, num_classes)
        self.ys: np.ndarray = None

    def __len__(self):
        assert len(self.edge_indices_list) == len(self.ys)
        return len(self.edge_indices_list)

    def __getitem__(self, item) -> Tuple:
        """
        :param item: id (int) of info
        :return: tuple of length 3 or 4
        if is_coo_repr:
            shape of 0: (num_actions, 2, num_selected_edges),
            shape of 1: See is_x_indices_repr,
            shape of 2: (num_selected_nodes, num_y_features) if self.y_features is not None,
            shape of -1: (num_classes,)
        else:
            shape of 0: (num_actions, num_selected_nodes, num_selected_nodes),
            shape of 1: See is_x_indices_repr,
            shape of 2: (num_selected_nodes, num_y_features) if self.y_features is not None
            shape of -1: (num_classes,)

        if is_x_indices_repr:
            shape of 1: (num_selected_nodes,)
        else:
            shape of 1: (num_selected_nodes, num_x_features)

        Note that
            values of <shape of 0> are indices of <shape of 1>
            values of <shape of 1 if is_x_indices_repr> are node_indices (not node_ids)

        TODO: Support slice as an item.
        TODO: Support not is_binary_repr for is_coo_repr & is_binary_repr for not is_coo_repr
        """
        indices = self.selected_node_indices[item]
        if self.is_coo_repr:
            matrices_in_list_form = self.edge_indices_list[item]
            matrices = [list_to_coo(lst) for lst in matrices_in_list_form]
        else:
            matrices = [list_to_matrix(lst, size=len(indices)) for lst in self.edge_indices_list[item]]

        if self.is_x_indices_repr:
            x_features_or_indices = indices
        else:
            x_features_or_indices = self.x_features[indices]

        if self.y_features is not None:
            return matrices, x_features_or_indices, self.y_features[item], self.ys[item]
        else:
            return matrices, x_features_or_indices, self.ys[item]

    def get_batch_generator(self,
                            batch_size=None,
                            shuffle=False,
                            seed=None,
                            is_train=None,
                            train_ratio=0.8,
                            fold=0) -> Generator:

        data_m, data_xf, data_yf, data_y = [], [], [], []

        indexes = np.asarray(range(len(self)))

        if shuffle:
            np.random.seed(seed)
            np.random.shuffle(indexes)

        if is_train is not None:
            kf = KFold(n_splits=int(1/(1-train_ratio)), random_state=seed, shuffle=shuffle)
            assert kf.get_n_splits() > fold
            for i, (train_idx, test_idx) in enumerate(kf.split(indexes)):

                if i != fold:
                    continue

                if is_train:
                    indexes = indexes[train_idx]
                else:
                    indexes = indexes[test_idx]

        for i, idx in enumerate(indexes):

            if len(self.selected_node_indices[idx]) <= 0:
                continue

            if self.y_features is not None:
                m, xf, yf, y = self[idx]
                data_yf.append(yf)
            else:
                m, xf, y = self[idx]

            data_m.append(m)
            data_xf.append(xf)
            data_y.append(y)

            if batch_size and len(data_y) % batch_size == 0:
                yield (data_m, data_xf, data_yf, data_y) if self.y_features is not None else (data_m, data_xf, data_y)
                data_m, data_xf, data_yf, data_y = [], [], [], []

        if len(data_m) != 0:
            yield (data_m, data_xf, data_yf, data_y) if self.y_features is not None else (data_m, data_xf, data_y)

    def update_matrices_and_indices(self, matrices_sequence, selected_node_indices, convert_to_list=True):

        if convert_to_list:
            matrices_sequence_in_list_form = []
            for matrices in matrices_sequence:
                matrices_sequence_in_list_form.append([matrix_to_list(mat) for mat in matrices])
            self.edge_indices_list = assign_or_concat(self.edge_indices_list, matrices_sequence_in_list_form)
        else:
            self.edge_indices_list = assign_or_concat(self.edge_indices_list, matrices_sequence)

        self.selected_node_indices = assign_or_concat(self.selected_node_indices, selected_node_indices)

    def update_x_features(self, x_features):
        if self.x_features is None:
            self.num_x_features = x_features[0].shape[0]
        self.x_features = assign_or_concat(self.x_features, x_features)

    def dynamic_update_x_features(self, update_func: Callable, **kwargs):
        """
        :param update_func: function that takes
                            *(matrices_in_list_form, selected_node_indices, x_features, y_features)
                             & **kwargs
        """
        prev_shape = self.x_features.shape
        self.x_features = update_func(
            matrices_in_list_form=self.edge_indices_list,
            selected_node_indices=self.selected_node_indices,
            x_features=self.x_features,
            y_features=self.y_features,
            **kwargs,
        )
        assert prev_shape == self.x_features.shape

    def update_y_features(self, y_features):
        if self.y_features is None:
            self.num_y_features = y_features[0].shape[0]
        self.y_features = assign_or_concat(self.y_features, y_features)

    def update_ys(self, ys):
        if self.ys is None:
            self.num_classes = 4  # TODO
        self.ys = assign_or_concat(self.ys, ys)

    def dump(self, name_prefix, num_subfiles=1):

        assert self.edge_indices_list is not None
        assert len(self.edge_indices_list) == len(self.ys)

        # Dump xs, ys
        info_batch_size = int(math.ceil(len(self) / num_subfiles))
        x_batch_size = int(math.ceil(len(self.x_features) / num_subfiles))

        for i in range(num_subfiles):

            info_start, info_end = (i*info_batch_size, (i+1)*info_batch_size)
            x_start, x_end = (i*x_batch_size, (i+1)*x_batch_size)

            instance_to_dump = ActionMatrixLoader(path=self.path, actions=self.actions)
            instance_to_dump.update_matrices_and_indices(
                matrices_sequence=self.edge_indices_list[info_start:info_end],
                selected_node_indices=self.selected_node_indices[info_start:info_end],
                convert_to_list=False,
            )
            instance_to_dump.update_x_features(self.x_features[x_start:x_end])
            instance_to_dump.update_ys(self.ys[info_start:info_end])
            if self.y_features is not None:
                instance_to_dump.update_y_features(self.y_features[info_start:info_end])
            dump_batch(instance=instance_to_dump, path=self.path, name="{}_{}.pkl".format(name_prefix, i))

        cprint("Dump: {} with num_subfiles {}".format(name_prefix, num_subfiles), "blue")

    def load(self, name_prefix):
        # Load xs, ys
        file_names_of_prefix = [f for f in os.listdir(self.path) if f.startswith(name_prefix) and f.endswith(".pkl")]

        if not file_names_of_prefix:
            return False

        for file_name in file_names_of_prefix:
            if not self._load_batch(path=self.path, name=file_name):
                cprint("Load Failed in Loading {}".format(file_names_of_prefix), "red")
                return False

        cprint("Loaded: {}".format(file_names_of_prefix), "green")
        return True

    def _load_batch(self, path, name):
        try:
            with open(os.path.join(path, name), 'rb') as f:
                loaded: ActionMatrixLoader = pickle.load(f)
                self.edge_indices_list = assign_or_concat(self.edge_indices_list, loaded.edge_indices_list)
                self.selected_node_indices = assign_or_concat(self.selected_node_indices, loaded.selected_node_indices)
                self.x_features = assign_or_concat(self.x_features, loaded.x_features)
                self.y_features = assign_or_concat(self.y_features, loaded.y_features)
                self.ys = assign_or_concat(self.ys, loaded.ys)
            return True
        except Exception as e:
            cprint('Load Failed: {} \n\t{}.\n'.format(os.path.join(path, name), e), "red")
            return False

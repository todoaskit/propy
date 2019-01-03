import numpy as np


def ones_feature(num_nodes, num_features):
    return np.ones(shape=(num_nodes, num_features))


def matrix_to_list(matrix, default_value=0):
    lst = []
    for i, row in enumerate(matrix):
        for j, val in enumerate(row):
            if val != default_value:
                lst.append([i, j, val])
    return lst


def list_to_matrix(lst, size, default_value=0):
    matrix = np.full(shape=(size, size), fill_value=default_value)
    for i, j, val in lst:
        matrix[i][j] = val
    return matrix


def list_to_coo(lst) -> np.ndarray:
    """
    :param lst: list of [u, v, val]
    :return: ndarray of shape (2, num_edges)
    """
    if len(lst) == 0:
        return np.asarray([[], []])
    else:
        arr = np.asarray(lst)
        coo = np.transpose(arr[:, :2])
        return coo.astype(np.int)


def list_to_edge_attr(lst) -> np.ndarray:
    """
    :param lst: list of [u, v, val]
    :return: ndarray of shape (num_edges,)
    """
    return np.asarray([val for (_, _, val) in lst])

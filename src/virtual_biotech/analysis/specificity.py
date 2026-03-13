"""Cell-type specificity and expression heterogeneity metrics."""

import numpy as np
from scipy.stats import kurtosis, skew


def compute_tau(mean_expression_per_celltype: np.ndarray) -> float:
    """Compute tau specificity index.

    Args:
        mean_expression_per_celltype: Array of mean log-normalized expression
            per cell type (cell types with <20 cells excluded).

    Returns:
        Tau index in [0, 1]. 0 = ubiquitous, 1 = perfectly specific.
    """
    x = mean_expression_per_celltype
    x_max = np.max(x)
    if x_max == 0:
        return 0.0
    n = len(x)
    if n <= 1:
        return 0.0
    tau = np.sum(1 - x / x_max) / (n - 1)
    return float(tau)


def compute_bimodality_coefficient(expression_values: np.ndarray) -> float:
    """Compute bimodality coefficient among expressing cells.

    Args:
        expression_values: Expression values for cells with expression > 0.

    Returns:
        BC in [0, 1]. BC > 0.555 suggests bimodal distribution.
    """
    x = expression_values[expression_values > 0]
    n = len(x)
    if n < 4:
        return 0.0
    m3 = skew(x)
    m4 = kurtosis(x, fisher=True)  # Excess kurtosis
    numerator = m3**2 + 1
    denominator = m4 + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))
    return float(numerator / denominator)

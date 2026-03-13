"""Feature-to-outcome statistical analysis utilities."""

import numpy as np
import statsmodels.api as sm
from scipy.stats import zscore


def analyze_feature_outcome_association(
    df,
    feature_col: str,
    outcome_col: str,
) -> dict:
    """Univariate logistic regression of standardized feature vs binary outcome.

    Args:
        df: DataFrame with trial-level features and outcomes.
        feature_col: Column name for feature (e.g., "tau_cell_type_specificity").
        outcome_col: Column name for binary outcome (e.g., "primary_endpoint_met").

    Returns:
        Dictionary with odds_ratio, CI, p-value, sample size, and event count.
    """
    df = df.dropna(subset=[feature_col, outcome_col])
    x_values = zscore(df[feature_col].values)
    x_with_const = sm.add_constant(x_values.reshape(-1, 1))
    y = df[outcome_col].values.astype(int)

    model = sm.GLM(y, x_with_const, family=sm.families.Binomial())
    result = model.fit()

    or_estimate = np.exp(result.params[1])
    ci_array = result.conf_int()
    ci = np.exp(ci_array[1])

    return {
        "odds_ratio": float(or_estimate),
        "ci_lower": float(ci[0]),
        "ci_upper": float(ci[1]),
        "pvalue": float(result.pvalues[1]),
        "n": len(y),
        "events": int(y.sum()),
    }


def permutation_test(
    df,
    feature_col: str,
    outcome_col: str,
    n_permutations: int = 1000,
) -> dict:
    """Permutation test: shuffle outcomes, refit regression, compare coefficients.

    Args:
        df: DataFrame with trial-level features and outcomes.
        feature_col: Feature column name.
        outcome_col: Outcome column name.
        n_permutations: Number of permutation iterations.

    Returns:
        Dictionary with observed log-OR, permutation p-value, and null distribution.
    """
    rng = np.random.default_rng()
    observed = analyze_feature_outcome_association(df, feature_col, outcome_col)
    observed_coef = np.log(observed["odds_ratio"])

    null_coefs = []
    for _ in range(n_permutations):
        df_perm = df.copy()
        df_perm[outcome_col] = rng.permutation(df_perm[outcome_col].values)
        try:
            result = analyze_feature_outcome_association(df_perm, feature_col, outcome_col)
            null_coefs.append(np.log(result["odds_ratio"]))
        except Exception:
            continue

    null_coefs = np.array(null_coefs)
    p_value = float(np.mean(np.abs(null_coefs) >= np.abs(observed_coef)))

    return {
        "observed_log_or": float(observed_coef),
        "p_permutation": p_value,
        "null_distribution": null_coefs,
    }

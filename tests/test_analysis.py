"""Tests for analysis utility functions."""

import numpy as np
import pandas as pd
import pytest

from virtual_biotech.analysis.hallmarks import (
    HALLMARK_GENE_SETS,
    compute_all_hallmark_scores,
    compute_hallmark_score,
)
from virtual_biotech.analysis.specificity import (
    compute_bimodality_coefficient,
    compute_tau,
)
from virtual_biotech.analysis.statistics import (
    analyze_feature_outcome_association,
    permutation_test,
)


class TestTauSpecificity:
    """Tests for tau cell-type specificity index."""

    def test_perfectly_specific(self):
        """Gene expressed in only one cell type has tau = 1."""
        expr = np.array([10.0, 0.0, 0.0, 0.0, 0.0])
        tau = compute_tau(expr)
        assert tau == pytest.approx(1.0)

    def test_ubiquitous(self):
        """Gene equally expressed in all cell types has tau = 0."""
        expr = np.array([5.0, 5.0, 5.0, 5.0, 5.0])
        tau = compute_tau(expr)
        assert tau == pytest.approx(0.0)

    def test_no_expression(self):
        """Gene with zero expression everywhere returns 0."""
        expr = np.array([0.0, 0.0, 0.0])
        tau = compute_tau(expr)
        assert tau == 0.0

    def test_single_cell_type(self):
        """Single cell type returns 0 (not enough to compute)."""
        expr = np.array([5.0])
        tau = compute_tau(expr)
        assert tau == 0.0

    def test_intermediate_specificity(self):
        """Partially specific gene has tau between 0 and 1."""
        expr = np.array([10.0, 2.0, 1.0, 0.5])
        tau = compute_tau(expr)
        assert 0.0 < tau < 1.0

    def test_tau_range(self):
        """Tau is always in [0, 1]."""
        rng = np.random.default_rng(42)
        for _ in range(100):
            expr = rng.exponential(scale=5.0, size=10)
            tau = compute_tau(expr)
            assert 0.0 <= tau <= 1.0


class TestBimodalityCoefficient:
    """Tests for bimodality coefficient."""

    def test_too_few_expressing_cells(self):
        """Returns 0 when fewer than 4 expressing cells."""
        expr = np.array([0.0, 0.0, 1.0, 2.0])
        bc = compute_bimodality_coefficient(expr)
        assert bc == 0.0

    def test_all_zeros(self):
        """Returns 0 for all-zero expression."""
        expr = np.zeros(100)
        bc = compute_bimodality_coefficient(expr)
        assert bc == 0.0

    def test_unimodal_normal(self):
        """Unimodal normal distribution has BC < 0.555."""
        rng = np.random.default_rng(42)
        expr = np.abs(rng.normal(loc=5, scale=1, size=1000))
        bc = compute_bimodality_coefficient(expr)
        assert bc < 0.555

    def test_bimodal_distribution(self):
        """Bimodal distribution has BC > 0.555."""
        rng = np.random.default_rng(42)
        # Two distinct modes with moderate overlap
        low_mode = rng.normal(loc=2, scale=0.5, size=500)
        high_mode = rng.normal(loc=5, scale=0.5, size=500)
        expr = np.concatenate([low_mode, high_mode])
        expr = expr[expr > 0]
        bc = compute_bimodality_coefficient(expr)
        assert bc > 0.555

    def test_bc_range(self):
        """BC is always non-negative."""
        rng = np.random.default_rng(42)
        expr = rng.exponential(scale=2, size=200)
        bc = compute_bimodality_coefficient(expr)
        assert bc >= 0.0


class TestHallmarkScores:
    """Tests for hallmark signature scoring."""

    def test_all_hallmarks_defined(self):
        """All 6 hallmark gene sets are defined."""
        assert len(HALLMARK_GENE_SETS) == 6
        expected = {"apoptosis", "proliferation_suppression", "dna_damage", "stress_response", "resistance", "cell_cycle_arrest"}
        assert set(HALLMARK_GENE_SETS.keys()) == expected

    def test_apoptosis_positive_lfc(self):
        """Positive LFC in apoptosis genes → positive score (drug induces apoptosis)."""
        lfc = {gene: 1.0 for gene in HALLMARK_GENE_SETS["apoptosis"]["genes"]}
        score = compute_hallmark_score(lfc, "apoptosis")
        assert score > 0

    def test_proliferation_suppression_negative_lfc(self):
        """Negative LFC in proliferation genes → positive score (suppression)."""
        lfc = {gene: -1.0 for gene in HALLMARK_GENE_SETS["proliferation_suppression"]["genes"]}
        score = compute_hallmark_score(lfc, "proliferation_suppression")
        assert score > 0

    def test_cell_cycle_arrest_mixed(self):
        """Cell cycle arrest uses mixed direction genes."""
        lfc = {}
        for gene in HALLMARK_GENE_SETS["cell_cycle_arrest"]["positive_genes"]:
            lfc[gene] = 1.0  # Upregulated → arrest
        for gene in HALLMARK_GENE_SETS["cell_cycle_arrest"]["negative_genes"]:
            lfc[gene] = -1.0  # Downregulated → arrest
        score = compute_hallmark_score(lfc, "cell_cycle_arrest")
        assert score > 0

    def test_zero_lfc_returns_zero(self):
        """All-zero LFC gives zero score."""
        lfc = {}
        score = compute_hallmark_score(lfc, "apoptosis")
        assert score == 0.0

    def test_missing_genes_treated_as_zero(self):
        """Missing genes default to LFC=0."""
        lfc = {"BAX": 2.0}  # Only one gene present
        score = compute_hallmark_score(lfc, "apoptosis")
        n_genes = len(HALLMARK_GENE_SETS["apoptosis"]["genes"])
        expected = 1.0 * 2.0 / n_genes  # direction * mean(2/n + 0*(n-1)/n)
        assert score == pytest.approx(expected, rel=1e-6)

    def test_compute_all_scores(self):
        """compute_all_hallmark_scores returns all 6 scores."""
        lfc = {"BAX": 1.0, "MKI67": -0.5, "GADD45A": 0.8}
        scores = compute_all_hallmark_scores(lfc)
        assert len(scores) == 6
        assert all(isinstance(v, float) for v in scores.values())


class TestStatistics:
    """Tests for feature-outcome statistical analysis."""

    def _make_trial_df(self, n: int = 100, seed: int = 42) -> pd.DataFrame:
        """Create a synthetic trial-level DataFrame."""
        rng = np.random.default_rng(seed)
        feature = rng.normal(size=n)
        # Higher feature → higher probability of positive outcome
        prob = 1 / (1 + np.exp(-0.8 * feature))
        outcome = rng.binomial(1, prob, size=n)
        return pd.DataFrame({"feature": feature, "outcome": outcome})

    def test_logistic_regression_returns_required_keys(self):
        """analyze_feature_outcome_association returns OR, CI, p-value, n, events."""
        df = self._make_trial_df()
        result = analyze_feature_outcome_association(df, "feature", "outcome")
        assert "odds_ratio" in result
        assert "ci_lower" in result
        assert "ci_upper" in result
        assert "pvalue" in result
        assert "n" in result
        assert "events" in result

    def test_logistic_regression_or_direction(self):
        """Positive feature-outcome association yields OR > 1."""
        df = self._make_trial_df(n=500)
        result = analyze_feature_outcome_association(df, "feature", "outcome")
        assert result["odds_ratio"] > 1.0

    def test_logistic_regression_sample_size(self):
        """Reported n matches input DataFrame length."""
        df = self._make_trial_df(n=80)
        result = analyze_feature_outcome_association(df, "feature", "outcome")
        assert result["n"] == 80

    def test_permutation_test_returns_required_keys(self):
        """permutation_test returns observed log-OR and permutation p-value."""
        df = self._make_trial_df(n=60)
        result = permutation_test(df, "feature", "outcome", n_permutations=50)
        assert "observed_log_or" in result
        assert "p_permutation" in result
        assert "null_distribution" in result

    def test_permutation_pvalue_range(self):
        """Permutation p-value is between 0 and 1."""
        df = self._make_trial_df(n=60)
        result = permutation_test(df, "feature", "outcome", n_permutations=50)
        assert 0.0 <= result["p_permutation"] <= 1.0

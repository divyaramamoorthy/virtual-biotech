"""Hallmark signature scores from drug perturbation data."""

import numpy as np

HALLMARK_GENE_SETS: dict[str, dict] = {
    "apoptosis": {
        "genes": ["BAX", "CASP3", "CASP9", "BID", "PMAIP1", "BBC3", "APAF1", "CYCS", "CASP7", "CASP8", "FAS"],
        "direction": +1,
    },
    "proliferation_suppression": {
        "genes": ["MKI67", "PCNA", "TOP2A", "CDK1", "AURKA", "AURKB", "BUB1", "CCNB2", "CDC20", "PLK1", "TPX2"],
        "direction": -1,
    },
    "dna_damage": {
        "genes": ["GADD45A", "MDM2", "CDKN1A", "DDB2", "XPC"],
        "direction": +1,
    },
    "stress_response": {
        "genes": ["DDIT3", "ATF4", "HSPA5", "XBP1", "ATF6", "ERN1", "HMOX1", "NQO1", "TXNRD1", "GCLM", "SQSTM1"],
        "direction": +1,
    },
    "resistance": {
        "genes": ["BCL2", "MCL1", "XIAP", "BIRC5", "BCL2L1", "ABCB1", "ABCG2", "CFLAR"],
        "direction": +1,
    },
    "cell_cycle_arrest": {
        "positive_genes": ["CDKN1A", "CDKN1B", "CDKN2A", "BTG2"],
        "negative_genes": ["CCNA2", "CCNB1", "CCNE1"],
    },
}


def compute_hallmark_score(lfc_dict: dict[str, float], hallmark: str) -> float:
    """Compute hallmark signature score from log-fold changes.

    Args:
        lfc_dict: {gene_symbol: lfc_value} with non-significant (adj p >= 0.05) set to 0.
        hallmark: One of the hallmark names from HALLMARK_GENE_SETS.

    Returns:
        Hallmark score. Positive = drug efficacy direction.
    """
    config = HALLMARK_GENE_SETS[hallmark]

    if hallmark == "cell_cycle_arrest":
        pos_genes = config["positive_genes"]
        neg_genes = config["negative_genes"]
        pos_score = np.mean([lfc_dict.get(g, 0) for g in pos_genes])
        neg_score = np.mean([lfc_dict.get(g, 0) for g in neg_genes])
        return float(pos_score - neg_score)
    else:
        genes = config["genes"]
        direction = config["direction"]
        mean_lfc = np.mean([lfc_dict.get(g, 0) for g in genes])
        return float(direction * mean_lfc)


def compute_all_hallmark_scores(lfc_dict: dict[str, float]) -> dict[str, float]:
    """Compute all 6 hallmark scores from log-fold changes.

    Args:
        lfc_dict: {gene_symbol: lfc_value} with non-significant set to 0.

    Returns:
        Dictionary mapping hallmark name to score.
    """
    return {hallmark: compute_hallmark_score(lfc_dict, hallmark) for hallmark in HALLMARK_GENE_SETS}

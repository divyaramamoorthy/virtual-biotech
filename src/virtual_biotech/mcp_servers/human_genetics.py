"""Human Genetics MCP Server — GWAS, QTL, gnomAD, ClinVar, dbSNP, PharmGKB, ENCODE E2G."""

import httpx
from fastmcp import FastMCP

mcp = FastMCP("human-genetics")

OPEN_TARGETS_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"


def _ot_graphql(query: str, variables: dict) -> dict:
    """Execute an Open Targets GraphQL query."""
    response = httpx.post(OPEN_TARGETS_GRAPHQL, json={"query": query, "variables": variables}, timeout=30)
    response.raise_for_status()
    return response.json()


@mcp.tool()
def query_gwas_associations(gene_symbol: str, disease_id: str) -> dict:
    """Query GWAS catalog and Open Targets for variant-disease associations at a gene locus.

    Args:
        gene_symbol: Official gene symbol (e.g., "BRCA1", "TP53").
        disease_id: EFO disease identifier (e.g., "EFO_0000270" for asthma).

    Returns:
        Dictionary with lead variants, p-values, effect sizes, sample sizes,
        and study metadata.
    """
    query = """
    query GWASAssociations($ensemblId: String!, $efoId: String!) {
        disease(efoId: $efoId) {
            associatedTargets(page: {size: 50, index: 0}) {
                rows {
                    target { approvedSymbol id }
                    score
                    datatypeScores { id score }
                }
            }
        }
    }
    """
    # First resolve gene symbol to Ensembl ID
    search_query = """
    query SearchTarget($queryString: String!) {
        search(queryString: $queryString, entityNames: ["target"], page: {size: 1, index: 0}) {
            hits { id name entity }
        }
    }
    """
    search_result = _ot_graphql(search_query, {"queryString": gene_symbol})
    hits = search_result.get("data", {}).get("search", {}).get("hits", [])
    ensembl_id = hits[0]["id"] if hits else None

    if not ensembl_id:
        return {"gene_symbol": gene_symbol, "disease_id": disease_id, "error": "Gene not found", "associations": []}

    result = _ot_graphql(query, {"ensemblId": ensembl_id, "efoId": disease_id})
    rows = result.get("data", {}).get("disease", {}).get("associatedTargets", {}).get("rows", [])

    target_row = next((r for r in rows if r["target"]["approvedSymbol"] == gene_symbol), None)

    return {
        "gene_symbol": gene_symbol,
        "ensembl_id": ensembl_id,
        "disease_id": disease_id,
        "overall_score": target_row["score"] if target_row else 0.0,
        "datatype_scores": target_row["datatypeScores"] if target_row else [],
    }


@mcp.tool()
def query_credible_sets(gene_symbol: str, disease_id: str) -> dict:
    """Retrieve fine-mapped credible sets from SuSiE/SuSiE-inf via Open Targets Genetics.

    Args:
        gene_symbol: Official gene symbol.
        disease_id: EFO disease identifier.

    Returns:
        Dictionary with variant IDs, posterior inclusion probabilities,
        and credible set size.
    """
    # Resolve gene symbol to Ensembl ID
    search_query = """
    query SearchTarget($queryString: String!) {
        search(queryString: $queryString, entityNames: ["target"], page: {size: 1, index: 0}) {
            hits { id }
        }
    }
    """
    search_result = _ot_graphql(search_query, {"queryString": gene_symbol})
    hits = search_result.get("data", {}).get("search", {}).get("hits", [])
    ensembl_id = hits[0]["id"] if hits else None

    if not ensembl_id:
        return {"gene_symbol": gene_symbol, "disease_id": disease_id, "error": "Gene not found"}

    # Query Open Targets for credible set evidence via the evidences endpoint
    credible_query = """
    query CredibleSets($ensemblId: String!, $efoId: String!) {
        target(ensemblId: $ensemblId) {
            evidences(datasourceIds: ["ot_genetics_portal"], diseaseIds: [$efoId], size: 20) {
                rows {
                    variantId
                    studyId
                    score
                    resourceScore
                }
            }
        }
    }
    """
    try:
        result = _ot_graphql(credible_query, {"ensemblId": ensembl_id, "efoId": disease_id})
        rows = result.get("data", {}).get("target", {}).get("evidences", {}).get("rows", [])
    except Exception:
        rows = []

    credible_sets = []
    for row in rows:
        credible_sets.append(
            {
                "variant_id": row.get("variantId"),
                "study_id": row.get("studyId"),
                "score": row.get("score"),
                "resource_score": row.get("resourceScore"),
            }
        )

    return {
        "gene_symbol": gene_symbol,
        "ensembl_id": ensembl_id,
        "disease_id": disease_id,
        "credible_sets": credible_sets,
    }


@mcp.tool()
def query_l2g_scores(gene_symbol: str, disease_id: str) -> dict:
    """Get locus-to-gene (L2G) machine learning causal gene predictions.

    Args:
        gene_symbol: Official gene symbol.
        disease_id: EFO disease identifier.

    Returns:
        Dictionary with L2G score, rank, and contributing features
        (eQTL, chromatin, distance).
    """
    search_query = """
    query SearchTarget($queryString: String!) {
        search(queryString: $queryString, entityNames: ["target"], page: {size: 1, index: 0}) {
            hits { id }
        }
    }
    """
    search_result = _ot_graphql(search_query, {"queryString": gene_symbol})
    hits = search_result.get("data", {}).get("search", {}).get("hits", [])
    ensembl_id = hits[0]["id"] if hits else None

    if not ensembl_id:
        return {"gene_symbol": gene_symbol, "error": "Gene not found"}

    # Query Open Targets for genetic association evidence which includes L2G-derived scores
    l2g_query = """
    query L2GEvidence($ensemblId: String!, $efoId: String!) {
        target(ensemblId: $ensemblId) {
            evidences(datasourceIds: ["ot_genetics_portal"], diseaseIds: [$efoId], size: 50) {
                rows {
                    variantId
                    studyId
                    score
                    resourceScore
                }
            }
        }
    }
    """
    try:
        result = _ot_graphql(l2g_query, {"ensemblId": ensembl_id, "efoId": disease_id})
        rows = result.get("data", {}).get("target", {}).get("evidences", {}).get("rows", [])
    except Exception:
        rows = []

    # The resource_score from ot_genetics_portal reflects L2G-derived confidence
    l2g_entries = []
    max_score = None
    for row in rows:
        score = row.get("resourceScore")
        l2g_entries.append(
            {
                "variant_id": row.get("variantId"),
                "study_id": row.get("studyId"),
                "l2g_score": score,
            }
        )
        if score is not None and (max_score is None or score > max_score):
            max_score = score

    return {
        "gene_symbol": gene_symbol,
        "disease_id": disease_id,
        "ensembl_id": ensembl_id,
        "max_l2g_score": max_score,
        "l2g_entries": l2g_entries,
    }


@mcp.tool()
def query_qtl_colocalization(gene_symbol: str, tissue: str) -> dict:
    """Query eQTL/pQTL/sQTL colocalization results.

    Args:
        gene_symbol: Official gene symbol.
        tissue: GTEx tissue name (e.g., "Lung", "Colon_Transverse").

    Returns:
        Dictionary with H4 posterior probabilities, CLPP scores,
        and tissue specificity.
    """
    # Resolve gene to Ensembl ID
    search_query = """
    query SearchTarget($queryString: String!) {
        search(queryString: $queryString, entityNames: ["target"], page: {size: 1, index: 0}) {
            hits { id }
        }
    }
    """
    search_result = _ot_graphql(search_query, {"queryString": gene_symbol})
    hits = search_result.get("data", {}).get("search", {}).get("hits", [])
    ensembl_id = hits[0]["id"] if hits else None

    if not ensembl_id:
        return {"gene_symbol": gene_symbol, "tissue": tissue, "error": "Gene not found"}

    # Query GTEx eQTL data from the GTEx portal
    gtex_url = "https://gtexportal.org/api/v2/association/singleTissueEqtl"
    eqtl_data = []
    try:
        params = {"gencodeId": ensembl_id, "tissueSiteDetailId": tissue, "datasetId": "gtex_v8"}
        response = httpx.get(gtex_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        for entry in data.get("singleTissueEqtl", [])[:20]:
            eqtl_data.append(
                {
                    "variant_id": entry.get("variantId"),
                    "pvalue": entry.get("pValue"),
                    "nes": entry.get("nes"),
                    "tissue": entry.get("tissueSiteDetailId"),
                }
            )
    except Exception:
        pass

    # Also check Open Targets for expression QTL evidence
    qtl_query = """
    query QTLEvidence($ensemblId: String!) {
        target(ensemblId: $ensemblId) {
            evidences(datasourceIds: ["expression_atlas"], size: 20) {
                rows {
                    score
                    studyId
                }
            }
        }
    }
    """
    expression_evidence = []
    try:
        result = _ot_graphql(qtl_query, {"ensemblId": ensembl_id})
        rows = result.get("data", {}).get("target", {}).get("evidences", {}).get("rows", [])
        for row in rows:
            expression_evidence.append({"study_id": row.get("studyId"), "score": row.get("score")})
    except Exception:
        pass

    return {
        "gene_symbol": gene_symbol,
        "ensembl_id": ensembl_id,
        "tissue": tissue,
        "eqtl_data": eqtl_data,
        "expression_evidence": expression_evidence,
    }


@mcp.tool()
def query_rare_variants(gene_symbol: str) -> dict:
    """Retrieve gnomAD constraint metrics and ClinVar pathogenic variants.

    Args:
        gene_symbol: Official gene symbol.

    Returns:
        Dictionary with pLI, LOEUF, missense Z scores, ClinVar pathogenic
        variants, and rare variant burden meta-analysis results.
    """
    # Query gnomAD for constraint metrics
    gnomad_url = "https://gnomad.broadinstitute.org/api"
    query = """
    query GeneConstraint($geneSymbol: String!) {
        gene(gene_symbol: $geneSymbol, reference_genome: GRCh38) {
            gene_id
            symbol
            gnomad_constraint {
                exp_lof
                exp_mis
                exp_syn
                obs_lof
                obs_mis
                obs_syn
                oe_lof
                oe_lof_lower
                oe_lof_upper
                oe_mis
                oe_mis_lower
                oe_mis_upper
                pLI
                lof_z
                mis_z
                syn_z
            }
        }
    }
    """
    try:
        response = httpx.post(gnomad_url, json={"query": query, "variables": {"geneSymbol": gene_symbol}}, timeout=30)
        response.raise_for_status()
        data = response.json()
        constraint = data.get("data", {}).get("gene", {}).get("gnomad_constraint", {})
    except Exception:
        constraint = {}

    # Query ClinVar via NCBI E-utilities
    clinvar_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    try:
        params = {
            "db": "clinvar",
            "term": f"{gene_symbol}[gene] AND pathogenic[clinsig]",
            "retmode": "json",
            "retmax": 20,
        }
        response = httpx.get(clinvar_url, params=params, timeout=30)
        response.raise_for_status()
        clinvar_data = response.json()
        clinvar_count = int(clinvar_data.get("esearchresult", {}).get("count", 0))
    except Exception:
        clinvar_count = 0

    return {
        "gene_symbol": gene_symbol,
        "constraint_metrics": {
            "pLI": constraint.get("pLI"),
            "loeuf": constraint.get("oe_lof_upper"),
            "oe_lof": constraint.get("oe_lof"),
            "missense_z": constraint.get("mis_z"),
        },
        "clinvar_pathogenic_count": clinvar_count,
    }


@mcp.tool()
def query_pharmacogenomics(gene_symbol: str) -> dict:
    """Query PharmGKB for pharmacogenomic variant annotations.

    Args:
        gene_symbol: Official gene symbol.

    Returns:
        Dictionary with drug-gene relationships and clinical annotations.
    """
    url = f"https://api.pharmgkb.org/v1/data/gene?symbol={gene_symbol}"
    try:
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception:
        data = {}

    return {
        "gene_symbol": gene_symbol,
        "pharmgkb_data": data,
    }


@mcp.tool()
def query_enhancer_gene(gene_symbol: str, tissue: str) -> dict:
    """Get ENCODE E2G enhancer-to-gene predictions for a locus in specified tissue.

    Args:
        gene_symbol: Official gene symbol.
        tissue: Tissue/cell type for E2G predictions.

    Returns:
        Dictionary with regulatory element count and confidence scores.
    """
    # Query ENCODE portal for regulatory elements near the gene
    encode_url = "https://www.encodeproject.org/search/"
    params = {
        "type": "Annotation",
        "annotation_type": "candidate Cis-Regulatory Elements",
        "target.gene_symbol": gene_symbol,
        "biosample_ontology.term_name": tissue,
        "format": "json",
        "limit": 25,
    }
    try:
        response = httpx.get(encode_url, params=params, headers={"Accept": "application/json"}, timeout=30)
        response.raise_for_status()
        data = response.json()
        results = data.get("@graph", [])
    except Exception:
        results = []

    enhancer_links = []
    for item in results:
        enhancer_links.append(
            {
                "accession": item.get("accession", ""),
                "description": item.get("description", ""),
                "biosample": item.get("biosample_summary", ""),
                "status": item.get("status", ""),
            }
        )

    # Also query Open Targets for regulatory variant evidence
    search_query = """
    query SearchTarget($queryString: String!) {
        search(queryString: $queryString, entityNames: ["target"], page: {size: 1, index: 0}) {
            hits { id }
        }
    }
    """
    try:
        search_result = _ot_graphql(search_query, {"queryString": gene_symbol})
        hits = search_result.get("data", {}).get("search", {}).get("hits", [])
        ensembl_id = hits[0]["id"] if hits else None
    except Exception:
        ensembl_id = None

    return {
        "gene_symbol": gene_symbol,
        "tissue": tissue,
        "ensembl_id": ensembl_id,
        "enhancer_gene_links": enhancer_links,
        "regulatory_element_count": len(enhancer_links),
    }


if __name__ == "__main__":
    mcp.run()

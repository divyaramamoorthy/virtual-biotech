"""Tests for the shared MCP source metadata helper."""

from datetime import date

from virtual_biotech.mcp_servers._sources import make_source


def test_make_source_full():
    """Test make_source with all parameters."""
    result = make_source(
        "Open Targets Platform",
        url="https://platform.opentargets.org/target/ENSG00000141510",
        version="v4",
        identifiers={"ensembl_id": "ENSG00000141510"},
    )

    assert result["database"] == "Open Targets Platform"
    assert result["url"] == "https://platform.opentargets.org/target/ENSG00000141510"
    assert result["version"] == "v4"
    assert result["identifiers"] == {"ensembl_id": "ENSG00000141510"}
    assert result["accessed"] == date.today().isoformat()


def test_make_source_minimal():
    """Test make_source with only the database name."""
    result = make_source("gnomAD")

    assert result["database"] == "gnomAD"
    assert result["accessed"] == date.today().isoformat()
    assert "url" not in result
    assert "version" not in result
    assert "identifiers" not in result


def test_make_source_with_url_only():
    """Test make_source with database and URL, no optional fields."""
    result = make_source("ClinVar", url="https://www.ncbi.nlm.nih.gov/clinvar/?term=TP53[gene]")

    assert result["database"] == "ClinVar"
    assert result["url"] == "https://www.ncbi.nlm.nih.gov/clinvar/?term=TP53[gene]"
    assert "version" not in result
    assert "identifiers" not in result


def test_make_source_accessed_is_today():
    """Test that accessed date is always today's ISO date."""
    result = make_source("ChEMBL")
    assert result["accessed"] == date.today().isoformat()

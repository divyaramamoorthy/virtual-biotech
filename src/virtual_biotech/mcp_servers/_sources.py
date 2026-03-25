"""Shared source metadata helper for MCP tool citation provenance."""

from datetime import date


def make_source(
    database: str,
    url: str | None = None,
    *,
    version: str | None = None,
    identifiers: dict[str, str] | None = None,
) -> dict:
    """Build a source metadata dict for inclusion in MCP tool responses.

    Args:
        database: Name of the data source (e.g., "Open Targets Platform").
        url: Direct URL to the relevant resource page.
        version: Data version or release identifier.
        identifiers: Key identifiers used in the query (e.g., {"ensembl_id": "ENSG00000141510"}).

    Returns:
        Dict with database, accessed date, and optional url/version/identifiers.
    """
    source: dict = {
        "database": database,
        "accessed": date.today().isoformat(),
    }
    if url:
        source["url"] = url
    if version:
        source["version"] = version
    if identifiers:
        source["identifiers"] = identifiers
    return source

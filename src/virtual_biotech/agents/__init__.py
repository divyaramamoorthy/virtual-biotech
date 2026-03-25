"""Agent definitions for the Virtual Biotech organization."""

CITATION_INSTRUCTION = """
DATA SOURCE CITATIONS:
Cite claims that come from MCP tool results using inline references [1], [2], etc.
Extract source information exclusively from the "_sources" field returned by MCP tools.
At the end of your analysis, include a "## Data Sources" section listing each cited
source with its database name, URL, and access date.

Only cite data retrieved via MCP tools. Do NOT cite literature, review articles,
textbook knowledge, or general scientific background — those do not need citations.
Do NOT invent or guess URLs. If a tool response has no "_sources" field, do not
fabricate a citation for it.

Example:
  GWAS analysis reveals a strong association (score=0.82) between TP53 and
  breast carcinoma [1]. Genetic constraint analysis shows high intolerance
  to loss-of-function (pLI=0.99) [2]. TP53 is a well-known tumor suppressor
  involved in cell cycle regulation (no citation needed — general knowledge).

  ## Data Sources
  [1] Open Targets Platform — https://platform.opentargets.org/evidence/ENSG00000141510/EFO_0000305 (accessed 2026-03-24)
  [2] gnomAD — https://gnomad.broadinstitute.org/gene/TP53?dataset=gnomad_r4 (accessed 2026-03-24)
"""

"""Context assembler — builds LLM context from ontology routing results.

Assembles structured context (schema, terms, metrics, lineage) from
RDF graph data for injection into the Copilot prompt.
"""

from __future__ import annotations

import logging
from typing import Any

from ontology import NS, kb_graph_iri

_logger = logging.getLogger(__name__)


class ContextAssembler:
    """Assembles LLM-ready context from RDF ontology data.

    Usage:
        assembler = ContextAssembler(store)
        ctx = assembler.build_context(kb_ids=[1], routing_result={...})
    """

    def __init__(self, store: Any):
        self._store = store

    def build_context(
        self,
        kb_ids: list[int],
        routing_result: dict[str, Any],
        *,
        max_terms: int = 15,
        max_metrics: int = 10,
        max_tables: int = 20,
    ) -> dict[str, Any]:
        """Build full context from routing results.

        Returns a dict with sections: terms, metrics, tables, schema, lineage.
        Each section is formatted for direct injection into the LLM prompt.
        """
        concepts = routing_result.get("concepts", [])
        tables = routing_result.get("tables", [])
        expanded = routing_result.get("expanded_tables", [])

        # Separate concepts by type
        terms = [c for c in concepts if "BusinessTerm" in c.get("type", "")]
        metrics = [c for c in concepts if "Metric" in c.get("type", "")]
        rules = [c for c in concepts if "BusinessRule" in c.get("type", "")]
        dimensions = [c for c in concepts if "Dimension" in c.get("type", "")]
        biz_concepts = [c for c in concepts if "BusinessConcept" in c.get("type", "")]
        # BusinessConcept entities can be merged into terms for display
        terms = terms + biz_concepts

        # Get table details from RDF
        all_table_iris = [t["iri"] for t in tables if t.get("iri")]
        for e in expanded:
            if e.get("iri") and e["iri"] not in all_table_iris:
                all_table_iris.append(e["iri"])

        table_details = self._fetch_table_details(kb_ids, all_table_iris[:max_tables])

        # Build formatted context sections
        sections: dict[str, str] = {}

        if terms:
            sections["terms"] = self._format_terms(terms[:max_terms])
        if metrics:
            sections["metrics"] = self._format_metrics(metrics[:max_metrics])
        if rules:
            sections["rules"] = self._format_rules(rules[:max_metrics])
        if dimensions:
            sections["dimensions"] = self._format_dimensions(dimensions[:max_terms])
        if table_details:
            sections["tables"] = self._format_tables(table_details)
            sections["schema"] = self._format_schema(table_details)

        return {
            "sections": sections,
            "term_count": len(terms),
            "metric_count": len(metrics),
            "table_count": len(table_details),
        }

    def _fetch_table_details(
        self, kb_ids: list[int], table_iris: list[str],
    ) -> list[dict[str, Any]]:
        """Fetch table metadata from RDF."""
        if not table_iris:
            return []

        ns = NS
        skos = "http://www.w3.org/2004/02/skos/core#"

        iri_filters = " || ".join(f'(?table = <{iri}>)' for iri in table_iris[:20])

        graph_blocks = []
        for kb_id in kb_ids:
            g = kb_graph_iri(kb_id)
            graph_blocks.append(f"""
            GRAPH <{g}> {{
              ?table a <{ns}PhysicalTable> ;
                     <{ns}platformId> ?platformId .
              OPTIONAL {{ ?table <{skos}prefLabel> ?name . }}
              OPTIONAL {{ ?table <{ns}businessSummary> ?summary . }}
              OPTIONAL {{ ?table <{ns}sensitivityLevel> ?sensitivity . }}
            }}
            """)

        sparql = f"""
        PREFIX dl: <{ns}>
        PREFIX skos: <{skos}>
        SELECT DISTINCT ?table ?platformId ?name ?summary ?sensitivity WHERE {{
          FILTER({iri_filters})
          {{ {' UNION '.join(graph_blocks)} }}
        }}
        """

        try:
            rows = self._store.sparql_query(sparql)
        except Exception as exc:
            _logger.warning("Table detail fetch failed: %s", exc)
            return []

        return [
            {
                "iri": str(r.get("table", "")),
                "platform_id": str(r.get("platformId", "")),
                "name": str(r.get("name", "")),
                "summary": str(r.get("summary", "")),
                "sensitivity": str(r.get("sensitivity", "internal")),
            }
            for r in rows
        ]

    # ── Formatters ──────────────────────────────────────────

    @staticmethod
    def _format_terms(terms: list[dict]) -> str:
        lines = ["## 业务术语"]
        for t in terms:
            label = t.get("label", "")
            definition = t.get("definition", "")
            lines.append(f"- **{label}**: {definition}" if definition else f"- **{label}**")
        return "\n".join(lines)

    @staticmethod
    def _format_metrics(metrics: list[dict]) -> str:
        lines = ["## 指标口径"]
        for m in metrics:
            label = m.get("label", "")
            definition = m.get("definition", "")
            lines.append(f"- **{label}**: {definition}" if definition else f"- **{label}**")
        return "\n".join(lines)

    @staticmethod
    def _format_rules(rules: list[dict]) -> str:
        lines = ["## 业务规则"]
        for r in rules:
            label = r.get("label", "")
            definition = r.get("definition", "")
            lines.append(f"- **{label}**: {definition}" if definition else f"- **{label}**")
        return "\n".join(lines)

    @staticmethod
    def _format_dimensions(dimensions: list[dict]) -> str:
        lines = ["## 分析维度"]
        for d in dimensions:
            label = d.get("label", "")
            definition = d.get("definition", "")
            lines.append(f"- **{label}**: {definition}" if definition else f"- **{label}**")
        return "\n".join(lines)

    @staticmethod
    def _format_tables(tables: list[dict]) -> str:
        lines = ["## 相关数据表"]
        for t in tables:
            name = t.get("name") or t.get("platform_id", "?")
            summary = t.get("summary", "")
            lines.append(f"- **{name}**: {summary}" if summary else f"- **{name}**")
        return "\n".join(lines)

    @staticmethod
    def _format_schema(tables: list[dict]) -> str:
        lines = ["## 表结构"]
        for t in tables:
            name = t.get("name") or f"table_{t.get('platform_id', '?')}"
            summary = t.get("summary", "")
            sensitivity = t.get("sensitivity", "internal")
            lines.append(f"### {name} (sensitivity: {sensitivity})")
            if summary:
                lines.append(f"  {summary}")
        return "\n".join(lines)

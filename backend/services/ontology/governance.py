"""Five-dimension quality assessment metrics for ontology governance.

P3: Implements completeness, accuracy, consistency, timeliness, and authority
quantitative indicators aligned with W3C DQV.

Scoring:
  - 完整度 (Completeness): 有定义的实体数 / 总实体数
  - 准确度 (Accuracy): 通过 SHACL 的三元组 / 总三元组
  - 一致性 (Consistency): 无冲突定义的实体 / 多源实体数
  - 时效性 (Timeliness): 最近 90 天更新的实体 / 总实体数
  - 权威性 (Authority): 人工审批通过 / 自动采纳
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ontology import NS

_logger = logging.getLogger(__name__)


@dataclass
class QualityScores:
    completeness: float = 0.0
    accuracy: float = 0.0
    consistency: float = 0.0
    timeliness: float = 0.0
    authority: float = 0.0

    @property
    def overall(self) -> float:
        """Weighted average: completeness 25%, accuracy 30%, consistency 20%,
        timeliness 10%, authority 15%."""
        return round(
            self.completeness * 0.25
            + self.accuracy * 0.30
            + self.consistency * 0.20
            + self.timeliness * 0.10
            + self.authority * 0.15,
            4,
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "completeness": round(self.completeness, 4),
            "accuracy": round(self.accuracy, 4),
            "consistency": round(self.consistency, 4),
            "timeliness": round(self.timeliness, 4),
            "authority": round(self.authority, 4),
            "overall": self.overall,
        }


@dataclass
class QualityAssessment:
    kb_id: int
    scores: QualityScores = field(default_factory=QualityScores)
    details: dict[str, Any] = field(default_factory=dict)
    assessed_at: str = ""


class OntologyQualityAssessor:
    """Compute five-dimension quality metrics for a knowledge base.

    Usage:
        assessor = OntologyQualityAssessor(store)
        report = assessor.assess(kb_id=1, domain_id=1)
    """

    def __init__(self, store: Any):
        self._store = store

    def assess(
        self,
        kb_id: int,
        domain_id: int | None = None,
        *,
        timeliness_window_days: int = 90,
    ) -> QualityAssessment:
        """Run full five-dimension quality assessment.

        Args:
            kb_id: Knowledge base ID.
            domain_id: Optional domain scope.
            timeliness_window_days: Days window for timeliness check.

        Returns:
            QualityAssessment with scores and detailed breakdowns.
        """
        scores = QualityScores()
        details: dict[str, Any] = {}
        now = datetime.now(timezone.utc)

        # Collect entity stats
        entity_stats = self._collect_entity_stats(kb_id, domain_id)
        details["entity_stats"] = entity_stats

        triple_stats = self._collect_triple_stats(kb_id)
        details["triple_stats"] = triple_stats

        # 1. Completeness: entities with definitions / total entities
        total = entity_stats.get("total", 0)
        with_def = entity_stats.get("with_definition", 0)
        scores.completeness = with_def / total if total > 0 else 0.0
        details["completeness"] = {
            "total_entities": total,
            "with_definition": with_def,
            "without_definition": total - with_def,
        }

        # 2. Accuracy: SHACL-passed triples / total triples
        total_triples = triple_stats.get("total", 0)
        passed_triples = triple_stats.get("shacl_passed", 0)
        scores.accuracy = passed_triples / total_triples if total_triples > 0 else 0.0
        details["accuracy"] = {
            "total_triples": total_triples,
            "shacl_passed": passed_triples,
            "shacl_failed": total_triples - passed_triples,
        }

        # 3. Consistency: entities without conflicts / multi-source entities
        multi_source = entity_stats.get("multi_source", 0)
        no_conflict = entity_stats.get("no_conflict", 0)
        scores.consistency = no_conflict / multi_source if multi_source > 0 else 1.0
        details["consistency"] = {
            "multi_source_entities": multi_source,
            "no_conflict": no_conflict,
            "conflicting": multi_source - no_conflict,
        }

        # 4. Timeliness: recently updated entities / total entities
        recent = entity_stats.get("updated_recently", 0)
        scores.timeliness = recent / total if total > 0 else 0.0
        details["timeliness"] = {
            "total_entities": total,
            "updated_recently": recent,
            "window_days": timeliness_window_days,
            "stale": total - recent,
        }

        # 5. Authority: human-approved entities / total entities
        approved = entity_stats.get("approved", 0)
        scores.authority = approved / total if total > 0 else 0.0
        details["authority"] = {
            "total_entities": total,
            "approved": approved,
            "auto_accepted": total - approved,
        }

        return QualityAssessment(
            kb_id=kb_id,
            scores=scores,
            details=details,
            assessed_at=now.isoformat(),
        )

    def _collect_entity_stats(self, kb_id: int, domain_id: int | None = None) -> dict[str, int]:
        """Collect entity-level statistics from the production graph."""
        from ontology import kb_graph_iri, domain_graph_iri

        graph = kb_graph_iri(kb_id)
        dl_ns = NS
        skos_def = "http://www.w3.org/2004/02/skos/core#definition"

        try:
            from services.ontology_store import sparql_query

            # Total entities (all BusinessConcept + DataAsset instances)
            total_query = f"""
            PREFIX dl: <{dl_ns}>
            SELECT (COUNT(?s) AS ?c) WHERE {{
              GRAPH <{graph}> {{
                {{ ?s a dl:BusinessConcept . }}
                UNION
                {{ ?s a dl:DataAsset . }}
              }}
            }}
            """
            rows = sparql_query(total_query)
            total = int(rows[0]["c"]) if rows and rows[0].get("c") else 0

            # With definition
            def_query = f"""
            PREFIX dl: <{dl_ns}>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            SELECT (COUNT(?s) AS ?c) WHERE {{
              GRAPH <{graph}> {{
                {{ ?s a dl:BusinessConcept . }}
                UNION
                {{ ?s a dl:DataAsset . }}
                ?s skos:definition ?def .
              }}
            }}
            """
            rows = sparql_query(def_query)
            with_def = int(rows[0]["c"]) if rows and rows[0].get("c") else 0

            # Multi-source entities (entities with multiple provenance)
            multi_query = f"""
            PREFIX dl: <{dl_ns}>
            SELECT (COUNT(DISTINCT ?s) AS ?c) WHERE {{
              GRAPH <{graph}> {{
                ?s dl:groundedBy ?chunk1, ?chunk2 .
                FILTER(?chunk1 != ?chunk2)
              }}
            }}
            """
            rows = sparql_query(multi_query)
            multi_source = int(rows[0]["c"]) if rows and rows[0].get("c") else 0

            # Approved entities
            approved_query = f"""
            PREFIX dl: <{dl_ns}>
            SELECT (COUNT(?s) AS ?c) WHERE {{
              GRAPH <{graph}> {{
                {{ ?s a dl:BusinessConcept . }}
                UNION
                {{ ?s a dl:DataAsset . }}
                ?s dl:approvalStatus "approved" .
              }}
            }}
            """
            rows = sparql_query(approved_query)
            approved = int(rows[0]["c"]) if rows and rows[0].get("c") else 0

            # Recently updated (entities with lastReviewedAt within window)
            cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
            recent_query = f"""
            PREFIX dl: <{dl_ns}>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
            SELECT (COUNT(?s) AS ?c) WHERE {{
              GRAPH <{graph}> {{
                {{ ?s a dl:BusinessConcept . }}
                UNION
                {{ ?s a dl:DataAsset . }}
                ?s dl:lastReviewedAt ?date .
                FILTER(?date > "{cutoff}"^^xsd:dateTime)
              }}
            }}
            """
            rows = sparql_query(recent_query)
            recent = int(rows[0]["c"]) if rows and rows[0].get("c") else 0

            # No-conflict entities (approximation: entities without quarantine entries)
            from ontology import quarantine_graph_iri
            q_graph = quarantine_graph_iri(kb_id)
            conflict_query = f"""
            PREFIX dl: <{dl_ns}>
            SELECT (COUNT(DISTINCT ?s) AS ?c) WHERE {{
              GRAPH <{graph}> {{
                {{ ?s a dl:BusinessConcept . }}
                UNION
                {{ ?s a dl:DataAsset . }}
              }}
              GRAPH <{q_graph}> {{
                ?q a dl:QuarantinedAssertion ;
                   dl:rawTriple ?raw .
                FILTER(CONTAINS(STR(?raw), STR(?s)))
              }}
            }}
            """
            try:
                rows = sparql_query(conflict_query)
                conflict_count = int(rows[0]["c"]) if rows and rows[0].get("c") else 0
            except Exception:
                conflict_count = 0

            no_conflict = max(0, multi_source - conflict_count) if multi_source > 0 else 0

            return {
                "total": total,
                "with_definition": with_def,
                "multi_source": multi_source,
                "approved": approved,
                "updated_recently": recent,
                "no_conflict": no_conflict,
            }

        except Exception as exc:
            _logger.warning("Entity stats collection failed: %s", exc)
            return {
                "total": 0,
                "with_definition": 0,
                "multi_source": 0,
                "approved": 0,
                "updated_recently": 0,
                "no_conflict": 0,
            }

    def _collect_triple_stats(self, kb_id: int) -> dict[str, int]:
        """Collect triple-level statistics."""
        try:
            from services.ontology_rdf_browser import fetch_kb_rdf_view

            view = fetch_kb_rdf_view(kb_id)
            prod = view.get("production", {})
            total = int(prod.get("triple_count") or 0)

            report = view.get("shacl_report") or {}
            passed = int(report.get("passed") or 0)
            total_assertions = int(report.get("totalAssertions") or 0)

            if passed == 0 and report.get("conforms") is True:
                passed = total

            return {
                "total": total,
                "shacl_passed": passed,
                "shacl_total_assertions": total_assertions,
            }
        except Exception as exc:
            _logger.warning("Triple stats collection failed: %s", exc)
            return {"total": 0, "shacl_passed": 0, "shacl_total_assertions": 0}


def assess_quality(
    kb_id: int,
    *,
    store: Any | None = None,
    domain_id: int | None = None,
) -> dict[str, Any]:
    """Convenience function: run five-dimension quality assessment.

    Returns a dict with scores, details, and an overall quality grade.
    """
    if store is None:
        from services.triple_store import get_triple_store
        store = get_triple_store()

    assessor = OntologyQualityAssessor(store)
    result = assessor.assess(kb_id, domain_id)

    overall = result.scores.overall
    if overall >= 0.90:
        grade = "A"
    elif overall >= 0.75:
        grade = "B"
    elif overall >= 0.60:
        grade = "C"
    elif overall >= 0.40:
        grade = "D"
    else:
        grade = "F"

    return {
        "ok": True,
        "kb_id": kb_id,
        "domain_id": domain_id,
        "grade": grade,
        "scores": result.scores.to_dict(),
        "details": result.details,
        "assessed_at": result.assessed_at,
    }

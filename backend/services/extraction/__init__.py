"""Ontology-native extraction pipeline (Phase 2).

All extractors return list[RawTriple] — no direct PostgreSQL writes.
The orchestrator collects triples and writes through OntologyWriter,
which handles cleaning → SHACL validation → production/quarantine.
"""

from services.extraction.term_extractor import extract_term_triples
from services.extraction.metric_extractor import extract_metric_triples
from services.extraction.relation_extractor import extract_relation_triples
from services.extraction.hierarchy_builder import build_hierarchy_triples
from services.extraction.lineage_extractor import extract_lineage_triples
from services.extraction.dimension_extractor import extract_dimension_triples
from services.extraction.join_extractor import extract_join_triples
from services.extraction.rule_extractor import extract_rule_triples
from services.extraction.orchestrator import ExtractionOrchestrator, run_extraction_pipeline

__all__ = [
    "extract_term_triples",
    "extract_metric_triples",
    "extract_relation_triples",
    "build_hierarchy_triples",
    "extract_lineage_triples",
    "extract_dimension_triples",
    "extract_join_triples",
    "extract_rule_triples",
    "ExtractionOrchestrator",
    "run_extraction_pipeline",
]

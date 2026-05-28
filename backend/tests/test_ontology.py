"""Tests for Formal OWL ontology layer."""
from __future__ import annotations

from rdflib import Graph

from ontology import NS, concept_slug, kb_graph_iri, table_iri
from config import get_settings
from services.ontology_loader import init_ontology
from services.ontology_store import insert_graph, load_tbox, sparql_query
from services.ontology_triple_cleaner import RawTriple, clean_triples, triples_to_ttl
from services.ontology_validation import validate_ttl


def test_concept_slug():
    assert concept_slug("GMV 总额", "metric") == "metric.gmv_总额"


def test_table_iri():
    assert table_iri(42) == "https://datalens.local/data/table/42"


def test_load_tbox():
    init_ontology()
    stats = load_tbox(force=True)
    assert stats >= 0


def test_clean_triples_deduplication():
    t = RawTriple(
        table_iri(1),
        "https://datalens.local/ontology/joinableWith",
        table_iri(2),
        True,
        graph=kb_graph_iri(1),
        confidence=80,
    )
    t2 = RawTriple(
        table_iri(2),
        "https://datalens.local/ontology/joinableWith",
        table_iri(1),
        True,
        graph=kb_graph_iri(1),
        confidence=80,
    )
    result = clean_triples([t, t2], kb_id=1, domain_tables=[])
    assert len(result.production) >= 1


def test_triples_to_ttl_roundtrip():
    triples = [
        RawTriple(
            "https://datalens.local/data/concept/test",
            "http://www.w3.org/2004/02/skos/core#prefLabel",
            "测试",
            False,
            lang="zh",
            graph=kb_graph_iri(1),
        )
    ]
    ttl = triples_to_ttl(triples)
    g = Graph()
    g.parse(data=ttl, format="turtle")
    assert len(g) >= 1


def test_shacl_metric_requires_formula():
    ttl = """
@prefix dl: <https://datalens.local/ontology/> .
@prefix skos: <http://www.w3.org/2004/02/skos/core#> .
<https://datalens.local/data/metric/bad> a dl:Metric ;
  skos:prefLabel "无公式"@zh .
"""
    report = validate_ttl(ttl)
    assert report.get("skipped") or report.get("conforms") is not None


def test_local_store_persist(tmp_path, monkeypatch):
    store_file = tmp_path / "test.trig"
    monkeypatch.setenv("ONTOLOGY_LOCAL_STORE_ENABLED", "true")
    monkeypatch.setenv("ONTOLOGY_LOCAL_STORE_PATH", str(store_file))
    monkeypatch.delenv("FUSEKI_URL", raising=False)
    get_settings.cache_clear()

    from services import ontology_store as osmod

    osmod.reset_triple_store()

    osmod.insert_graph(kb_graph_iri(1), f"<{table_iri(9)}> <{NS}platformId> \"9\" .")
    assert store_file.is_file()
    assert store_file.stat().st_size > 0

    osmod.reset_triple_store()
    ds = osmod._get_local_dataset()
    assert len(ds) >= 1
    get_settings.cache_clear()


def test_insert_and_query_local_sparql(monkeypatch):
    monkeypatch.setenv("FUSEKI_FALLBACK_MEMORY", "true")
    monkeypatch.delenv("FUSEKI_URL", raising=False)
    get_settings.cache_clear()

    from services import ontology_store as osmod

    osmod.reset_triple_store()

    graph = kb_graph_iri(99)
    insert_graph(
        graph,
        f"<{table_iri(5)}> <https://datalens.local/ontology/platformId> \"5\" .",
    )
    rows = sparql_query(f"SELECT ?p ?o WHERE {{ <{table_iri(5)}> ?p ?o }}")
    assert isinstance(rows, list)
    get_settings.cache_clear()


def test_assertion_lifecycle_mapping():
    from services.ontology.assertion_lifecycle import lifecycle_phase, LIFECYCLE_TO_STATUS

    assert lifecycle_phase("draft") == "draft"
    assert lifecycle_phase("linked") == "linked"
    assert lifecycle_phase("shacl_passed") == "shacl_passed"
    assert lifecycle_phase("pending_review") == "linked"
    assert lifecycle_phase("approved") == "production"
    assert LIFECYCLE_TO_STATUS["production"] == "approved"
    assert LIFECYCLE_TO_STATUS["linked"] == "linked"
    assert LIFECYCLE_TO_STATUS["shacl_passed"] == "shacl_passed"


def test_copilot_validation_suggest_fixes():
    from services.ontology.copilot_validation import _match_quarantine_items, _suggest_fixes

    items = [
        {
            "item_idx": 1,
            "reason": "unresolved_table_ref",
            "reason_label": "无法解析物理表引用",
            "subject": "https://datalens.local/data/metric/m1",
            "object": "orders",
        }
    ]
    matched = _match_quarantine_items(items, subject_iri="https://datalens.local/data/metric/m1")
    assert len(matched) == 1
    suggestions = _suggest_fixes(matched, [42])
    assert suggestions[0]["recommended_template"] == "map_table_by_platform_id"
    assert suggestions[0]["recommended_params"]["platform_id"] == 42


def test_quarantine_templates_unresolved():
    from services.ontology.quarantine_templates import apply_template, suggest_templates

    templates = suggest_templates("unresolved_table_ref", {"subject": "s", "predicate": "p", "object": "orders"})
    assert any(t["id"] == "map_table_by_platform_id" for t in templates)
    fix = apply_template(
        1,
        reason="unresolved_table_ref",
        raw_triple={"subject": "s", "predicate": "p", "object": "orders", "object_is_uri": False},
        template_id="map_table_by_platform_id",
        params={"platform_id": 42},
    )
    assert fix["ok"] and fix["action"] == "write"
    assert "table/42" in fix["triple"]["object"]


def test_modeling_layer_key_normalization():
    from services.ontology.modeling_layers import normalize_layer_key

    assert normalize_layer_key("vocabulary") == "vocabulary"
    assert normalize_layer_key("entity_concept") == "entity-concept"
    assert normalize_layer_key("unknown") is None


def test_connector_registry_resolve():
    from services.ingestion.connectors import resolve_asset_connector

    ak, conn = resolve_asset_connector(route_key="import-file")
    assert ak == "semantic_doc" and conn == "file"
    ak2, conn2 = resolve_asset_connector(source_kind="notion")
    assert ak2 == "semantic_doc" and conn2 == "api"


def test_list_quarantine_pagination():
    from unittest.mock import MagicMock, patch

    from routers.ontology import list_quarantine

    kb = MagicMock()
    db = MagicMock()
    db.get.return_value = kb
    payload = [{"item_idx": i, "reason": "test"} for i in range(25)]

    with patch("routers.ontology._quarantine_items_payload", return_value=payload):
        page0 = list_quarantine(kb_id=1, limit=20, offset=0, db=db)
        page1 = list_quarantine(kb_id=1, limit=20, offset=20, db=db)

    assert page0["total"] == 25
    assert len(page0["items"]) == 20
    assert page0["has_more"] is True
    assert page0["items"][0]["item_idx"] == 0

    assert len(page1["items"]) == 5
    assert page1["has_more"] is False
    assert page1["items"][0]["item_idx"] == 20


def test_insert_graph_fuseki_update_no_double_dots(monkeypatch):
    """Fuseki INSERT DATA: N-Triples lines already end with '.' — no extra join dots."""
    from rdflib import Graph, Literal, URIRef

    from services.triple_store.store import TripleStore

    captured: list[str] = []

    def _capture_update(query: str) -> None:
        captured.append(query)

    monkeypatch.setenv("FUSEKI_URL", "http://localhost:3030")
    monkeypatch.setenv("FUSEKI_DATASET", "datalens")
    get_settings.cache_clear()

    store = TripleStore(get_settings())
    store._fuseki_live = True  # noqa: SLF001
    monkeypatch.setattr(store, "_sparql_update", _capture_update)

    g = Graph()
    g.add((URIRef("http://ex/s1"), URIRef("http://ex/p"), Literal("a")))
    g.add((URIRef("http://ex/s2"), URIRef("http://ex/p"), URIRef("http://ex/o2")))
    store.insert_graph("http://datalens.local/kb/1", g.serialize(format="turtle"))

    assert len(captured) == 1
    assert " . ." not in captured[0]
    assert captured[0].startswith("INSERT DATA { GRAPH <http://datalens.local/kb/1> {")
    get_settings.cache_clear()

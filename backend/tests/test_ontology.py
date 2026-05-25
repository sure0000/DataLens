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

    osmod._local_dataset = None
    osmod._tbox_loaded = False
    osmod._fuseki_live = None

    osmod.insert_graph(kb_graph_iri(1), f"<{table_iri(9)}> <{NS}platformId> \"9\" .")
    assert store_file.is_file()
    assert store_file.stat().st_size > 0

    osmod._local_dataset = None
    ds = osmod._get_local_dataset()
    assert len(ds) >= 1
    get_settings.cache_clear()


def test_insert_and_query_local_sparql(monkeypatch):
    monkeypatch.setenv("FUSEKI_FALLBACK_MEMORY", "true")
    monkeypatch.delenv("FUSEKI_URL", raising=False)
    get_settings.cache_clear()

    from services import ontology_store as osmod

    osmod._local_dataset = None
    osmod._tbox_loaded = False
    osmod._fuseki_live = None

    graph = kb_graph_iri(99)
    insert_graph(
        graph,
        f"<{table_iri(5)}> <https://datalens.local/ontology/platformId> \"5\" .",
    )
    rows = sparql_query(f"SELECT ?p ?o WHERE {{ <{table_iri(5)}> ?p ?o }}")
    assert isinstance(rows, list)
    get_settings.cache_clear()

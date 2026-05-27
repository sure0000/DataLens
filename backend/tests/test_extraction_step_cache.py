"""Step cache round-trip tests."""

from services.extraction.step_cache import save_step_triples, load_step_triples, step_cache_exists
from services.ontology_triple_cleaner import RawTriple


def test_step_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    triples = [
        RawTriple("http://ex/s", "http://ex/p", "obj", False, graph="http://ex/g"),
    ]
    save_step_triples(1, 99, "term_extraction", triples)
    assert step_cache_exists(1, 99, "term_extraction")
    loaded = load_step_triples(1, 99, "term_extraction")
    assert len(loaded) == 1
    assert loaded[0].subject == "http://ex/s"

from services.ingestion.registry import _dedupe_key, _dedupe_packages


def test_git_dedupe_key_ignores_asset_kind():
    base = {
        "kb_id": 8,
        "connector": "git",
        "source_ref": {
            "git_source_id": 3,
            "owner": "org",
            "repo": "datalesn-test1",
            "branch": "main",
        },
    }
    processing = {**base, "asset_kind": "processing_code", "title": "datalesn-test1"}
    lineage = {**base, "asset_kind": "relation_lineage", "title": "datalesn-test1"}
    assert _dedupe_key(processing) == _dedupe_key(lineage)


def test_dedupe_packages_keeps_best_git_row():
    packages = [
        {
            "id": "ep-15",
            "db_id": 15,
            "kb_id": 8,
            "connector": "git",
            "asset_kind": "relation_lineage",
            "title": "datalesn-test1",
            "processing_state": "registered",
            "persistent": True,
            "source_ref": {"git_source_id": 3, "owner": "org", "repo": "datalesn-test1", "branch": "main"},
        },
        {
            "id": "ep-14",
            "db_id": 14,
            "kb_id": 8,
            "connector": "git",
            "asset_kind": "processing_code",
            "title": "datalesn-test1",
            "processing_state": "ready_for_extraction",
            "persistent": True,
            "source_ref": {"git_source_id": 3, "owner": "org", "repo": "datalesn-test1", "branch": "main"},
        },
    ]
    deduped = _dedupe_packages(packages)
    assert len(deduped) == 1
    assert deduped[0]["db_id"] == 14

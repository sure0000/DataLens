"""枚举解析与列画像中的 enum 标注。"""

from services.profiler import merge_enum_semantic_output, parse_mysql_discrete_type_literals, profile_column


def test_parse_mysql_enum() -> None:
    r = parse_mysql_discrete_type_literals("enum('ORDER_PAY','SIGN_IN','EXPIRE')")
    assert r is not None
    kind, vals = r
    assert kind == "mysql_enum"
    assert vals == ["ORDER_PAY", "SIGN_IN", "EXPIRE"]


def test_parse_mysql_set() -> None:
    r = parse_mysql_discrete_type_literals("set('a','b')")
    assert r is not None
    assert r[0] == "mysql_set"
    assert r[1] == ["a", "b"]


def test_merge_enum_prefixes_desc() -> None:
    prof = {"quality_metrics": {"enum": {"kind": "mysql_enum", "values": ["X", "Y"]}}}
    sem = merge_enum_semantic_output({"desc": "说明", "type": "dimension"}, prof)
    assert sem["type"] == "enum"
    assert "【MySQL ENUM】" in sem["desc"]
    assert "X" in sem["desc"] and "Y" in sem["desc"]


def test_profile_low_cardinality_varchar() -> None:
    rows = [
        {"st": "a"},
        {"st": "b"},
        {"st": "a"},
        {"st": "c"},
    ]
    p = profile_column(rows, "st", total_count=100, data_type="varchar(16)", column_type="varchar(16)")
    em = (p.get("quality_metrics") or {}).get("enum")
    assert isinstance(em, dict)
    assert em.get("kind") == "low_cardinality_observed"
    assert set(em.get("values") or []) == {"a", "b", "c"}

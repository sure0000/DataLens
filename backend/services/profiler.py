import re
from collections import Counter
from datetime import datetime, timezone
from statistics import mean
from typing import Any

# 样本内去重后取值个数不超过该阈值时，对字符串列标注为「样本观测到的离散取值」
_LOW_CARD_ENUM_MAX_DISTINCT = 36
_LOW_CARD_ENUM_MAX_VALUE_LEN = 64


def _is_numeric_type(data_type: str | None) -> bool:
    if not data_type:
        return False
    normalized = data_type.lower()
    return any(token in normalized for token in ("int", "numeric", "decimal", "float", "double", "real"))


def _is_datetime_type(data_type: str | None) -> bool:
    if not data_type:
        return False
    normalized = data_type.lower().strip()
    # MySQL 的 enum / set 类型名中含子串 "time"，不能按子串误判为时间类型
    if normalized in ("enum", "set"):
        return False
    return "date" in normalized or "time" in normalized


def parse_mysql_discrete_type_literals(column_type: str | None) -> tuple[str, list[str]] | None:
    """解析 MySQL / MariaDB information_schema.COLUMNS.COLUMN_TYPE 中的 enum(...) / set(...)，返回 (mysql_enum|mysql_set, 取值列表)。"""
    if not column_type:
        return None
    ct = column_type.strip()
    lower = ct.lower()
    if lower.startswith("enum(") and ct.rstrip().endswith(")"):
        kind = "mysql_enum"
    elif lower.startswith("set(") and ct.rstrip().endswith(")"):
        kind = "mysql_set"
    else:
        return None
    inner = ct[ct.index("(") + 1 : ct.rindex(")")]
    vals = re.findall(r"'((?:[^'\\\\]|\\\\.)*)'", inner)
    if not vals:
        return None
    return kind, [v.replace(r"\'", "'").replace(r"\\", "\\") for v in vals]


def _text_like_type(data_type: str | None) -> bool:
    if not data_type:
        return False
    dt = data_type.lower()
    if dt in ("enum", "set"):
        return True
    return any(x in dt for x in ("char", "text", "varchar"))


def _low_cardinality_enum_from_sample(
    column_name: str, data_type: str | None, non_null_values: list[Any], distinct_count: int, max_len_seen: int
) -> dict[str, Any] | None:
    if _is_numeric_type(data_type) or _is_datetime_type(data_type):
        return None
    if not _text_like_type(data_type):
        return None
    if distinct_count < 2 or distinct_count > _LOW_CARD_ENUM_MAX_DISTINCT:
        return None
    if max_len_seen > 80:
        return None
    cn = column_name.lower()
    if cn in ("remark", "description", "detail", "content", "comment", "note", "payload", "extra", "metadata"):
        return None
    if cn.endswith("_id") and distinct_count > 12:
        return None

    ordered: list[str] = []
    seen: set[str] = set()
    for v in non_null_values:
        s = str(v).strip()
        if not s or s in seen:
            continue
        if len(s) > _LOW_CARD_ENUM_MAX_VALUE_LEN:
            return None
        seen.add(s)
        ordered.append(s)
    if len(ordered) < 2:
        return None
    return {
        "kind": "low_cardinality_observed",
        "values": sorted(ordered, key=str),
        "note": "取值来自分析样本的去重结果，可能与全表不完全一致",
    }


def merge_enum_semantic_output(semantic: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """将 profiler 产出的枚举/离散取值合并进 LLM 列语义（描述前缀 + semantic_type）。"""
    out = dict(semantic)
    qm = profile.get("quality_metrics")
    if not isinstance(qm, dict):
        return out
    em = qm.get("enum")
    if not isinstance(em, dict):
        return out
    vals = em.get("values")
    if not isinstance(vals, list) or not vals:
        return out
    kind = str(em.get("kind") or "")
    note = str(em.get("note") or "").strip()
    parts = [str(v).strip() for v in vals if str(v).strip()]
    joined = "、".join(parts)
    if kind == "mysql_enum":
        tag = "MySQL ENUM"
        out["type"] = "enum"
    elif kind == "mysql_set":
        tag = "MySQL SET（可多选）"
        out["type"] = "enum"
    else:
        tag = "离散维度（样本观测）"
        out["type"] = "enum"
    prefix = f"【{tag}】可取值为：{joined}。"
    if note:
        prefix += f"（{note}）"
    desc = (out.get("desc") or "").strip()
    if "可取值为：" not in desc[:120]:
        out["desc"] = prefix + desc
    return out


def profile_column(
    sample_data: list[dict[str, Any]],
    column_name: str,
    total_count: int,
    data_type: str | None = None,
    column_type: str | None = None,
) -> dict[str, Any]:
    values = [row.get(column_name) for row in sample_data]
    non_null_values = [v for v in values if v is not None]
    null_count = len(values) - len(non_null_values)
    non_null_count = len(non_null_values)
    top = Counter(str(v) for v in non_null_values).most_common(10)
    distinct_count = len(set(str(v) for v in non_null_values))
    duplicate_ratio = (1 - distinct_count / non_null_count) if non_null_count else 0.0
    top1_ratio = (top[0][1] / non_null_count) if top and non_null_count else 0.0
    result: dict[str, Any] = {
        "null_ratio": round((null_count / total_count), 6) if total_count else 0.0,
        "distinct_count": distinct_count,
        "sample_values": [str(v) for v in non_null_values[:5]],
        "top_values": [{"value": k, "count": c} for k, c in top],
    }

    quality_metrics: dict[str, Any] = {
        "non_null_count": non_null_count,
        "null_count": null_count,
        "distinct_ratio": round((distinct_count / non_null_count), 6) if non_null_count else 0.0,
        "duplicate_ratio": round(duplicate_ratio, 6),
        "top1_ratio": round(top1_ratio, 6),
        "completeness_score": round(1 - result["null_ratio"], 6),
        "uniqueness_score": round(1 - duplicate_ratio, 6),
    }

    if _is_numeric_type(data_type):
        numeric: list[float] = []
        parse_failed = 0
        for v in non_null_values:
            try:
                numeric.append(float(v))
            except (TypeError, ValueError):
                parse_failed += 1
        if numeric:
            result["min"] = min(numeric)
            result["max"] = max(numeric)
            result["avg"] = mean(numeric)
            quality_metrics["distribution"] = {
                "min": result["min"],
                "max": result["max"],
                "avg": result["avg"],
            }
        quality_metrics["type_valid_ratio"] = round((1 - parse_failed / non_null_count), 6) if non_null_count else 1.0
    elif _is_datetime_type(data_type):
        parsed = 0
        future_count = 0
        now = datetime.now(timezone.utc)
        for v in non_null_values:
            dt = None
            if isinstance(v, datetime):
                dt = v
            elif isinstance(v, str):
                candidate = v.replace("Z", "+00:00")
                try:
                    dt = datetime.fromisoformat(candidate)
                except ValueError:
                    dt = None
            if dt is None:
                continue
            parsed += 1
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt > now:
                future_count += 1
        quality_metrics["type_valid_ratio"] = round((parsed / non_null_count), 6) if non_null_count else 1.0
        quality_metrics["future_time_ratio"] = round((future_count / non_null_count), 6) if non_null_count else 0.0
    else:
        text_values = [str(v) for v in non_null_values]
        format_issues = sum(1 for v in text_values if v != v.strip())
        max_length = max((len(v) for v in text_values), default=0)
        quality_metrics["format_issue_ratio"] = round((format_issues / non_null_count), 6) if non_null_count else 0.0
        quality_metrics["max_length"] = max_length

    risk_score = 0
    if result["null_ratio"] > 0.2:
        risk_score += 2
    elif result["null_ratio"] > 0.05:
        risk_score += 1
    if duplicate_ratio > 0.3:
        risk_score += 1
    if top1_ratio > 0.9:
        risk_score += 1
    if quality_metrics.get("type_valid_ratio", 1.0) < 0.95:
        risk_score += 2
    quality_metrics["risk_level"] = "high" if risk_score >= 3 else "medium" if risk_score >= 1 else "low"

    parsed = parse_mysql_discrete_type_literals(column_type)
    if parsed:
        kind, literals = parsed
        quality_metrics["enum"] = {"kind": kind, "values": literals}
    elif not _is_numeric_type(data_type) and not _is_datetime_type(data_type):
        max_len_seen = int(quality_metrics.get("max_length") or 0) if isinstance(quality_metrics, dict) else 0
        low = _low_cardinality_enum_from_sample(column_name, data_type, non_null_values, distinct_count, max_len_seen)
        if low:
            quality_metrics["enum"] = low

    result["quality_metrics"] = quality_metrics
    return result

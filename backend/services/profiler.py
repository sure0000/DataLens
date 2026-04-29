from collections import Counter
from datetime import datetime, timezone
from statistics import mean
from typing import Any


def _is_numeric_type(data_type: str | None) -> bool:
    if not data_type:
        return False
    normalized = data_type.lower()
    return any(token in normalized for token in ("int", "numeric", "decimal", "float", "double", "real"))


def _is_datetime_type(data_type: str | None) -> bool:
    if not data_type:
        return False
    normalized = data_type.lower()
    return "date" in normalized or "time" in normalized


def profile_column(sample_data: list[dict[str, Any]], column_name: str, total_count: int, data_type: str | None = None) -> dict[str, Any]:
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

    result["quality_metrics"] = quality_metrics
    return result

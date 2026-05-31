"""ChatBI NLP 预处理助手：时间解析、维度值提取、计算模式检测。

在意图识别之后、SQL 生成之前，对用户问题做轻量级结构化信息提取，
将提取到的提示（时间范围、维度过滤值、计算模式）注入 SQL 生成上下文，
减少 LLM 猜测导致的不确定性。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# 常用中文姓氏（Top 100+），用于识别人名类维度值
# ---------------------------------------------------------------------------
_COMMON_SURNAMES: set[str] = {
    "王", "李", "张", "刘", "陈", "杨", "黄", "赵", "周", "吴",
    "徐", "孙", "马", "胡", "朱", "郭", "何", "罗", "高", "林",
    "郑", "梁", "谢", "唐", "许", "冯", "宋", "韩", "邓", "彭",
    "曹", "曾", "田", "萧", "潘", "袁", "蔡", "蒋", "余", "于",
    "杜", "叶", "程", "魏", "苏", "吕", "丁", "任", "卢", "姚",
    "钟", "姜", "崔", "谭", "陆", "范", "汪", "廖", "石", "金",
    "韦", "贾", "夏", "付", "方", "白", "邹", "孟", "熊", "秦",
    "邱", "江", "尹", "薛", "闫", "段", "雷", "侯", "龙", "史",
    "陶", "黎", "贺", "顾", "毛", "郝", "龚", "邵", "万", "钱",
    "严", "覃", "武", "戴", "莫", "孔", "向", "汤", "温", "康",
    "施", "沈", "洪", "章", "阮", "颜", "樊", "齐", "易", "乔",
    "文", "严", "关", "纪", "包", "鲁", "董", "成", "倪", "崔",
}

# 非维度值的常见业务关键词，避免误提取
_NON_DIMENSION_KEYWORDS: set[str] = {
    "用电", "售电", "电量", "电费", "销售", "金额", "业绩", "利润",
    "环比", "同比", "对比", "比较", "变化", "增长", "下降", "增减",
    "多少", "怎样", "如何", "查询", "统计", "分析", "汇总", "合计",
    "平均", "最大", "最小", "排名", "趋势", "占比", "比例", "份额",
    "最近", "本月", "上月", "本年", "去年", "今天", "昨天", "本周",
    "上周", "这个", "哪个", "哪些", "什么", "请问", "帮我", "我想",
    "显示", "列出", "找出", "筛选", "导出",
}


# ---------------------------------------------------------------------------
# 时间表达式解析
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now()


def _year_from_question(text: str, default: int) -> int:
    """从问题中显式提取年份，若未提及则返回默认值。"""
    m = re.search(r"(\d{4})\s*年", text)
    if m:
        return int(m.group(1))
    # "去年" → 去年
    if "去年" in text:
        return default - 1
    if "明年" in text:
        return default + 1
    return default


def parse_chinese_time_expressions(text: str) -> dict[str, Any]:
    """从用户问题中解析中文时间表达，返回结构化时间提示。

    支持的表达：
    - 绝对月份：4月、5月、12月份
    - 绝对年份+月份：2025年4月
    - 相对日期：最近7天、近30天、近3个月
    - 命名时间：本月、上月、本周、上周、今年、去年、本季度
    - 完整日期：2025-04-01、2025.04.01

    Returns:
        dict with keys:
        - time_values: list[str] — 具体的时间过滤值（如 "2025-04"）
        - time_hint: str — 供 LLM 使用的自然语言时间提示
        - time_range_start / time_range_end: str | None — 区间查询的起止
        - is_comparison: bool — 是否为两个时间点的对比查询
    """
    text = (text or "").strip()
    now = _now()
    result: dict[str, Any] = {
        "time_values": [],
        "time_hint": "",
        "time_range_start": None,
        "time_range_end": None,
        "is_comparison": False,
    }

    if not text:
        return result

    year = _year_from_question(text, now.year)

    # ---- 绝对月份：4月、5月、12月份 ----
    month_matches = re.findall(r"(\d{1,2})\s*月(?:份)?", text)
    if month_matches:
        months = sorted({int(m) for m in month_matches if 1 <= int(m) <= 12})
        time_values = [f"{year}-{m:02d}" for m in months]
        result["time_values"] = time_values

        if len(months) == 1:
            m = months[0]
            result["time_hint"] = (
                f"时间范围：{year}年{m}月（假设为当年，若需跨年请明确说明年份）。"
                f"SQL 中请将月份过滤条件写为明确的日期范围（如 month_column = '{year}-{m:02d}' 或 BETWEEN '{year}-{m:02d}-01' AND '{year}-{m:02d}-{_days_in_month(year, m):02d}'）"
            )
        elif len(months) == 2 and abs(months[0] - months[1]) == 1:
            result["is_comparison"] = True
            result["time_hint"] = (
                f"时间范围：{year}年{months[0]}月 和 {year}年{months[1]}月（连续两月对比）。"
                f"SQL 中请用自连接或 CASE WHEN 分别取出 {year}-{months[0]:02d} 和 {year}-{months[1]:02d} 的数据进行对比。"
            )
        else:
            result["time_hint"] = (
                f"时间范围：{'、'.join(f'{year}年{m}月' for m in months)}。"
                f"SQL 中请用 IN ({', '.join(repr(v) for v in time_values)}) 或 BETWEEN 过滤这些月份。"
            )

    # ---- 绝对年份+月份：2025年4月 ----
    ym_matches = re.findall(r"(\d{4})\s*年\s*(\d{1,2})\s*月", text)
    if ym_matches:
        ym_values = [f"{int(y)}-{int(m):02d}" for y, m in ym_matches if 1 <= int(m) <= 12]
        if ym_values:
            result["time_values"] = ym_values
            if len(ym_values) == 1:
                result["time_hint"] = f"时间范围：{ym_values[0]}（用户已明确年份+月份）。"
            elif len(ym_values) == 2:
                result["is_comparison"] = True
                result["time_hint"] = (
                    f"时间范围：{ym_values[0]} 和 {ym_values[1]}（两月对比）。"
                    f"SQL 中推荐使用自连接分别取两月数据后计算差值。"
                )
            else:
                result["time_hint"] = f"时间范围：{'、'.join(ym_values)}。"

    # ---- 相对日期：最近7天、近30天 ----
    rel_days = re.search(r"(?:最近|近|过去)\s*(\d+)\s*天", text)
    if rel_days:
        days = int(rel_days.group(1))
        result["time_range_end"] = now.strftime("%Y-%m-%d")
        result["time_range_start"] = _format_date_offset(now, days=-days)
        result["time_hint"] = (
            f"时间范围：最近{days}天（{result['time_range_start']} 至 {result['time_range_end']}）。"
            f"SQL 中请用 date_column >= '{result['time_range_start']}' AND date_column <= '{result['time_range_end']}'"
        )

    rel_months = re.search(r"(?:最近|近|过去)\s*(\d+)\s*个?\s*月", text)
    if rel_months:
        months = int(rel_months.group(1))
        end_dt = now
        start_dt = _add_months(now, -months)
        result["time_range_start"] = start_dt.strftime("%Y-%m-01")
        result["time_range_end"] = _month_end(end_dt)
        result["time_hint"] = (
            f"时间范围：最近{months}个月（{result['time_range_start']} 至 {result['time_range_end']}）。"
        )

    # ---- 命名时间 ----
    _named_patterns = {
        "本月": lambda dt: (dt.strftime("%Y-%m-01"), _month_end(dt), f"本月（{dt.year}年{dt.month}月）"),
        "上月": lambda dt: (
            _add_months(dt, -1).strftime("%Y-%m-01"),
            _month_end(_add_months(dt, -1)),
            f"上月（{_add_months(dt, -1).year}年{_add_months(dt, -1).month}月）",
        ),
        "本周": lambda dt: (
            _week_start(dt),
            _week_end(dt),
            f"本周（{_week_start(dt)} 至 {_week_end(dt)}）",
        ),
        "上周": lambda dt: (
            _week_start(dt, weeks=-1),
            _week_end(dt, weeks=-1),
            f"上周（{_week_start(dt, weeks=-1)} 至 {_week_end(dt, weeks=-1)}）",
        ),
        "今年": lambda dt: (f"{dt.year}-01-01", f"{dt.year}-12-31", f"今年（{dt.year}年）"),
        "去年": lambda dt: (f"{dt.year - 1}-01-01", f"{dt.year - 1}-12-31", f"去年（{dt.year - 1}年）"),
    }

    for name, fn in _named_patterns.items():
        if name in text and not result["time_range_start"]:
            start, end, desc = fn(now)
            result["time_range_start"] = start
            result["time_range_end"] = end
            result["time_hint"] = (
                f"时间范围：{desc}。"
                f"SQL 中请用 date_column >= '{start}' AND date_column <= '{end}'"
            )

    return result


# ---- 日期工具函数 ----

def _days_in_month(year: int, month: int) -> int:
    import calendar
    return calendar.monthrange(year, month)[1]


def _month_end(dt: datetime) -> str:
    return dt.strftime("%Y-%m-") + f"{_days_in_month(dt.year, dt.month):02d}"


def _add_months(dt: datetime, months: int) -> datetime:
    """跨月加减，保持日合理（若目标月不存在同一天则取月末）。"""
    import calendar
    new_month = dt.month - 1 + months  # 0-based
    new_year = dt.year + new_month // 12
    new_month = new_month % 12 + 1
    max_day = calendar.monthrange(new_year, new_month)[1]
    new_day = min(dt.day, max_day)
    return dt.replace(year=new_year, month=new_month, day=new_day)


def _format_date_offset(dt: datetime, days: int) -> str:
    from datetime import timedelta
    return (dt + timedelta(days=days)).strftime("%Y-%m-%d")


def _week_start(dt: datetime, weeks: int = 0) -> str:
    from datetime import timedelta
    d = dt + timedelta(weeks=weeks)
    return (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")


def _week_end(dt: datetime, weeks: int = 0) -> str:
    from datetime import timedelta
    d = dt + timedelta(weeks=weeks)
    return (d - timedelta(days=d.weekday()) + timedelta(days=6)).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 维度值提取
# ---------------------------------------------------------------------------

def extract_dimension_values(text: str) -> dict[str, Any]:
    """从用户问题中提取潜在的维度过滤值（人名、地名、ID 等）。

    策略：
    1. 中文人名检测：常见姓氏 + 1~3 个中文字符，且不是业务关键词。
    2. 地名检测：以省/市/区/县/镇/村结尾的中文词。
    3. ID 类：纯数字/字母-数字组合（如订单号、设备号）。
    4. 引号包裹的字符串。

    Returns:
        dict with:
        - dimension_values: list[dict] — 每个元素含 value/text/type
        - dimension_hint: str — 供 LLM 使用的维度过滤提示
    """
    text = (text or "").strip()
    result: dict[str, Any] = {
        "dimension_values": [],
        "dimension_hint": "",
    }

    if not text:
        return result

    values: list[dict[str, str]] = []

    # ---- 策略 1：中文人名检测 ----
    # 匹配 2-4 个连续中文字符的候选词
    zh_words = re.findall(r"[一-鿿]{2,4}", text)
    for word in zh_words:
        # 首字是常见姓氏
        if word[0] not in _COMMON_SURNAMES:
            continue
        # 不是业务关键词
        if word in _NON_DIMENSION_KEYWORDS:
            continue
        # 不完全由关键词子串构成
        if any(kw in word for kw in ["环比", "同比", "用电", "售电", "销售", "查询", "统计"]):
            continue
        # 找到疑似人名
        values.append({
            "value": word,
            "text": word,
            "type": "person_name",
        })

    # ---- 策略 2：地名检测 ----
    place_suffixes = r"(?:省|市|区|县|镇|村|街道|路|园区|基地|工厂|门店|分公司)$"
    for word in zh_words:
        if re.search(place_suffixes, word):
            if word not in _NON_DIMENSION_KEYWORDS:
                values.append({
                    "value": word,
                    "text": word,
                    "type": "place",
                })

    # ---- 策略 3：ID 类（字母+数字组合或纯数字长串）----
    id_pattern = re.findall(r"\b([A-Za-z]{1,4}[-_]?\d{3,})\b|\b(\d{6,})\b", text)
    for groups in id_pattern:
        val = groups[0] or groups[1]
        if val:
            values.append({
                "value": val,
                "text": val,
                "type": "identifier",
            })

    # ---- 策略 4：引号包裹的值 ----
    quoted = re.findall(r"['\"「」『』]([^'\"「」『』]{2,20})['\"「」『』]", text)
    for qv in quoted:
        values.append({
            "value": qv,
            "text": qv,
            "type": "quoted_value",
        })

    # ---- 去重 ----
    seen: set[str] = set()
    unique_values: list[dict[str, str]] = []
    for v in values:
        if v["value"] not in seen:
            seen.add(v["value"])
            unique_values.append(v)

    result["dimension_values"] = unique_values

    if unique_values:
        parts: list[str] = []
        for v in unique_values:
            type_label = {
                "person_name": "人名",
                "place": "地名",
                "identifier": "ID/编码",
                "quoted_value": "指定值",
            }.get(v.get("type", ""), "维度值")
            parts.append(f"{type_label}「{v['text']}」")
        result["dimension_hint"] = (
            f"问题中检测到维度过滤值：{'、'.join(parts)}。"
            f"请在 SQL 的 WHERE 子句中将这些值用作对应名称/编码列的过滤条件。"
            f"例如，若表中存在客户名称/用户姓名/户名等列，应将对应人名值作为精确匹配过滤条件。"
        )

    return result


# ---------------------------------------------------------------------------
# 计算模式检测
# ---------------------------------------------------------------------------

# 计算模式关键词库
_CALCULATION_PATTERNS: dict[str, dict[str, list[str]]] = {
    "comparison": {
        "cn": ["环比", "同比", "对比", "比较", "变化", "增长", "下降", "增减",
               "上升", "下跌", "提高", "降低", "变动", "变化率", "vs", "相比",
               "之差", "差值", "差异"],
        "hint": (
            "计算模式：对比分析。应使用自连接（SELF JOIN）或 CASE WHEN 行列转置，"
            "分别计算两个时间段的值，然后计算差值（后期 - 前期）和百分比变化率（(后期-前期)/前期 × 100%）。"
            "若为环比（月对月），请按月度列自连接（ON 主体列相同 AND 月度差1个月）；"
            "若为同比（年对年），请按年度列自连接（ON 主体列相同 AND 年度差1年）。"
        ),
    },
    "ranking": {
        "cn": ["排名", "top", "前", "最高", "最低", "最大", "最小", "前10", "前5",
               "哪个最", "谁最"],
        "hint": (
            "计算模式：排序/Top-N。应使用 ORDER BY + LIMIT 取极值记录，"
            "或使用 RANK()/ROW_NUMBER() 窗口函数（如数据库支持）做排名。"
        ),
    },
    "trend": {
        "cn": ["趋势", "走势", "变化趋势", "逐月", "逐日", "走向", "波动"],
        "hint": (
            "计算模式：趋势分析。应按时间粒度（日/周/月）GROUP BY 后 ORDER BY 时间列，"
            "展示时间序列数据。可配合折线图展示。"
        ),
    },
    "aggregation": {
        "cn": ["汇总", "合计", "总计", "求和", "平均值", "平均"],
        "hint": "计算模式：汇总聚合。应使用 SUM/AVG/COUNT/MAX/MIN 等聚合函数配合 GROUP BY。",
    },
    "proportion": {
        "cn": ["占比", "比例", "百分比", "份额", "贡献", "构成"],
        "hint": (
            "计算模式：占比分析。应先计算总量（子查询或窗口函数），"
            "再计算每条记录占总量的百分比。"
        ),
    },
}


def detect_calculation_pattern(text: str) -> dict[str, Any]:
    """检测用户问题中的计算模式。

    Returns:
        dict with:
        - patterns: list[str] — 检测到的模式列表
        - pattern_hint: str — 供 LLM 使用的计算模式提示
        - is_comparison: bool — 是否为对比查询（最常用判断）
        - is_month_over_month: bool — 是否为环比
        - is_year_over_year: bool — 是否为同比
    """
    text = (text or "").strip()
    result: dict[str, Any] = {
        "patterns": [],
        "pattern_hint": "",
        "is_comparison": False,
        "is_month_over_month": False,
        "is_year_over_year": False,
    }

    if not text:
        return result

    detected: list[str] = []
    hints: list[str] = []

    for pattern_name, config in _CALCULATION_PATTERNS.items():
        for kw in config["cn"]:
            if kw.lower() in text.lower():
                detected.append(pattern_name)
                hints.append(config["hint"])
                break

    result["patterns"] = detected
    result["pattern_hint"] = "\n\n".join(hints)

    if "comparison" in detected:
        result["is_comparison"] = True
        if "环比" in text:
            result["is_month_over_month"] = True
        if "同比" in text:
            result["is_year_over_year"] = True

    return result


# ---------------------------------------------------------------------------
# 综合预处理入口
# ---------------------------------------------------------------------------

@dataclass
class QuestionPreprocessResult:
    """问题预处理的综合结果。"""
    question: str
    time_info: dict[str, Any]
    dimension_info: dict[str, Any]
    calculation_info: dict[str, Any]

    @property
    def combined_hint(self) -> str:
        """合并所有预处理提示，用于注入 SQL 生成上下文。"""
        parts: list[str] = []

        if self.time_info.get("time_hint"):
            parts.append(f"[时间解析] {self.time_info['time_hint']}")

        if self.dimension_info.get("dimension_hint"):
            parts.append(f"[维度过滤] {self.dimension_info['dimension_hint']}")

        if self.calculation_info.get("pattern_hint"):
            parts.append(f"[计算模式] {self.calculation_info['pattern_hint']}")

        return "\n".join(parts)

    @property
    def is_comparison_query(self) -> bool:
        """是否为对比类查询（需要自连接/CASE WHEN）。"""
        return bool(
            self.calculation_info.get("is_comparison")
            or self.time_info.get("is_comparison")
        )

    @property
    def is_month_over_month(self) -> bool:
        return bool(self.calculation_info.get("is_month_over_month"))

    @property
    def is_year_over_year(self) -> bool:
        return bool(self.calculation_info.get("is_year_over_year"))


def preprocess_question(question: str) -> QuestionPreprocessResult:
    """对用户问题执行完整的轻量级预处理。

    解析时间表达、提取维度过滤值、检测计算模式，
    全部基于规则/启发式，无需 LLM 调用，耗时 < 1ms。
    """
    q = (question or "").strip()
    return QuestionPreprocessResult(
        question=q,
        time_info=parse_chinese_time_expressions(q),
        dimension_info=extract_dimension_values(q),
        calculation_info=detect_calculation_pattern(q),
    )



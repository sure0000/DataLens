"""ChatBI 本体映射稳定性 & 答案准确性批量测试。

使用方法：
  CHATBI_API_URL=http://localhost:8000/api/ask STABILITY_RUNS=3 python tests/test_chatbi_stability.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

API_URL = os.getenv("CHATBI_API_URL", "http://localhost:8000/api/ask")
AUTH_TOKEN = os.getenv("CHATBI_AUTH_TOKEN", "datalens-dev-token")
STABILITY_RUNS = int(os.getenv("STABILITY_RUNS", "2"))

# 哪些问题需要多次运行做稳定性测试
STABILITY_IDS = {1, 7, 14, 15, 26, 3, 8, 13, 35}

# ── 48 个测试问题 ──
TEST_CASES = [
    (1,  "2026年5月张晓明的月度用电量是多少？",                     ["daily_consumption", "张晓明"]),
    (2,  "钱伟当前欠费金额是多少？",                                 ["bill", "钱伟", "overdue"]),
    (3,  "2026年5月杭州萧山发电厂有限公司的应收电费是多少？",         ["bill", "萧山发电厂"]),
    (4,  "萧山区目前有多少个有效用电客户？",                         ["customer", "count"]),
    (5,  "2026年5月城厢Ⅰ线的总供电量是多少？",                        ["supply", "城厢Ⅰ线"]),
    (6,  "杭州奥体博览中心5月份光伏日发电量是多少？",                ["generation", "光伏"]),
    (7,  "2026年5月各客户类型的售电量分别是多少？",                  ["customer_type", "sum"]),
    (8,  "2026年5月各线路的电费回收率排名？",                        ["collection", "recovery"]),
    (9,  "2026年5月哪些台区负载率超过80%？",                         ["load_rate", "80"]),
    (10, "2026年5月分时售电量中，峰平谷各占多少？",                  ["peak", "valley", "flat"]),
    (11, "2026年5月各变电站管辖的总供电量？",                        ["substation", "supply"]),
    (12, "5月份分布式光伏总发电量是多少？",                           ["distributed", "generation"]),
    (13, "张晓明4月和5月用电量环比变化多少？",                       ["环比", "张晓明"]),
    (14, "2026年4月和5月萧山区整体电费回收率对比？",                 ["collection", "recovery", "对比"]),
    (15, "2026年5月用电量TOP5大客户是谁？",                          ["top", "limit", "customer"]),
    (16, "2026年5月应收电费TOP3但未缴费的客户？",                    ["top", "unpaid"]),
    (17, "城厢Ⅰ线4月vs5月售电量变化？",                              ["城厢Ⅰ线", "change"]),
    (18, "哪些大客户的峰谷比超过1.15？",                              ["peak", "valley", "ratio", "1.15"]),
    (19, "2026年5月北干Ⅰ线上有哪些客户？各自用电量和应收电费？",     ["北干Ⅰ线", "bill"]),
    (20, "信用等级为D的客户有哪些？欠费情况如何？",                   ["credit", "overdue"]),
    (21, "2026年5月1日城厢Ⅰ线-1号台区的日负荷情况？",                ["load", "城厢Ⅰ线"]),
    (22, "临浦Ⅰ线5月为什么回收率为0？",                              ["临浦Ⅰ线", "recovery"]),
    (23, "重要性等级为一级的客户，5月缴费情况？",                     ["importance", "bill"]),
    (24, "2026年5月18日哪个台区出现了异常电表？",                    ["abnormal", "meter"]),
    (25, "杭州萧山化纤集团有限公司功率因数是多少？是否用电异常？",     ["power_factor", "化纤"]),
    (26, "2026年5月电费催缴等级是什么？需要催缴多少金额？",           ["collection", "monitor", "催缴"]),
    (27, "哪些客户连续两个月逾期？",                                  ["overdue", "连续"]),
    (28, "2026年5月大工业客户的平均度电均价是多少？",                ["avg", "price", "industrial"]),
    (29, "5月份工商业客户中，谁的分时用电峰谷比最高？",              ["peak", "valley", "ratio", "max"]),
    (30, "奥体博览中心光伏的自发自用率是多少？5月10日为何发电量增加？", ["self", "use", "光伏"]),
    (31, "杭州萧山现代农业科技公司光伏是全额上网还是自发自用？",     ["光伏", "export", "self"]),
    (32, "2026年5月已出账但未缴费的居民客户有哪些？",                ["bill", "unpaid", "resident"]),
    (33, "瓜沥Ⅰ线-1号台区5月1日的负载率是否达到预警线？",            ["load_rate", "瓜沥Ⅰ线"]),
    (34, "萧山钢铁有限公司5月电费是否已全部结清？",                  ["钢铁", "paid"]),
    (35, "2026年5月按客户类型统计售电量、应收电费、实收电费和回收率", ["customer_type", "collection"]),
    (36, "找出5月日均用电量超过10万kWh的客户，并列出其峰谷比和缴费率", ["avg", "daily", "100000"]),
    (37, "2026年5月各线路的大工业vs居民售电量占比？",               ["line", "industrial", "resident"]),
    (38, "5月份哪一天北干Ⅱ线-3号台区日用电量最高？",                 ["max", "load", "北干Ⅱ线"]),
    (39, "对比三个分布式光伏站5月总发电量和等效利用小时数",           ["distributed", "generation"]),
    (40, "如果萧山发电厂和万达广场的5月账单全部结清，整体回收率会提升到多少？", ["collection", "recovery"]),
    (41, "萧山区售电量是多少？",                                      None),   # 边界：应追问时间
    (42, "北干线的用电量",                                            None),   # 边界：应澄清
    (43, "上个月电费回收率",                                          None),   # 边界：相对时间
    (44, "居民户均用电量",                                            ["avg", "resident"]),
    (45, "抄表成功率",                                                None),   # 边界
    (46, "2026年6月的售电量",                                         None),   # 边界：空结果
    (47, "线损率是多少？",                                            None),   # 边界：无法回答
    (48, "停电次数最多的区域",                                        None),   # 边界：无法回答
]


def call_api(question: str, *, timeout: int = 180) -> dict:
    payload = json.dumps({"question": question, "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=payload,
        headers={"Authorization": f"Bearer {AUTH_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"_error": f"HTTP {e.code}"}
    except Exception as e:
        return {"_error": str(e)}


def check_sql(sql: str, keywords: list[str] | None) -> bool:
    if keywords is None:
        return True
    sql_lower = sql.lower()
    return all(kw.lower() in sql_lower for kw in keywords)


def run_single(question: str, *, timeout: int = 180) -> dict:
    t0 = time.time()
    data = call_api(question, timeout=timeout)
    elapsed = time.time() - t0
    onto = data.get("ontology_mapping", {}) or {}
    qr = data.get("query_result", {}) or {}
    return {
        "elapsed": round(elapsed, 1),
        "error": data.get("_error", ""),
        "matched": onto.get("matched", False),
        "mappings": onto.get("mappings", []) or [],
        "mapping_count": len(onto.get("mappings", []) or []),
        "ontology_trace": onto.get("ontology_trace", []) or [],
        "sql": (data.get("sql") or "")[:400],
        "query_ok": qr.get("ok", False),
        "rows": qr.get("rows", []),
        "row_count": qr.get("row_count", 0),
        "query_error": qr.get("error", ""),
        "intent": data.get("intent", ""),
        "explanation": (data.get("explanation") or "")[:200],
    }


def main():
    lines = []
    def log(msg=""):
        print(msg)
        lines.append(msg)

    log("=" * 90)
    log(f"ChatBI 测试报告 — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"API: {API_URL}  |  稳定性轮数: {STABILITY_RUNS}  |  稳定性问题: {sorted(STABILITY_IDS)}")
    log("=" * 90)
    log()

    all_results = {}
    stability_ok = 0
    stability_total = 0
    mapping_fail = []
    keyword_fail = []
    query_fail = []

    for test_id, question, expected_kw in TEST_CASES:
        need_stability = test_id in STABILITY_IDS
        runs = STABILITY_RUNS if need_stability else 1
        q_preview = question[:50]

        log(f"── #{test_id:2d} 正在测试 (×{runs}): {q_preview}")

        results = []
        for r in range(runs):
            res = run_single(question)
            results.append(res)

        all_results[test_id] = results
        first = results[0]

        # 检查本体映射
        has_mapping = first["matched"]
        mapping_kinds = {m.get("target_kind") for m in first["mappings"]}
        mapping_labels = {m.get("target_label") for m in first["mappings"]}

        # 检查 SQL 关键词
        sql_ok = check_sql(first["sql"], expected_kw)

        # 检查查询结果
        query_ok = first["query_ok"]

        # 稳定性检查（多次运行）- 语义级别对比
        if runs > 1:
            stability_total += 1
            matched_set = {r["matched"] for r in results}
            mcount_set = {r["mapping_count"] for r in results}
            # 查询结果一致性（JSON 序列化后对比）
            rows_json = [json.dumps(r.get("rows", []), sort_keys=True, ensure_ascii=False) for r in results]
            is_stable_mapping = (len(matched_set) == 1 and len(mcount_set) == 1)
            is_stable_result = (len(set(rows_json)) == 1)
            is_stable = is_stable_mapping and is_stable_result
            if is_stable:
                stability_ok += 1

        # 输出结果摘要
        status = ""
        if first["error"]:
            status += f" [ERR:{first['error']}]"
        if has_mapping:
            mt_str = ",".join(f"{k}:{l}" for k, l in zip(mapping_kinds, mapping_labels) if l)
            status += f" 映射=✓({mt_str})"
        else:
            status += " 映射=✗"
            if test_id <= 40:
                mapping_fail.append((test_id, question))

        if first["sql"]:
            status += f" SQL=✓"
        else:
            status += f" SQL=✗"

        if not sql_ok and expected_kw:
            status += f" [缺关键词:{expected_kw}]"
            if test_id <= 40:
                keyword_fail.append((test_id, question, expected_kw))

        if query_ok:
            row_count = first["row_count"]
            status += f" 查询=✓({row_count}行)"
        else:
            status += f" 查询=✗({first['query_error'][:50]})"
            if test_id <= 40:
                query_fail.append((test_id, question, first["query_error"][:80]))

        if runs > 1:
            status += f" 稳定={'✓' if is_stable else '✗'}"

        status += f" {first['elapsed']}s"
        log(f"  {status}")

        if first["ontology_trace"]:
            for t in first["ontology_trace"][:2]:
                log(f"    ├ {t.get('type','?')} \"{t.get('label','')}\" [{t.get('match_type','?')}] score={t.get('match_score','?')}")
        # SQL 仅在首次运行时输出
        if first["sql"] and test_id == next(iter(TEST_CASES))[0] if isinstance(TEST_CASES[0], tuple) else False:
            log(f"    └ SQL: {first['sql'][:150]}")

    # ── 汇总 ──
    log()
    log("=" * 90)
    log("【测试结果汇总】")
    log(f"  总问题数: {len(TEST_CASES)}")
    log(f"  本体映射准确率: {len(TEST_CASES) - len(mapping_fail)}/{len(TEST_CASES)} (未命中: {len(mapping_fail)})")
    log(f"  稳定性通过率: {stability_ok}/{stability_total}")
    log(f"  SQL 关键词缺失: {len(keyword_fail)}")
    log(f"  查询执行失败: {len(query_fail)}")

    if mapping_fail:
        log()
        log("【本体未命中】")
        for tid, q in mapping_fail:
            log(f"  #{tid} {q[:60]}")

    if keyword_fail:
        log()
        log("【SQL 关键词缺失】")
        for tid, q, kw in keyword_fail:
            log(f"  #{tid} {q[:60]}  → 缺 {kw}")

    if query_fail:
        log()
        log("【查询执行失败】")
        for tid, q, err in query_fail:
            log(f"  #{tid} {q[:60]}  → {err}")

    # 稳定性格差异
    log()
    log("【稳定性详情（语义级对比）】")
    for test_id in sorted(STABILITY_IDS):
        if test_id not in all_results:
            continue
        results = all_results[test_id]
        if len(results) < 2:
            continue
        matched_vals = {r["matched"] for r in results}
        mcount_vals = {r["mapping_count"] for r in results}
        rows_json = [json.dumps(r.get("rows", []), sort_keys=True, ensure_ascii=False) for r in results]
        result_stable = len(set(rows_json)) == 1
        log(f"  #{test_id}: 映射={matched_vals} 映射数={mcount_vals} 结果一致性={result_stable} 耗时={[r['elapsed'] for r in results]}")

    # 保存报告
    report_path = os.path.join(
        os.path.dirname(__file__), "..", "test-results", "chatbi_test_report.txt"
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log(f"\n报告已保存: {report_path}")


if __name__ == "__main__":
    main()

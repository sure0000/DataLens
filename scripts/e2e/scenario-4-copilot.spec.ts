import { test, expect } from "@playwright/test";
import { CopilotPage } from "./pages/copilot";

/**
 * 场景 4-5：ChatBI 问答验证
 *
 * 22 个精心设计的问题，按难度分层：
 *   - 基础查询 (Q01-Q04)：单表简单 WHERE/COUNT
 *   - 聚合统计 (Q05-Q08)：GROUP BY + 聚合函数
 *   - 多表 JOIN (Q09-Q12)：跨表关联分析
 *   - 业务口径 (Q13-Q17)：依赖知识库 RAG
 *   - 模糊/复杂 (Q18-Q22)：模糊意图、多步推理
 */

// ── 问题列表 ──
const QUESTIONS_BASIC = [
  "目前在制的活跃批次有哪些？列出批次号、产品型号和当前工序",
  "FAB_A01 产线今天的平均 OEE 是多少？",
  "列出所有 A 级供应商的名称和省份",
  "本月工单总数和已完成数量各是多少",
];

const QUESTIONS_AGG = [
  "各产线的设备 OEE 平均值对比",
  "不同类型缺陷的数量分布是怎样的？",
  "本月各成本中心的费用占比",
  "月度销售订单金额趋势（按月汇总）",
];

const QUESTIONS_JOIN = [
  "每个供应商的采购总额是多少？列出供应商名称和总金额",
  "良率最高的前 5 个批次对应的产品型号",
  "每个客户的销售额及回款状态",
  "各产品的毛利率对比（销售额减去成本）",
];

const QUESTIONS_KPI = [
  "整体制造良率是多少？请按工序和终检分别统计",
  "本月工单准时交付率如何？",
  "TOP 5 缺陷类型的 DPPM 是多少？",
  "前五大客户的销售额贡献度如何？",
  "FAB_A01 线的整体 OEE 和瓶颈设备分析",
];

const QUESTIONS_COMPLEX = [
  "哪些批次的质量有问题？",
  "最近的物料供应情况怎么样？",
  "产线最近是不是不太稳定？",
  "我们最赚钱的产品是哪个？",
  "对比一下有知识库和没有知识库时，问'整体良率是多少'的回答差异",
];

const ALL_QUESTIONS = [
  ...QUESTIONS_BASIC,
  ...QUESTIONS_AGG,
  ...QUESTIONS_JOIN,
  ...QUESTIONS_KPI,
  ...QUESTIONS_COMPLEX,
];

test.describe("场景 4-5: ChatBI 问答验证", () => {
  let copilot: CopilotPage;
  const results: Array<{
    category: string;
    question: string;
    hasAnswer: boolean;
    hasSql: boolean;
  }> = [];

  test.beforeEach(({ page }) => {
    copilot = new CopilotPage(page);
  });

  test("4.1: 基础查询 - 简单单表", async ({ page }) => {
    await copilot.goto();

    // 等待业务域加载并选择
    await page.waitForTimeout(2000);
    console.log("\n═══ 4.1 基础查询 ═══");

    for (const q of QUESTIONS_BASIC) {
      console.log(`\n  ❓ ${q}`);
      await copilot.ask(q, 60000);

      const answer = await copilot.getLastAnswer();
      const sql = await copilot.getSqlText();
      const hasSql = sql.length > 0;
      const hasAnswer = answer.length > 0;

      console.log(`  SQL: ${hasSql ? "✅" : "❌"} | 回答: ${hasAnswer ? "✅" : "❌"}`);
      results.push({
        category: "基础查询",
        question: q,
        hasAnswer,
        hasSql,
      });
    }
  });

  test("4.2: 聚合统计", async ({ page }) => {
    await copilot.goto();
    await page.waitForTimeout(2000);
    console.log("\n═══ 4.2 聚合统计 ═══");

    for (const q of QUESTIONS_AGG) {
      console.log(`\n  ❓ ${q}`);
      await copilot.ask(q, 60000);

      const answer = await copilot.getLastAnswer();
      const sql = await copilot.getSqlText();
      const hasSql = sql.length > 0;

      console.log(`  SQL: ${hasSql ? "✅" : "❌"}`);
      results.push({ category: "聚合统计", question: q, hasAnswer: answer.length > 0, hasSql });
    }
  });

  test("4.3: 多表 JOIN", async ({ page }) => {
    await copilot.goto();
    await page.waitForTimeout(2000);
    console.log("\n═══ 4.3 多表 JOIN ═══");

    for (const q of QUESTIONS_JOIN) {
      console.log(`\n  ❓ ${q}`);
      await copilot.ask(q, 90000);

      const answer = await copilot.getLastAnswer();
      const sql = await copilot.getSqlText();
      const hasSql = sql.length > 0;

      // 检查 SQL 中是否有 JOIN 关键字
      const hasJoin = sql.toUpperCase().includes("JOIN");
      console.log(`  SQL: ${hasSql ? "✅" : "❌"} | JOIN: ${hasJoin ? "✅" : "❌"}`);
      results.push({
        category: "多表JOIN",
        question: q,
        hasAnswer: answer.length > 0,
        hasSql,
      });
    }
  });

  test("4.4: 业务口径（带知识库 RAG）", async ({ page }) => {
    await copilot.goto();
    await page.waitForTimeout(2000);
    console.log("\n═══ 4.4 业务口径 ═══");

    for (const q of QUESTIONS_KPI) {
      console.log(`\n  ❓ ${q}`);
      await copilot.ask(q, 90000);

      const answer = await copilot.getLastAnswer();
      const sql = await copilot.getSqlText();
      const hasSql = sql.length > 0;

      // 检查回答中是否有关键业务术语（说明 RAG 生效）
      const hasTerms =
        answer.includes("良率") ||
        answer.includes("DPPM") ||
        answer.includes("OEE") ||
        answer.includes("贡献度");
      console.log(`  SQL: ${hasSql ? "✅" : "❌"} | 术语: ${hasTerms ? "✅" : "❌"}`);
      results.push({
        category: "业务口径",
        question: q,
        hasAnswer: answer.length > 0,
        hasSql,
      });
    }
  });

  test("4.5: 模糊/复杂问法", async ({ page }) => {
    await copilot.goto();
    await page.waitForTimeout(2000);
    console.log("\n═══ 4.5 模糊/复杂 ═══");

    for (const q of QUESTIONS_COMPLEX) {
      console.log(`\n  ❓ ${q}`);
      await copilot.ask(q, 90000);

      const answer = await copilot.getLastAnswer();
      const sql = await copilot.getSqlText();
      const hasSql = sql.length > 0;

      console.log(`  SQL: ${hasSql ? "✅" : "❌"}`);
      results.push({
        category: "模糊/复杂",
        question: q,
        hasAnswer: answer.length > 0,
        hasSql,
      });
    }
  });

  test.afterAll(async () => {
    // 生成汇总报告
    console.log("\n");
    console.log("=".repeat(70));
    console.log("📊 问答测试汇总报告");
    console.log("=".repeat(70));

    const categories = [...new Set(results.map((r) => r.category))];
    let totalOk = 0;

    for (const cat of categories) {
      const items = results.filter((r) => r.category === cat);
      const ok = items.filter((r) => r.hasSql).length;
      totalOk += ok;
      console.log(`\n[${cat}] ${ok}/${items.length} 通过`);
      for (const item of items) {
        const status = item.hasSql ? "✅" : "❌";
        console.log(`  ${status} ${item.question.substring(0, 50)}...`);
      }
    }

    console.log(`\n总计: ${totalOk}/${ALL_QUESTIONS.length} 通过 (${Math.round((totalOk / ALL_QUESTIONS.length) * 100)}%)`);
    console.log("=".repeat(70));
  });
});

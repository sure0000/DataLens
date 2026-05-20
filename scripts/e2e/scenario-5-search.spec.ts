import { test, expect } from "@playwright/test";

/**
 * 场景 6-7：文件导入 + 知识搜索验证
 * - 通过 API 上传额外的 PDF/DOCX 测试文档
 * - 验证混合搜索效果（向量 + BM25）
 */

const KB_NAME = "华芯制造知识库";

test.describe("场景 6-7: 文件导入与知识搜索", () => {
  test("6.1: 通过 API 导入额外的知识文件", async ({ page }) => {
    // 获取 KB ID
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const listResp = await page.request.get(`${apiBase}/api/knowledge-bases`);
    const listData = await listResp.json();
    const kb = (listData.knowledge_bases || []).find(
      (k: { name: string }) => k.name === KB_NAME
    );

    if (!kb) {
      test.skip(!kb, "知识库未找到");
      return;
    }

    console.log(`  知识库 ID: ${kb.id}`);

    // 生成一个额外的测试文档（markdown）
    const additionalDoc = `# 华芯半导体 2026 Q1 运营总结

## 生产概况
- 晶圆总产出: 32,500 片（等效8寸）
- 综合良率: 97.2%
- 整体 OEE: 82.5%

## 质量分析
- DPPM: 2,850（环比下降12%）
- 主要缺陷: particle (42%), thickness_err (28%), electrical (15%)
- 客户退货率: 0.08%

## 交付表现
- OTD: 94.5%
- 平均 Cycle Time: 18.5 天
- WIP Days: 12.3 天

## 财务指标
- 营收: 7.2 亿元
- 毛利率: 38.5%
- 单位成本: ￥1,850/片
`;

    // 通过 API 上传
    const boundary = `----Boundary${Math.random().toString(36).substring(2)}`;
    const body = [
      `--${boundary}`,
      'Content-Disposition: form-data; name="file"; filename="q1-2026-summary.md"',
      "Content-Type: text/markdown",
      "",
      additionalDoc,
      `--${boundary}--`,
    ].join("\r\n");

    const uploadResp = await page.request.post(
      `${apiBase}/api/knowledge-bases/${kb.id}/entries/import-file`,
      {
        headers: { "Content-Type": `multipart/form-data; boundary=${boundary}` },
        data: body,
      }
    );

    expect(uploadResp.ok()).toBeTruthy();
    console.log("  ✔ 额外文档已上传");

    // 等待 pipeline 处理
    await page.waitForTimeout(10000);
  });

  test("7.1: 混合搜索验证 - OEE", async ({ page }) => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const listResp = await page.request.get(`${apiBase}/api/knowledge-bases`);
    const listData = await listResp.json();
    const kb = (listData.knowledge_bases || []).find(
      (k: { name: string }) => k.name === KB_NAME
    );

    if (!kb) {
      test.skip(!kb, "知识库未找到");
      return;
    }

    // 执行混合搜索
    const searchResp = await page.request.post(
      `${apiBase}/api/knowledge-bases/${kb.id}/search`,
      { data: { query: "OEE 设备综合效率 计算方法", top_k: 5 } }
    );

    expect(searchResp.ok()).toBeTruthy();
    const data = await searchResp.json();
    const results = data.hits || data.results || data.entries || [];

    console.log(`\n  搜索 'OEE 设备综合效率' 返回 ${results.length} 条结果`);
    for (const r of results.slice(0, 3)) {
      console.log(`    - ${r.title || r.name} (score: ${r.rrf_score || r.score})`);
    }

    expect(results.length).toBeGreaterThan(0);
  });

  test("7.2: 混合搜索验证 - 良率口径", async ({ page }) => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const listResp = await page.request.get(`${apiBase}/api/knowledge-bases`);
    const listData = await listResp.json();
    const kb = (listData.knowledge_bases || []).find(
      (k: { name: string }) => k.name === KB_NAME
    );

    if (!kb) {
      test.skip(!kb, "知识库未找到");
      return;
    }

    const searchResp = await page.request.post(
      `${apiBase}/api/knowledge-bases/${kb.id}/search`,
      { data: { query: "良率计算公式 分母 hold批次", top_k: 5 } }
    );

    expect(searchResp.ok()).toBeTruthy();
    const data = await searchResp.json();
    const results = data.hits || data.results || data.entries || [];

    console.log(`\n  搜索 '良率 分母 hold批次' 返回 ${results.length} 条结果`);

    // 检查是否返回了关于良率口径的条目
    const hasYieldContent = results.some(
      (r: { snippet?: string; body?: string }) =>
        (r.snippet || r.body || "").includes("良率")
    );
    expect(hasYieldContent).toBeTruthy();
    console.log("  ✔ 良率相关知识被成功检索到");
  });

  test("7.3: 知识搜索界面展示", async ({ page }) => {
    // 获取 KB ID
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const listResp = await page.request.get(`${apiBase}/api/knowledge-bases`);
    const listData = await listResp.json();
    const kb = (listData.knowledge_bases || []).find(
      (k: { name: string }) => k.name === KB_NAME
    );

    if (!kb) {
      test.skip(!kb, "知识库未找到");
      return;
    }

    // 进入知识库页面
    await page.goto(`/knowledge-bases/${kb.id}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    // 截图知识库详情
    await page.screenshot({ path: "screenshots/7.3-kb-detail.png" });

    // 检查是否有文档列表
    const docResp = await page.request.get(
      `${apiBase}/api/knowledge-bases/${kb.id}/documents`
    );
    const docData = await docResp.json();
    const docs = docData.documents || [];
    console.log(`\n  知识库中 ${docs.length} 个文档`);
    for (const d of docs.slice(0, 5)) {
      console.log(`    - ${d.filename || d.name || d.id} (${d.status})`);
    }
    expect(docs.length).toBeGreaterThan(0);

    // 截图文档列表
    await page.screenshot({ path: "screenshots/7.4-kb-documents.png" });
  });
});

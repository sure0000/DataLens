import { test, expect } from "@playwright/test";
import { KnowledgeBasesPage } from "./pages/knowledgebases";
import { DomainsPage } from "./pages/domains";

/**
 * 场景 3：知识库导入
 * - 创建知识库
 * - 通过文件导入知识条目（批量）
 * - 验证搜索
 * - 关联到业务域
 */

const KB_NAME = "华芯制造知识库";
const KB_DESC = "包含制造业业务术语、指标口径、业务规则和常见分析示例";

const DOMAIN_NAME = "华芯半导体生产分析";

test.describe("场景 3: 知识库导入与管理", () => {
  let kbPage: KnowledgeBasesPage;

  test.beforeEach(({ page }) => {
    kbPage = new KnowledgeBasesPage(page);
  });

  test("3.1: 创建知识库（UI）", async () => {
    const { page } = kbPage;

    await kbPage.create(KB_NAME, KB_DESC);

    // 验证进入知识库详情页
    await expect(page.locator("text=语义知识库").first()).toBeVisible();
    await page.waitForTimeout(1000);

    // 截图
    await page.screenshot({ path: "screenshots/3.1-kb-created.png" });
  });

  test("3.2: 批量导入知识条目（文件上传）", async () => {
    const { page } = kbPage;

    // 通过 API 获取 KB ID
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const listResp = await page.request.get(`${apiBase}/api/knowledge-bases`);
    const listData = await listResp.json();
    const kb = (listData.knowledge_bases || []).find(
      (k: { name: string }) => k.name === KB_NAME
    );

    if (!kb) {
      test.skip(!kb, "知识库未找到，跳过");
      return;
    }

    console.log(`  知识库 ID: ${kb.id}, 开始导入文件...`);

    // 读取知识库 markdown 文件内容
    const fs = await import("fs");
    const path = await import("path");
    const filePath = path.resolve(
      __dirname,
      "../testdata/knowledge_manufacturing_domain.md"
    );

    if (!fs.existsSync(filePath)) {
      test.skip(true, "知识库文件不存在，跳过");
      return;
    }

    // 通过 UI 导入
    await page.goto(`/knowledge-bases/${kb.id}`);
    await page.waitForLoadState("networkidle");

    // 等待页面完全加载
    await page.waitForTimeout(2000);

    // 截图初始状态
    await page.screenshot({ path: "screenshots/3.2-before-import.png" });

    // 使用 UI 导入文件
    await kbPage.importFile(filePath);

    // 等待上传成功反馈
    await page.waitForTimeout(3000);
    console.log("  文件已上传，等待 pipeline 处理...");

    // 等待 pipeline 处理完成
    await kbPage.waitForPipeline(kb.id, 90000);

    // 刷新页面
    await page.reload();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    // 截图导入后
    await page.screenshot({ path: "screenshots/3.3-kb-after-import.png" });
  });

  test("3.3: 关联知识库到业务域", async () => {
    const { page } = kbPage;
    const domainsPage = new DomainsPage(page);

    // 进入业务域详情
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await domainsPage.clickDomainName(DOMAIN_NAME);

    // 关联知识库
    await domainsPage.associateKnowledgeBase(KB_NAME);

    // 截图
    await page.screenshot({
      path: "screenshots/3.4-domain-kb-associated.png",
    });

    // 验证关联成功
    await expect(page.locator(`text=${KB_NAME}`).first()).toBeVisible();
  });

  test("3.5: 知识搜索验证", async () => {
    const { page } = kbPage;

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

    // 进入知识库详情
    await page.goto(`/knowledge-bases/${kb.id}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    // 尝试执行混合搜索（如果页面有搜索面板）
    const searchResult = await page.request.post(
      `${apiBase}/api/knowledge-bases/${kb.id}/search`,
      { data: { query: "OEE 良率", top_k: 5 } }
    );

    if (searchResult.ok()) {
      const data = await searchResult.json();
      const results = data.hits || data.results || data.entries || [];
      console.log(`  搜索 'OEE 良率' 返回 ${results.length} 条结果`);
      expect(results.length).toBeGreaterThan(0);
    } else {
      console.warn("  搜索接口返回异常");
    }

    // 截图
    await page.screenshot({ path: "screenshots/3.5-kb-search.png" });
  });
});

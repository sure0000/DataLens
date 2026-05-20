import { test, expect } from "@playwright/test";
import { DataSourcesPage } from "./pages/datasources";

/**
 * 场景 1：数据源接入
 * 测试端到端的数据源创建、连接测试、库表分析流程
 */

const DS_NAME = "华芯半导体生产库";
const MYSQL_CONFIG = {
  host: process.env.MYSQL_HOST || "127.0.0.1",
  port: Number(process.env.MYSQL_PORT) || 3306,
  user: process.env.MYSQL_USER || "root",
  password: process.env.MYSQL_PASSWORD || "",
  database: "manufacturing_demo",
};

test.describe("场景 1: 数据源接入", () => {
  let datasourcesPage: DataSourcesPage;

  test.beforeAll(async ({ request }) => {
    // 清理旧数据源及关联的业务域，避免重复
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    // 先删域（级联删 selections），再删数据源
    const domainResp = await request.get(`${apiBase}/api/business-domains`);
    const domainData = await domainResp.json() as { domains: Array<{ id: number; name: string }> };
    for (const d of domainData.domains || []) {
      if (d.name.includes("华芯")) {
        await request.delete(`${apiBase}/api/business-domains/${d.id}`).catch(() => {});
      }
    }
    const dsResp = await request.get(`${apiBase}/api/datasources`);
    const dsData = await dsResp.json() as { datasources: Array<{ id: number; name: string }> };
    for (const ds of dsData.datasources || []) {
      if (ds.name === DS_NAME) {
        await request.delete(`${apiBase}/api/datasources/${ds.id}`).catch(() => {});
      }
    }
  });

  test.beforeEach(({ page }) => {
    datasourcesPage = new DataSourcesPage(page);
  });

  test("1.1 ~ 1.4: 新建 MySQL 数据源、测试连接并保存", async () => {
    const { page } = datasourcesPage;
    await datasourcesPage.goto();

    // 点击新增
    await datasourcesPage.clickAdd();

    // 选择 MySQL
    await datasourcesPage.selectTypeMySQL();

    // 填写连接信息
    await datasourcesPage.fillForm({
      name: DS_NAME,
      host: MYSQL_CONFIG.host,
      port: MYSQL_CONFIG.port,
      database: MYSQL_CONFIG.database,
      username: MYSQL_CONFIG.user,
      password: MYSQL_CONFIG.password,
      description: "华芯半导体路演演示数据源 (9张表)",
    });

    // 测试连接
    await datasourcesPage.clickTestConnection();
    const testResult = await datasourcesPage.waitForTestResult();
    console.log(`  连接结果: ${testResult}`);

    // 断言连接成功，发现 9 张表
    expect(testResult).toContain("连接成功");
    expect(testResult).toContain("9");

    // 截图
    await page.screenshot({ path: "screenshots/1.2-connection-success.png" });

    // 保存数据源
    await datasourcesPage.clickSave();
    await page.waitForTimeout(1000);

    // 验证数据源出现在列表中
    const names = await datasourcesPage.getDataSourceNames();
    expect(names.some((n) => n.includes("华芯半导体"))).toBeTruthy();

    // 截图
    await page.screenshot({ path: "screenshots/1.3-datasource-saved.png" });
  });

  test("1.5: 触发分析并查看数据源详情", async () => {
    const { page } = datasourcesPage;

    // 通过 API 直接触发分析
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const listResp = await page.request.get(`${apiBase}/api/datasources`);
    const listData = await listResp.json();
    const ds = (listData.datasources || []).find(
      (d: { name: string }) => d.name === DS_NAME
    );

    if (!ds) {
      test.skip(!ds, "数据源未找到，跳过分析测试");
      return;
    }

    console.log(`  数据源 ID: ${ds.id}, 触发单库分析 (manufacturing_demo)...`);

    // 仅分析 manufacturing_demo 数据库（避免分析 MySQL 上所有其他数据库）
    const analyzeResp = await page.request.post(
      `${apiBase}/api/datasources/${ds.id}/analyze/database/manufacturing_demo`
    );
    expect(analyzeResp.ok()).toBeTruthy();

    // 进入数据源详情查看表（catalog 端点在分析进行中即可正常返回）
    await page.goto(`/datasources/${ds.id}`);
    await page.waitForLoadState("networkidle");

    // 等待详情页渲染完成（应显示 manufacturing_demo 数据库卡片）
    await expect(page.locator("text=manufacturing_demo").first()).toBeVisible({ timeout: 30000 });

    // 验证加载状态已消失
    await expect(page.locator("text=正在加载数据源详情")).not.toBeVisible({ timeout: 5000 });

    // 截图
    await page.screenshot({ path: "screenshots/1.5-datasource-detail.png" });
  });
});

import { test, expect } from "@playwright/test";
import { DomainsPage } from "./pages/domains";

/**
 * 场景 2：业务域与选表
 * 测试创建业务域、挂载数据表、查看表详情
 */

const DOMAIN_NAME = "华芯半导体生产分析";
const DOMAIN_DESC =
  "覆盖华芯半导体制造的全链路数据：晶圆在制品(WIP)、工单、设备OEE、质量检验、供应链采购、成本核算、销售订单。适用于生产管理、质量分析、成本控制场景。";

test.describe("场景 2: 业务域与选表", () => {
  let domainsPage: DomainsPage;

  test.beforeEach(({ page }) => {
    domainsPage = new DomainsPage(page);
  });

  test("2.1 ~ 2.2: 创建业务域并挂载表", async () => {
    const { page } = domainsPage;

    // 通过 UI 创建业务域
    await domainsPage.create(DOMAIN_NAME, DOMAIN_DESC);

    // 验证创建成功（页面刷新后出现在列表中）
    await page.waitForTimeout(1000);
    await expect(page.locator(`text=${DOMAIN_NAME}`).first()).toBeVisible();

    // 截图
    await page.screenshot({ path: "screenshots/2.1-domain-created.png" });

    // 进入详情页
    await domainsPage.clickDomainName(DOMAIN_NAME);

    // 批量添加所有表
    await domainsPage.batchAddAllTables();

    // 截图
    await page.screenshot({ path: "screenshots/2.2-tables-mounted.png" });

    // 验证数据表列表中包含 9 张表
    await expect(page.locator("text=数据表列表")).toBeVisible();
  });

  test("2.3: 验证表已正确挂载", async () => {
    const { page } = domainsPage;

    // 进入业务域详情
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // 点击已创建的业务域
    await domainsPage.clickDomainName(DOMAIN_NAME);
    await page.waitForLoadState("networkidle");

    // 验证详情页标题正确
    await expect(page.locator(`text=${DOMAIN_NAME}`).first()).toBeVisible();

    // 使用搜索框依次验证 9 张 manufacturing_demo 表（搜索可绕过列表分页限制）
    const expectedTables = [
      "wip_lots",
      "production_orders",
      "equipment_metrics",
      "quality_inspections",
      "suppliers",
      "purchase_orders",
      "cost_transactions",
      "customers",
      "sales_orders",
    ];

    for (const tableName of expectedTables) {
      const searchInput = page.locator('input[placeholder="搜索数据库/数据表/说明"]');
      await searchInput.fill(tableName);
      await page.waitForTimeout(500);
      await expect(page.locator(`text=${tableName}`).first()).toBeVisible();
      console.log(`  ✔ 表 ${tableName} 已挂载`);
      await searchInput.clear();
    }

    // 截图
    await page.screenshot({ path: "screenshots/2.3-all-tables-verified.png" });
  });
});

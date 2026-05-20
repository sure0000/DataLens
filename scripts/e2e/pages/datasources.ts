import type { Page } from "@playwright/test";

/**
 * Data Sources 页面对象模型
 * 对应 frontend/app/datasources/page.tsx
 */
export class DataSourcesPage {
  constructor(private page: Page) {}

  /** 导航到数据源列表 */
  async goto() {
    await this.page.goto("/datasources");
    await this.page.waitForLoadState("networkidle");
  }

  /** 点击"新增数据源" */
  async clickAdd() {
    await this.page.getByRole("button", { name: "新增数据源" }).first().click();
    // 等待类型选择器出现
    await this.page.waitForSelector("text=关系型");
  }

  /** 在类型选择器中选择 MySQL */
  async selectTypeMySQL() {
    // MySQL 卡片在"关系型"分组下，按钮完整文本为 "MySQL OLTP、业务库"
    await this.page.getByRole("button", { name: "MySQL OLTP、业务库" }).click();
    // 等待表单渲染
    await this.page.waitForTimeout(500);
  }

  /** 填写连接表单 */
  async fillForm(params: {
    name?: string;
    host?: string;
    port?: number;
    database?: string;
    username?: string;
    password?: string;
    description?: string;
  }) {
    const { name, host, port, database, username, password, description } = params;

    if (name) {
      const input = this.page.locator(
        'label:has(span:text("名称（必填，页面显示名）")) input'
      );
      await input.clear();
      await input.fill(name);
    }

    if (description) {
      const input = this.page.locator(
        'label:has(span:text("备注（选填，用途说明）")) input'
      );
      await input.fill(description);
    }

    if (host) {
      const input = this.page.locator('label:has(span:text("Host")) input');
      await input.clear();
      await input.fill(host);
    }

    if (port) {
      const input = this.page.locator('label:has(span:text("Port")) input');
      await input.clear();
      await input.fill(String(port));
    }

    if (database) {
      const input = this.page.locator('label:has(span:text("Database")) input');
      await input.clear();
      await input.fill(database);
    }

    if (username) {
      const input = this.page.locator('label:has(span:text("Username")) input');
      await input.clear();
      await input.fill(username);
    }

    if (password !== undefined) {
      // Password 字段的 placeholder 为 "输入连接密码"
      const input = this.page.locator('[placeholder="输入连接密码"]');
      await input.waitFor({ state: "visible", timeout: 5000 });
      await input.clear();
      await this.page.waitForTimeout(200);
      await input.fill(password);
      // 验证已填入
      const filled = await input.inputValue();
      if (!filled) {
        await input.pressSequentially(password, { delay: 30 });
      }
    }
  }

  /** 点击"测试当前连接" */
  async clickTestConnection() {
    await this.page.getByRole("button", { name: "测试当前连接" }).click();
  }

  /** 等待连接测试结果 */
  async waitForTestResult(): Promise<string> {
    // 结果出现在 role="status" 的元素中
    const result = await this.page.waitForSelector('[role="status"]', {
      timeout: 30000,
    });
    return (await result.textContent()) || "";
  }

  /** 判断连接测试是否成功 */
  async isTestSuccessful(): Promise<boolean> {
    const text = await this.waitForTestResult();
    return text.includes("连接成功");
  }

  /** 点击"保存数据源" */
  async clickSave() {
    await this.page.getByRole("button", { name: "保存数据源" }).click();
    // 等待模态框关闭
    await this.page.waitForTimeout(1000);
  }

  /** 点击已保存数据源的名称进入详情 */
  async clickDataSourceName(name: string) {
    await this.page.getByRole("link", { name }).first().click();
    await this.page.waitForLoadState("networkidle");
  }

  /** 在数据源详情页点击"分析全部"（POST /api/datasources/:id/analyze/datasource） */
  async triggerAnalyzeAll() {
    // 数据源详情页有一个"分析全部表"的按钮，通过 API 方式也接受
    // 尝试找按钮
    const btn = this.page.getByRole("button", { name: /分析全部|分析所有/i });
    if (await btn.isVisible()) {
      await btn.click();
      await this.page.waitForTimeout(2000);
      // 等待分析完成（可能需要几秒到几十秒）
      await this.page.waitForTimeout(10000);
    }
  }

  /** 获取数据源列表中的所有名称 */
  async getDataSourceNames(): Promise<string[]> {
    return this.page.locator(".app-list-item-main .app-link").allTextContents();
  }

  /** 直接通过 API 创建并分析数据源（加速测试） */
  async createViaApi(params: {
    name: string;
    sourceType: string;
    host: string;
    port: number;
    database: string;
    username: string;
    password?: string;
  }) {
    const { name, sourceType, host, port, database, username, password } = params;
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    // 创建数据源
    const createResp = await this.page.request.post(`${apiBase}/api/datasources`, {
      data: {
        name,
        source_type: sourceType,
        host,
        port,
        database,
        username,
        connection_password: password || "",
      },
    });
    const createResult = await createResp.json();
    const dsId = createResult.id || createResult.datasource?.id;

    if (!dsId) {
      throw new Error(`Failed to create datasource: ${JSON.stringify(createResult)}`);
    }

    // 触发全量分析
    await this.page.request.post(`${apiBase}/api/datasources/${dsId}/analyze/datasource`);

    // 等待分析完成
    await this.page.waitForTimeout(5000);

    return dsId;
  }
}

import type { Page } from "@playwright/test";

/**
 * Business Domain 页面对象模型
 * 对应 frontend/app/page.tsx (列表) 和 frontend/app/business-domains/[id]/page.tsx (详情)
 */
export class DomainsPage {
  constructor(private page: Page) {}

  /** 导航到首页（业务域列表） */
  async goto() {
    await this.page.goto("/");
    await this.page.waitForLoadState("networkidle");
  }

  /** 点击"新增业务域" */
  async clickAdd() {
    await this.page.getByRole("button", { name: "新增业务域" }).first().click();
    await this.page.waitForSelector('[aria-labelledby="create-domain-title"]');
  }

  /** 填写新增业务域表单 */
  async fillCreateForm(name: string, description: string) {
    const nameInput = this.page.locator(
      'label:has(span:text("业务域名称（必填）")) input'
    );
    await nameInput.fill(name);

    const descInput = this.page.locator(
      'label:has(span:text("业务描述（选填）")) textarea'
    );
    await descInput.fill(description);
  }

  /** 点击"保存"按钮创建业务域 */
  async clickSave() {
    const saveBtn = this.page.getByRole("button", { name: "保存" });
    // 确认按钮不被 disabled
    await saveBtn.waitFor({ state: "visible" });
    // 点击保存
    await saveBtn.click();
    await this.page.waitForTimeout(1500);
  }

  /** 点击进入业务域详情 */
  async clickDomainName(name: string) {
    await this.page.getByRole("link", { name }).first().click();
    await this.page.waitForLoadState("networkidle");
  }

  /** 创建业务域（完整流程） */
  async create(name: string, description: string) {
    await this.goto();
    await this.clickAdd();
    await this.fillCreateForm(name, description);
    await this.clickSave();
  }

  /**
   * 在业务域详情页：批量添加数据表
   * 通过"选中当前结果的全部表"全选后保存
   */
  async batchAddAllTables() {
    // 点击"批量添加数据表"
    await this.page.getByRole("button", { name: "批量添加数据表" }).click();
    await this.page.waitForTimeout(500);

    // 等待批量选择模态框打开
    await this.page.waitForSelector('h3:has-text("批量添加数据表")');

    // 点击"选中当前结果的全部表"
    await this.page.getByRole("button", { name: "选中当前结果的全部表" }).click();
    await this.page.waitForTimeout(300);

    // 点击"保存选择"
    await this.page.getByRole("button", { name: "保存选择" }).click();
    await this.page.waitForTimeout(500);

    // 在确认对话框中点击"确认保存"
    const confirmBtn = this.page.getByRole("button", { name: "确认保存" });
    if (await confirmBtn.isVisible()) {
      await confirmBtn.click();
      await this.page.waitForTimeout(2000);
    }
  }

  /** 关联知识库到业务域 */
  async associateKnowledgeBase(kbName: string) {
    // 点击"添加知识库"
    await this.page.getByRole("button", { name: "添加知识库" }).click();
    await this.page.waitForTimeout(300);

    // 勾选指定知识库
    const kbCheckbox = this.page.locator("label", { hasText: kbName }).locator('input[type="checkbox"]').first();
    await kbCheckbox.check();
    await this.page.waitForTimeout(200);

    // 点击"确定"
    await this.page.getByRole("button", { name: "确定" }).click();
    await this.page.waitForTimeout(300);

    // 点击"保存"关联
    await this.page.getByRole("button", { name: "保存" }).first().click();
    await this.page.waitForTimeout(1000);
  }

  /** 直接通过 API 创建业务域并挂载表（加速） */
  async createViaApi(name: string, description: string, datasourceId: number) {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    // 创建业务域
    const resp = await this.page.request.post(`${apiBase}/api/business-domains`, {
      data: { name, description },
    });
    const result = await resp.json();
    const domainId = result.id;

    if (!domainId) {
      throw new Error(`Failed to create domain: ${JSON.stringify(result)}`);
    }

    // 获取数据源的库表选项
    const optionsResp = await this.page.request.get(
      `${apiBase}/api/business-domains/options`
    );
    const options = await optionsResp.json();

    // 构建 selections
    const selections: Array<{
      datasource_id: number;
      database_name: string;
      table_names: string[];
    }> = [];

    for (const ds of options.datasources || []) {
      if (ds.id === datasourceId) {
        for (const db of ds.databases || []) {
          selections.push({
            datasource_id: ds.id,
            database_name: db.name,
            table_names: (db.tables || []).map((t: { name: string }) => t.name),
          });
        }
      }
    }

    if (selections.length > 0) {
      await this.page.request.post(
        `${apiBase}/api/business-domains/${domainId}/selections`,
        { data: selections }
      );
    }

    return domainId;
  }
}

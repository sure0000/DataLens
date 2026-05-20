import type { Page } from "@playwright/test";

/**
 * Copilot 页面对象模型
 * 对应 frontend/app/copilot/page.tsx
 */
export class CopilotPage {
  constructor(private page: Page) {}

  /** 导航到 Copilot */
  async goto() {
    await this.page.goto("/copilot");
    await this.page.waitForLoadState("networkidle");
    // 等待页面完全加载
    await this.page.waitForTimeout(2000);
  }

  /** 选择业务域 */
  async selectBusinessDomain(domainName: string) {
    // 业务域下拉选择器
    const domainSelector = this.page.locator("text=选择业务域").first();
    if (await domainSelector.isVisible()) {
      await domainSelector.click();
      await this.page.waitForTimeout(300);

      // 从下拉菜单中选择目标业务域
      const option = this.page.getByRole("option", { name: domainName });
      if (await option.isVisible()) {
        await option.click();
        await this.page.waitForTimeout(500);
      }
    }
  }

  /** 判断是否在聊天模式（有活跃 session） */
  async isChatMode(): Promise<boolean> {
    return this.page.url().includes("session=");
  }

  /** 提问并等待回答 */
  async ask(question: string, timeoutMs = 90000): Promise<void> {
    const textarea = this.page.locator("textarea").first();
    // 等待输入框可见且可用（非 disabled）
    await textarea.waitFor({ state: "visible", timeout: 15000 });
    await textarea.waitFor({ state: "enabled", timeout: 30000 }).catch(() => {});

    // 清空并输入问题
    await textarea.clear();
    await textarea.fill(question);
    await this.page.waitForTimeout(300);

    // 按 Enter 提交（不是 Shift+Enter）
    await textarea.press("Enter");

    // 等待回答完成
    await this.waitForAnswer(timeoutMs);

    // 回答完成后，等待 textarea 重新可用（流式结束时前端会解除 disabled）
    await textarea.waitFor({ state: "enabled", timeout: 10000 }).catch(() => {});
  }

  /** 等待流式回答完成 */
  async waitForAnswer(timeoutMs = 90000): Promise<void> {
    const startTime = Date.now();
    const deadline = startTime + timeoutMs;

    // 等待生成指示器出现（有 5s 窗口让它出现）
    const generatingLocator = this.page
      .locator("text=正在分析中")
      .or(this.page.locator("text=生成中"))
      .or(this.page.locator("text=流式加载中"))
      .first();

    const appeared = await generatingLocator
      .waitFor({ state: "visible", timeout: 5000 })
      .then(() => true)
      .catch(() => false);

    if (appeared) {
      // 等待生成指示器消失
      const remaining = deadline - Date.now();
      if (remaining > 0) {
        await generatingLocator
          .waitFor({ state: "hidden", timeout: remaining })
          .catch(() => {
            console.warn("  ⚠️ 生成指示器超时未消失，继续检查回答...");
          });
      }
    } else {
      // 可能生成太快没看到指示器，等待 SQL 或回答出现
      await this.page
        .locator(".sql-block")
        .or(this.page.locator(".copilot-md"))
        .first()
        .waitFor({ state: "visible", timeout: 5000 })
        .catch(() => {});
    }

    // 再额外等待确保渲染完成
    await this.page.waitForTimeout(500);

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    console.log(`  ⏱ 回答耗时: ${elapsed}s`);
  }

  /** 获取最后一条助手的回答文本 */
  async getLastAnswer(): Promise<string> {
    // 查找所有助手消息（含 ChatGptStyleBody 的容器），取最后一条
    const assistantMessages = this.page.locator(".copilot-md").last();
    if (await assistantMessages.isVisible().catch(() => false)) {
      return (await assistantMessages.textContent()) || "";
    }
    return "";
  }

  /** 获取页面上可见的 SQL 文本 */
  async getSqlText(): Promise<string> {
    // 优先从最新的 <details> 面板中取结构化 SQL
    const sqlBlock = this.page.locator(".sql-block").last();
    if (await sqlBlock.isVisible().catch(() => false)) {
      return (await sqlBlock.textContent()) || "";
    }
    return "";
  }

  /** 连续问多组问题（适合预设脚本） */
  async askBatch(questions: string[], timeoutPerQuestion = 90000) {
    const results: Array<{ question: string; answer: string; ok: boolean }> = [];

    for (const q of questions) {
      console.log(`\n  ❓: ${q}`);
      try {
        await this.ask(q, timeoutPerQuestion);
        const answer = await this.getLastAnswer();
        const hasSql = (await this.getSqlText()).length > 0;
        results.push({ question: q, answer, ok: hasSql });
        console.log(`  ✅ SQL 生成: ${hasSql ? "是" : "否"}`);
      } catch (e) {
        console.warn(`  ⚠️ 问题失败: ${q}`);
        results.push({ question: q, answer: String(e), ok: false });
      }

      // 截图
      const safeName = q.replace(/[^a-zA-Z0-9一-龥]/g, "_").substring(0, 50);
      await this.page.screenshot({
        path: `screenshots/copilot_${safeName}.png`,
        fullPage: false,
      });
    }

    return results;
  }

  /** 获取业务域下拉的当前选中值 */
  async getSelectedDomain(): Promise<string> {
    const el = this.page.locator("text=选择业务域").first();
    if (await el.isVisible()) {
      return (await el.textContent()) || "";
    }
    return "";
  }

  /** 通过 API 询问（跳过 UI，用在批量测试中） */
  async askViaApi(
    question: string,
    businessDomainId: number | null
  ): Promise<Record<string, unknown>> {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const resp = await this.page.request.post(`${apiBase}/api/ask`, {
      data: {
        question,
        business_domain_id: businessDomainId,
        table_id: null,
      },
      timeout: 120000,
    });
    return await resp.json();
  }
}

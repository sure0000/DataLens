import type { Page } from "@playwright/test";

/**
 * Knowledge Base 页面对象模型
 * 对应 frontend/app/knowledge-bases/page.tsx 和 [id]/page.tsx
 */
export class KnowledgeBasesPage {
  constructor(private page: Page) {}

  /** 导航到知识库列表 */
  async goto() {
    await this.page.goto("/knowledge-bases");
    await this.page.waitForLoadState("networkidle");
  }

  /** 创建知识库（打开模态框 → 填写 → 保存） */
  async create(name: string, description: string) {
    await this.goto();

    // 点击"新建知识库"按钮
    await this.page.getByRole("button", { name: "新建知识库" }).click();
    await this.page.waitForTimeout(500);

    // 填写名称
    const nameInput = this.page.locator(
      'label:has(span:text("名称（必填）")) input'
    );
    await nameInput.fill(name);

    // 填写描述
    const descInput = this.page.locator(
      'label:has(span:text("描述（选填）")) textarea'
    );
    await descInput.fill(description);

    // 点击"保存"
    await this.page.getByRole("button", { name: "保存" }).click();
    await this.page.waitForTimeout(2000);
  }

  /** 点击知识库进入详情 */
  async clickKnowledgeBase(name: string) {
    await this.page.getByRole("link", { name }).first().click();
    await this.page.waitForLoadState("networkidle");
  }

  /** 通过文件导入知识库条目 */
  async importFile(filePath: string) {
    // 点击"导入"按钮
    await this.page.getByRole("button", { name: "导入" }).click();
    await this.page.waitForTimeout(500);

    // 点击"文档导入"卡片
    await this.page.getByRole("button", { name: "文档导入" }).click();
    await this.page.waitForTimeout(500);

    // 文件输入是 sr-only 类型，用 setInputFiles
    const fileInput = this.page.locator('input[type="file"]');
    await fileInput.setInputFiles(filePath);

    // 等待上传和处理完成
    await this.page.waitForTimeout(3000);
  }

  /** 直接通过 API 创建知识库 */
  async createViaApi(name: string, description: string): Promise<number> {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const resp = await this.page.request.post(`${apiBase}/api/knowledge-bases`, {
      data: { name, description },
    });
    const result = await resp.json();

    const kbId = result.id || result.knowledge_base?.id;
    if (!kbId) {
      throw new Error(`Failed to create KB: ${JSON.stringify(result)}`);
    }
    return kbId;
  }

  /** 通过 API 批量创建知识条目 */
  async addEntryViaApi(
    kbId: number,
    entry: { title: string; body: string; summary?: string; tags?: string[] }
  ) {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    await this.page.request.post(
      `${apiBase}/api/knowledge-bases/${kbId}/entries`,
      {
        data: {
          title: entry.title,
          body: entry.body,
          summary: entry.summary || "",
          tags: entry.tags || [],
        },
      }
    );
  }

  /** 通过 API 上传文件到知识库 */
  async importFileViaApi(kbId: number, filePath: string) {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    // 读取文件内容
    const fs = await import("fs");
    const fileBuffer = fs.readFileSync(filePath);
    const fileName = filePath.split("/").pop() || "knowledge.md";

    // 创建 FormData
    const boundary = `----FormBoundary${Math.random().toString(36).substring(2)}`;
    let body = "";
    body += `--${boundary}\r\n`;
    body += `Content-Disposition: form-data; name="file"; filename="${fileName}"\r\n`;
    body += `Content-Type: text/markdown\r\n\r\n`;
    body += fileBuffer.toString("utf-8");
    body += `\r\n--${boundary}--\r\n`;

    await this.page.request.post(
      `${apiBase}/api/knowledge-bases/${kbId}/entries/import-file`,
      {
        headers: {
          "Content-Type": `multipart/form-data; boundary=${boundary}`,
        },
        data: body,
      }
    );
  }

  /** 等待文档处理 pipeline 完成 */
  async waitForPipeline(kbId: number, timeoutMs = 60000) {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const start = Date.now();

    while (Date.now() - start < timeoutMs) {
      const resp = await this.page.request.get(
        `${apiBase}/api/knowledge-bases/${kbId}/documents`
      );
      const data = await resp.json();
      const docs = data.documents || [];

      const allIndexed = docs.every(
        (d: { status: string }) => d.status === "indexed"
      );
      const anyFailed = docs.some((d: { status: string }) => d.status === "failed");

      if (allIndexed && docs.length > 0) return true;
      if (anyFailed) {
        console.warn("Some documents failed pipeline processing");
        return false;
      }

      await this.page.waitForTimeout(2000);
    }

    console.warn("Pipeline wait timeout");
    return false;
  }
}

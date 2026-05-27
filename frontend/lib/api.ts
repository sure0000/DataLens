const RAW_API = (process.env.NEXT_PUBLIC_API_URL || "").trim();
const DEFAULT_API = "http://127.0.0.1:8000";

function isLoopbackHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

function stripTrailingSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

function resolveApiBase(): string {
  const configured = RAW_API || DEFAULT_API;
  if (typeof window === "undefined") return stripTrailingSlash(configured);
  try {
    const currentUrl = new URL(window.location.href);
    const targetUrl = new URL(configured);
    const currentIsLoopback = isLoopbackHost(currentUrl.hostname);
    const targetIsLoopback = isLoopbackHost(targetUrl.hostname);

    // 局域网访问前端时，若 API 仍配置为 localhost/127.0.0.1，自动替换为当前访问主机，避免“假断连”。
    if (!currentIsLoopback && targetIsLoopback) {
      targetUrl.hostname = currentUrl.hostname;
    }
    return stripTrailingSlash(targetUrl.toString());
  } catch {
    return stripTrailingSlash(configured);
  }
}

export const API = resolveApiBase();

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

/** 将 FastAPI 等返回的 JSON `{ "detail": "..." }` 解析为可读字符串（便于 Toast 展示）。 */
export function formatApiError(e: ApiError): string {
  const raw = (e.message || "").trim();
  if (!raw) return `请求失败（HTTP ${e.status}，无响应正文）`;

  const fallback = `请求失败（HTTP ${e.status}）`;

  try {
    const j = JSON.parse(raw) as { detail?: unknown; message?: unknown };
    if (typeof j.detail === "string") {
      const s = j.detail.trim();
      if (s.length > 4000) return `${s.slice(0, 4000)}…`;
      return s || fallback;
    }
    if (typeof j.message === "string" && j.message.trim() && j.detail === undefined) {
      return j.message.trim();
    }
    if (Array.isArray(j.detail)) {
      const parts = j.detail.map((item: unknown) => {
        if (typeof item === "object" && item !== null) {
          const o = item as Record<string, unknown>;
          if (typeof o.msg === "string" && o.msg.trim()) return o.msg.trim();
          if (typeof o.message === "string" && o.message.trim()) return o.message.trim();
        }
        return JSON.stringify(item);
      });
      const joined = parts.filter(Boolean).join("；").trim();
      if (joined) return joined;
    }
    if (j.detail !== undefined && j.detail !== null && typeof j.detail === "object") {
      try {
        const s = JSON.stringify(j.detail);
        if (s && s !== "{}") return s;
      } catch {
        /* ignore */
      }
    }
  } catch {
    /* 非 JSON 时直接使用原文 */
  }

  const out = raw.length > 4000 ? `${raw.slice(0, 4000)}…` : raw;
  return out.trim() || fallback;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${API}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }
    });
  } catch (e: unknown) {
    const hint = e instanceof Error ? e.message : String(e);
    throw new ApiError(
      0,
      JSON.stringify({
        detail: `无法连接 API（${API}）：${hint}。请确认后端已启动，且浏览器能访问该地址（勿混用本机与局域网访问方式）。`
      })
    );
  }
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText);
    const body = (text || "").trim() || resp.statusText || `HTTP ${resp.status}`;
    throw new ApiError(resp.status, body);
  }
  return resp.json() as Promise<T>;
}

/** POST multipart（不要设置 Content-Type，由浏览器写入 boundary） */
export async function apiForm<T>(path: string, form: FormData): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${API}${path}`, { method: "POST", body: form });
  } catch (e: unknown) {
    const hint = e instanceof Error ? e.message : String(e);
    throw new ApiError(
      0,
      JSON.stringify({
        detail: `无法连接 API（${API}）：${hint}。请确认后端已启动且地址配置正确。`
      })
    );
  }
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText);
    const body = (text || "").trim() || resp.statusText || `HTTP ${resp.status}`;
    throw new ApiError(resp.status, body);
  }
  return resp.json() as Promise<T>;
}

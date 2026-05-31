export type GitSourceFormFields = {
  name: string;
  provider: "github" | "gitlab";
  apiBase: string;
  owner: string;
  repo: string;
  branch: string;
  pathPrefix: string;
  token: string;
  includeGlobs: string;
  maxFileKb: number;
  maxFiles: number;
  enableDocumentIndexing: boolean;
  extractionProfile: "mixed" | "data_warehouse";
  cron: string;
  enabled: boolean;
};

export type ParsedGitRepo = {
  provider: "github" | "gitlab";
  owner: string;
  repo: string;
  branch?: string;
  pathPrefix?: string;
  apiBase?: string;
};

function stripGitSuffix(name: string): string {
  return name.replace(/\.git$/i, "");
}

function normalizePathPrefix(path: string): string {
  const trimmed = path.replace(/^\/+|\/+$/g, "");
  return trimmed ? `${trimmed}/` : "";
}

export function parseGitHubRepoUrl(input: string): ParsedGitRepo | null {
  const raw = input.trim();
  if (!raw) return null;

  if (!raw.includes("://") && !raw.startsWith("git@")) {
    const short = raw.match(/^([\w.-]+)\/([\w.-]+?)(?:\.git)?\/?$/);
    if (short) {
      return {
        provider: "github",
        owner: short[1],
        repo: stripGitSuffix(short[2]),
      };
    }
  }

  const ssh = raw.match(/^git@([\w.-]+):([^/]+)\/([^/]+?)(?:\.git)?\/?$/i);
  if (ssh) {
    const host = ssh[1].toLowerCase();
    const owner = ssh[2];
    const repo = stripGitSuffix(ssh[3]);
    return {
      provider: "github",
      owner,
      repo,
      apiBase: host === "github.com" ? "" : `https://${host}/api/v3`,
    };
  }

  try {
    const u = new URL(raw.includes("://") ? raw : `https://${raw}`);
    const host = u.hostname.toLowerCase();
    if (host !== "github.com" && !host.endsWith(".github.com")) return null;

    const parts = u.pathname.split("/").filter(Boolean);
    if (parts.length < 2) return null;

    const owner = parts[0];
    const repo = stripGitSuffix(parts[1]);
    let branch = "";
    let pathPrefix = "";

    if (parts[2] === "tree" || parts[2] === "blob") {
      branch = decodeURIComponent(parts[3] || "");
      pathPrefix = normalizePathPrefix(parts.slice(4).map(decodeURIComponent).join("/"));
    }

    const apiBase = host === "github.com" ? "" : `https://${host}/api/v3`;

    return { provider: "github", owner, repo, branch, pathPrefix, apiBase };
  } catch {
    return null;
  }
}

export function parseGitLabRepoUrl(input: string): ParsedGitRepo | null {
  const raw = input.trim();
  if (!raw) return null;

  const ssh = raw.match(/^git@([\w.-]+):(.+?)(?:\.git)?\/?$/i);
  if (ssh) {
    const host = ssh[1].toLowerCase();
    const pathParts = ssh[2].split("/").filter(Boolean);
    if (pathParts.length < 2) return null;
    const repo = stripGitSuffix(pathParts[pathParts.length - 1]);
    const owner = pathParts.slice(0, -1).join("/");
    const apiBase =
      host === "gitlab.com" ? "" : `https://${host}/api/v4`;
    return { provider: "gitlab", owner, repo, apiBase };
  }

  try {
    const u = new URL(raw.includes("://") ? raw : `https://${raw}`);
    const host = u.hostname.toLowerCase();
    let path = u.pathname;
    const apiBase = host === "gitlab.com" ? "" : `https://${host}/api/v4`;

    const treeIdx = path.indexOf("/-/tree/");
    const blobIdx = path.indexOf("/-/blob/");
    const markerIdx = treeIdx >= 0 ? treeIdx : blobIdx;
    let branch = "";
    let pathPrefix = "";
    if (markerIdx >= 0) {
      const after = path.slice(markerIdx + (treeIdx >= 0 ? "/-/tree/".length : "/-/blob/".length));
      const segs = after.split("/").filter(Boolean);
      branch = decodeURIComponent(segs[0] || "");
      pathPrefix = normalizePathPrefix(segs.slice(1).map(decodeURIComponent).join("/"));
      path = path.slice(0, markerIdx);
    }

    const parts = path.split("/").filter(Boolean);
    if (parts.length < 2) return null;
    const repo = stripGitSuffix(parts[parts.length - 1]);
    const owner = parts.slice(0, -1).join("/");

    return { provider: "gitlab", owner, repo, branch, pathPrefix, apiBase };
  } catch {
    return null;
  }
}

export function parseGitRepoUrl(
  input: string,
  provider?: "github" | "gitlab",
): ParsedGitRepo | null {
  if (provider === "gitlab") return parseGitLabRepoUrl(input);
  if (provider === "github") return parseGitHubRepoUrl(input);
  return parseGitHubRepoUrl(input) ?? parseGitLabRepoUrl(input);
}

export function formatGitHubRepoUrl(data: {
  owner: string;
  repo: string;
  branch?: string;
  pathPrefix?: string;
  apiBase?: string;
}): string {
  const owner = data.owner.trim();
  const repo = data.repo.trim();
  if (!owner || !repo) return "";

  let host = "github.com";
  const base = (data.apiBase || "").trim();
  if (base) {
    try {
      host = new URL(base).hostname;
    } catch {
      /* keep default */
    }
  }

  let url = `https://${host}/${owner}/${repo}`;
  const branch = (data.branch || "").trim();
  const prefix = (data.pathPrefix || "").trim().replace(/\/$/, "");
  if (branch) {
    url += `/tree/${encodeURIComponent(branch)}`;
    if (prefix) url += `/${prefix}`;
  }
  return url;
}

export function formatGitLabRepoUrl(data: {
  owner: string;
  repo: string;
  branch?: string;
  pathPrefix?: string;
  apiBase?: string;
}): string {
  const owner = data.owner.trim();
  const repo = data.repo.trim();
  if (!owner || !repo) return "";

  let host = "gitlab.com";
  const base = (data.apiBase || "").trim();
  if (base) {
    try {
      host = new URL(base).hostname;
    } catch {
      /* keep default */
    }
  }

  let url = `https://${host}/${owner}/${repo}`;
  const branch = (data.branch || "").trim();
  const prefix = (data.pathPrefix || "").trim().replace(/\/$/, "");
  if (branch) {
    url += `/-/tree/${encodeURIComponent(branch)}`;
    if (prefix) url += `/${prefix}`;
  }
  return url;
}

export function formatGitRepoUrl(data: GitSourceFormFields): string {
  return data.provider === "gitlab"
    ? formatGitLabRepoUrl(data)
    : formatGitHubRepoUrl(data);
}

export function applyParsedRepoToForm(
  parsed: ParsedGitRepo,
  current: GitSourceFormFields,
): Partial<GitSourceFormFields> {
  const patch: Partial<GitSourceFormFields> = {
    provider: parsed.provider,
    owner: parsed.owner,
    repo: parsed.repo,
    apiBase: parsed.apiBase ?? "",
  };
  if (parsed.branch !== undefined) patch.branch = parsed.branch;
  if (parsed.pathPrefix !== undefined) patch.pathPrefix = parsed.pathPrefix;
  if (!current.name.trim()) patch.name = parsed.repo;
  return patch;
}

export function gitSourceValidationError(
  data: GitSourceFormFields,
  opts?: { requireToken?: boolean; isEditing?: boolean },
): string | null {
  if (!data.owner.trim() || !data.repo.trim()) {
    return data.provider === "github"
      ? "请填写有效的 GitHub 项目地址"
      : "请填写有效的 GitLab 项目地址，或填写 Owner 与仓库名";
  }
  if (!data.name.trim()) {
    return "请填写显示名称";
  }
  if (opts?.requireToken && !opts?.isEditing && !data.token.trim()) {
    return "新建代码源时必须填写访问令牌";
  }
  return null;
}

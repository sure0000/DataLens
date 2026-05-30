import { shouldShowApiSourceInKb } from "../components/knowledge-bases/apiSourceMatching";
import type {
  ApiSource,
  DatabaseImport,
  DocRow,
  Entry,
  GitSource,
  KB,
} from "../components/knowledge-bases/types";
import { api } from "./api";

export type KbSourcesSnapshot = {
  kb: KB;
  entries: Entry[];
  gitSources: GitSource[];
  apiSources: ApiSource[];
  documents: DocRow[];
  databaseImports: DatabaseImport[];
};

/** 拉取知识库导入源全量快照（用于 state 更新，不触发整页 loading） */
export async function fetchKbSourcesSnapshot(kbId: number): Promise<KbSourcesSnapshot> {
  const [res, gitRes, kbApiRes, globalApiRes, docsRes, dbRes] = await Promise.all([
    api<{ knowledge_base: KB; entries: Entry[] }>(`/api/knowledge-bases/${kbId}`),
    api<{ git_sources: GitSource[] }>(`/api/knowledge-bases/${kbId}/git-sources`).catch(() => ({
      git_sources: [] as GitSource[],
    })),
    api<{ api_sources: ApiSource[] }>(`/api/knowledge-bases/${kbId}/api-sources`).catch(() => ({
      api_sources: [] as ApiSource[],
    })),
    api<{ api_sources: ApiSource[] }>(`/api/api-sources`).catch(() => ({
      api_sources: [] as ApiSource[],
    })),
    api<{ documents: DocRow[] }>(`/api/knowledge-bases/${kbId}/documents`).catch(() => ({
      documents: [] as DocRow[],
    })),
    api<{ imports: DatabaseImport[] }>(`/api/knowledge-bases/${kbId}/database-imports`).catch(
      () => ({ imports: [] as DatabaseImport[] }),
    ),
  ]);

  const entries = res.entries ?? [];
  const docs = docsRes.documents ?? [];
  const mergedApi = [...(kbApiRes.api_sources ?? [])];
  const seen = new Set(mergedApi.map((s) => s.id));
  for (const s of globalApiRes.api_sources ?? []) {
    if (seen.has(s.id)) continue;
    if (!shouldShowApiSourceInKb(s, entries, docs)) continue;
    mergedApi.push(s);
  }

  return {
    kb: res.knowledge_base,
    entries,
    gitSources: gitRes.git_sources ?? [],
    apiSources: mergedApi,
    documents: docs,
    databaseImports: dbRes.imports ?? [],
  };
}

/** 轮询用：仅更新条目与文档 */
export async function fetchKbEntriesAndDocuments(
  kbId: number,
): Promise<{ entries: Entry[]; documents: DocRow[] }> {
  const [kbRes, docsRes] = await Promise.all([
    api<{ entries: Entry[] }>(`/api/knowledge-bases/${kbId}`),
    api<{ documents: DocRow[] }>(`/api/knowledge-bases/${kbId}/documents`),
  ]);
  return {
    entries: kbRes.entries ?? [],
    documents: docsRes.documents ?? [],
  };
}

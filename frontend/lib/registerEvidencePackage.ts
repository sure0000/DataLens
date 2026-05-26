import { api } from "./api";
import type { AssetKind, ConnectorKind } from "../components/knowledge-bases/ingestionTypes";

/** 登记持久化证据包（导入层契约） */
export async function registerEvidencePackage(
  kbId: number,
  payload: {
    asset_kind: AssetKind;
    connector: ConnectorKind;
    title: string;
    source_ref?: Record<string, unknown>;
    linked_entry_ids?: number[];
    processing_state?: string;
  },
) {
  return api<{ ok: boolean; package: Record<string, unknown> }>(
    `/api/knowledge-bases/${kbId}/ingestion/packages`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

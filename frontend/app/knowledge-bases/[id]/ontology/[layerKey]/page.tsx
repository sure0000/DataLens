import { redirect } from "next/navigation";

/** 遗留五层详情页 → 知识库「建模与质量」区块 */
export default function OntologyLayerRedirectPage({
  params,
}: {
  params: { id: string; layerKey: string };
}) {
  redirect(`/knowledge-bases/${params.id}#modeling`);
}

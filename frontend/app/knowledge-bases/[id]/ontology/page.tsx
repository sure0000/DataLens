import { redirect } from "next/navigation";
import { isOntologyBrowseTab, ontologyUrl } from "../../../../lib/ontologyRoutes";

/** 遗留路由 → canonical /ontology?kb= 或知识库 #modeling */
export default function KnowledgeBaseOntologyRedirect({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams: { tab?: string };
}) {
  const kbId = Number(params.id);
  if (!Number.isFinite(kbId)) {
    redirect("/ontology");
  }

  const tab = searchParams?.tab;

  if (tab === "governance") {
    redirect(`/knowledge-bases/${kbId}#modeling`);
  }

  if (tab && isOntologyBrowseTab(tab)) {
    redirect(ontologyUrl({ kbId, tab }));
  }

  redirect(ontologyUrl({ kbId }));
}

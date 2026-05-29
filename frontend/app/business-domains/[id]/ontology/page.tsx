import { redirect } from "next/navigation";

/** 遗留路由 → 全局语义资产页（使用侧栏当前业务域） */
export default function DomainOntologyRedirect({
  searchParams,
}: {
  params: { id: string };
  searchParams: { [key: string]: string | string[] | undefined };
}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(searchParams)) {
    if (typeof value === "string") params.set(key, value);
  }
  const q = params.toString();
  redirect(q ? `/ontology?${q}` : "/ontology");
}

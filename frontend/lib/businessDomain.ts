export type BusinessDomainOption = {
  id: number;
  name: string;
  is_builtin?: boolean;
};

const ACTIVE_DOMAIN_KEY = "datalens_active_business_domain_id_v1";
const DOMAIN_UPDATED_EVENT = "datalens-business-domain-updated";

function parseId(raw: string | null): number | null {
  if (!raw) return null;
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n;
}

export function getActiveBusinessDomainId(): number | null {
  if (typeof window === "undefined") return null;
  return parseId(window.localStorage.getItem(ACTIVE_DOMAIN_KEY));
}

export function setActiveBusinessDomainId(domainId: number | null): void {
  if (typeof window === "undefined") return;
  if (domainId == null) {
    window.localStorage.removeItem(ACTIVE_DOMAIN_KEY);
  } else {
    window.localStorage.setItem(ACTIVE_DOMAIN_KEY, String(domainId));
  }
  emitBusinessDomainUpdated();
}

export function getBusinessDomainUpdatedEventName(): string {
  return DOMAIN_UPDATED_EVENT;
}

export function emitBusinessDomainUpdated(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(DOMAIN_UPDATED_EVENT));
}

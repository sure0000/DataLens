"use client";

import { useEffect, useState } from "react";
import {
  getActiveBusinessDomainId,
  getBusinessDomainUpdatedEventName,
} from "../lib/businessDomain";

/** 订阅侧栏当前业务域；切换时 domainId 更新，无需整页刷新。 */
export function useBusinessDomain(): number | null {
  const [domainId, setDomainId] = useState<number | null>(() =>
    typeof window !== "undefined" ? getActiveBusinessDomainId() : null
  );

  useEffect(() => {
    const sync = () => setDomainId(getActiveBusinessDomainId());
    sync();
    const evt = getBusinessDomainUpdatedEventName();
    window.addEventListener(evt, sync);
    return () => window.removeEventListener(evt, sync);
  }, []);

  return domainId;
}

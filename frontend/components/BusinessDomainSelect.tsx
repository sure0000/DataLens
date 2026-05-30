"use client";

import { Icon } from "./AppIcons";
import type { BusinessDomainOption } from "../lib/businessDomain";

type Props = {
  domains: BusinessDomainOption[];
  value: number | null;
  onChange: (domainId: number | null) => void;
  /** 侧栏折叠时仅显示图标，点击展开原生选择 */
  compact?: boolean;
};

export default function BusinessDomainSelect({ domains, value, onChange, compact = false }: Props) {
  const current = domains.find((d) => d.id === value);

  if (compact) {
    return (
      <div
        className="app-domain-select-wrap relative mx-auto h-9 w-9"
        title={current ? `当前业务域：${current.name}` : "选择业务域"}
      >
        <select
          className="app-domain-select app-domain-select--icon-only"
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
          aria-label={current ? `当前业务域：${current.name}` : "选择业务域"}
        >
          {domains.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
        <span
          className="app-control-button pointer-events-none flex h-9 w-9 items-center justify-center p-0"
          aria-hidden
        >
          <Icon name="domain" className="h-4 w-4" />
        </span>
      </div>
    );
  }

  return (
    <div className="app-domain-select-wrap mt-1">
      <Icon name="domain" className="app-field__adorn app-field__adorn--start h-3.5 w-3.5" />
      <select
        className="app-domain-select w-full"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
        aria-label="当前业务域"
      >
        {domains.map((d) => (
          <option key={d.id} value={d.id}>
            {d.name}
          </option>
        ))}
      </select>
      <Icon name="chevronDown" className="app-field__adorn app-field__adorn--end h-4 w-4" />
    </div>
  );
}

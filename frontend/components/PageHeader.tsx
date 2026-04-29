"use client";

import type { ReactNode } from "react";
import Breadcrumbs, { type BreadcrumbItem } from "./Breadcrumbs";

type PageHeaderProps = {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  meta?: ReactNode;
  breadcrumbs?: BreadcrumbItem[];
};

export default function PageHeader({ title, subtitle, actions, meta, breadcrumbs = [] }: PageHeaderProps) {
  return (
    <header className="app-page-header">
      <div>
        {!!breadcrumbs.length && <Breadcrumbs items={breadcrumbs} />}
        <h1 className="app-page-title">{title}</h1>
        {subtitle ? <p className="app-page-subtitle">{subtitle}</p> : null}
        {meta ? <div className="mt-1 text-xs app-text-muted">{meta}</div> : null}
      </div>
      {actions ? <div className="app-page-header-actions">{actions}</div> : null}
    </header>
  );
}

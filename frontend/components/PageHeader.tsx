"use client";

import type { ReactNode } from "react";
import Breadcrumbs, { type BreadcrumbItem } from "./Breadcrumbs";

type PageHeaderProps = {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  /** 若为 true，将 actions 整块放在副标题（说明）下方，并保持整行铺满 */
  actionsBelowSubtitle?: boolean;
  meta?: ReactNode;
  breadcrumbs?: BreadcrumbItem[];
};

export default function PageHeader({
  title,
  subtitle,
  actions,
  actionsBelowSubtitle = false,
  meta,
  breadcrumbs = []
}: PageHeaderProps) {
  if (actionsBelowSubtitle) {
    return (
      <header className="app-page-header">
        <div className="min-w-0 w-full">
          {!!breadcrumbs.length && <Breadcrumbs items={breadcrumbs} />}
          <h1 className="app-page-title">{title}</h1>
          {subtitle ? <p className="app-page-subtitle">{subtitle}</p> : null}
          {meta ? <div className="mt-1 text-xs app-text-muted">{meta}</div> : null}
          {actions ? <div className="app-page-header-toolbar-row mt-3 w-full min-w-0">{actions}</div> : null}
        </div>
      </header>
    );
  }

  return (
    <header className="app-page-header">
      <div className="min-w-0">
        {!!breadcrumbs.length && <Breadcrumbs items={breadcrumbs} />}
        <h1 className="app-page-title">{title}</h1>
        {subtitle ? <p className="app-page-subtitle">{subtitle}</p> : null}
        {meta ? <div className="mt-1 text-xs app-text-muted">{meta}</div> : null}
      </div>
      {actions ? <div className="app-page-header-actions">{actions}</div> : null}
    </header>
  );
}

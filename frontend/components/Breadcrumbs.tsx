"use client";

import Link from "next/link";

export type BreadcrumbItem = {
  label: string;
  href?: string;
};

export default function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  if (!items.length) return null;
  return (
    <nav aria-label="面包屑导航" className="app-breadcrumbs">
      {items.map((item, idx) => {
        const isLast = idx === items.length - 1;
        return (
          <span key={`${item.label}-${idx}`} className="app-breadcrumb-item">
            {item.href && !isLast ? (
              <Link href={item.href} className="app-breadcrumb-link">
                {item.label}
              </Link>
            ) : (
              <span className={isLast ? "app-breadcrumb-current" : "app-breadcrumb-text"}>{item.label}</span>
            )}
            {!isLast ? <span className="app-breadcrumb-sep">/</span> : null}
          </span>
        );
      })}
    </nav>
  );
}

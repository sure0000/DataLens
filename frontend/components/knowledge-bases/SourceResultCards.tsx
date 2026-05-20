"use client";

import type { OutputCardData } from "./types";

interface SourceResultCardsProps {
  cards: OutputCardData[];
  onViewAll?: (cardId: string) => void;
}

export default function SourceResultCards({ cards, onViewAll }: SourceResultCardsProps) {
  if (cards.length === 0) {
    return (
      <section className="mt-4 app-card p-4">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-lg">📄</span>
          <h2 className="app-section-title">本资料源产出</h2>
        </div>
        <p className="text-sm text-app-muted">
          暂无产出数据。清洗流水线完成后，术语和指标将在此展示。
        </p>
      </section>
    );
  }

  return (
    <section className="mt-4 space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-lg">📄</span>
        <h2 className="app-section-title">本资料源产出</h2>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((card) => {
          const iconSvg = card.icon === "terms" ? (
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6 4h5a2 2 0 012 2v14a2 2 0 00-2-2H6V4zM13 4h5v14h-5a2 2 0 00-2 2V6a2 2 0 012-2z" />
            </svg>
          ) : (
            <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="20" x2="18" y2="10" />
              <line x1="12" y1="20" x2="12" y2="4" />
              <line x1="6" y1="20" x2="6" y2="14" />
            </svg>
          );

          return (
            <div key={card.id} className="app-card flex flex-col gap-3 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="app-text-accent">{iconSvg}</span>
                  <h3 className="text-sm font-semibold text-app-primary">{card.label}</h3>
                </div>
                <span className="text-xs text-app-muted">{card.totalCount} 项</span>
              </div>

              {card.previews.length > 0 && (
                <div className="space-y-1.5">
                  {card.previews.map((p, i) => (
                    <div key={i} className="flex items-center justify-between text-xs">
                      <span className="text-app-primary truncate">{p.text}</span>
                      <span className="shrink-0 ml-2 text-app-muted">
                        {p.subtext && (
                          <span className="mr-2 text-[11px]">{p.subtext}</span>
                        )}
                        {p.confidence != null && (
                          <span
                            className={`text-[11px] font-medium ${
                              p.confidence >= 80
                                ? "app-text-success"
                                : p.confidence >= 50
                                ? "text-amber-600"
                                : "text-app-muted"
                            }`}
                          >
                            {Math.round(p.confidence)}%
                          </span>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {card.totalCount > 3 && (
                <button className="app-link text-xs self-start" type="button" onClick={() => onViewAll?.(card.id)}>
                  查看全部 →
                </button>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

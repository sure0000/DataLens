"use client";

interface IriBreadcrumbProps {
  iri: string;
  onClickSegment?: (segmentIndex: number, fullPath: string) => void;
}

export default function IriBreadcrumb({ iri, onClickSegment }: IriBreadcrumbProps) {
  if (!iri) return null;

  const url = iri.replace(/^<|>$/g, "");
  const segments = url.split("/").filter(Boolean);
  const last = segments[segments.length - 1];

  if (segments.length === 0) {
    return (
      <code className="text-[11px] font-mono text-app-muted">{url}</code>
    );
  }

  // Build scheme + host
  const scheme = segments[0].includes(":") ? segments[0] : null;
  const schemeDisplay = scheme ? scheme.replace(/:$/, "://") : null;

  return (
    <nav aria-label="IRI path" className="inline-flex flex-wrap items-center gap-x-0.5 text-[11px] font-mono">
      {schemeDisplay && (
        <span className="text-app-muted select-none">{schemeDisplay}</span>
      )}
      {schemeDisplay && <Separator />}
      {segments.slice(scheme ? 1 : 0).map((seg, i) => {
        const absoluteIndex = scheme ? i + 1 : i;
        const fullPath = segments.slice(0, absoluteIndex + 1).join("/");
        const isLast = absoluteIndex === segments.length - 1;

        return (
          <span key={`${seg}-${absoluteIndex}`} className="inline-flex items-center gap-x-0.5">
            {i > 0 && <Separator />}
            {onClickSegment && !isLast ? (
              <button
                type="button"
                className="text-app-link hover:underline cursor-pointer bg-transparent border-0 p-0"
                onClick={() => onClickSegment(absoluteIndex, fullPath)}
              >
                {seg}
              </button>
            ) : (
              <span className={isLast ? "text-app-primary font-semibold" : "text-app-muted"}>
                {seg}
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}

function Separator() {
  return <span className="text-app-muted/50 select-none mx-0.5">/</span>;
}

"use client";

type AnswerSection = {
  title: string;
  lines: string[];
};

function parseAnswerSections(raw: string): AnswerSection[] {
  const sectionTitles = new Set(["结论", "说明", "下一步", "边界", "可替代问题", "判断依据"]);
  const lines = raw.replace(/\r/g, "").split("\n");
  const sections: AnswerSection[] = [];
  let current: AnswerSection | null = null;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (sectionTitles.has(trimmed)) {
      current = { title: trimmed, lines: [] };
      sections.push(current);
      continue;
    }
    if (!current) {
      current = { title: "说明", lines: [] };
      sections.push(current);
    }
    current.lines.push(trimmed);
  }

  return sections;
}

type Props = {
  answer?: string;
  explanation?: string;
  showExplanation?: boolean;
};

const SECTION_ACCENT: Record<string, { badge: string; text: string }> = {
  结论: { badge: "bg-[#111827] text-white", text: "text-[#111827]" },
  说明: { badge: "bg-[#e0f2fe] text-[#0369a1]", text: "text-[#374151]" },
  下一步: { badge: "bg-[#dcfce7] text-[#15803d]", text: "text-[#374151]" },
  边界: { badge: "bg-[#fef9c3] text-[#854d0e]", text: "text-[#374151]" },
  可替代问题: { badge: "bg-[#f3e8ff] text-[#7e22ce]", text: "text-[#374151]" },
  判断依据: { badge: "bg-[#ede9fe] text-[#5b21b6]", text: "text-[#374151]" },
};

function SectionBlock({ section, isConclusion = false }: { section: AnswerSection; isConclusion?: boolean }) {
  const accent = SECTION_ACCENT[section.title] ?? { badge: "bg-[#f3f4f6] text-[#374151]", text: "text-[#374151]" };
  return (
    <div className={isConclusion ? "rounded-xl border border-[#e5e7eb] bg-[#f9fafb] p-3" : ""}>
      <span className={`inline-block rounded-md px-2 py-0.5 text-xs font-semibold ${accent.badge}`}>
        {section.title}
      </span>
      <div className="mt-2 space-y-1.5">
        {section.lines.map((line, lineIdx) => {
          const content = line.replace(/^[-*•]\s*/, "");
          return (
            <p
              key={`${section.title}-${lineIdx}`}
              className={`break-words leading-6 ${isConclusion ? "text-base font-medium text-[#111827]" : `text-sm ${accent.text}`}`}
            >
              {!isConclusion && <span className="mr-1.5 text-[#9ca3af]">·</span>}
              {content}
            </p>
          );
        })}
      </div>
    </div>
  );
}

export default function AssistantStructuredAnswer({ answer, explanation, showExplanation = true }: Props) {
  const answerText = (answer || "已返回结果。").trim();
  const explanationText = (explanation || "").trim();
  const answerSections = parseAnswerSections(answerText);
  const explanationSections = parseAnswerSections(explanationText);
  const shouldShowExplanation = showExplanation && explanationText.length > 0;

  return (
    <div className="space-y-3">
      {answerSections.length ? (
        answerSections.map((section, idx) => (
          <SectionBlock
            key={`${section.title}-${idx}`}
            section={section}
            isConclusion={section.title === "结论"}
          />
        ))
      ) : (
        <p className="whitespace-pre-wrap break-words text-sm leading-7 text-[#111827]">{answerText}</p>
      )}

      {shouldShowExplanation && (
        <div className="space-y-2.5 rounded-xl border border-[#ddd6fe] bg-[#f5f3ff] p-3">
          {explanationSections.length ? (
            explanationSections.map((section, idx) => (
              <SectionBlock key={`exp-${section.title}-${idx}`} section={section} />
            ))
          ) : (
            <>
              <span className="inline-block rounded-md bg-[#ede9fe] px-2 py-0.5 text-xs font-semibold text-[#5b21b6]">
                判断依据
              </span>
              <p className="whitespace-pre-wrap break-words text-sm leading-7 text-[#374151]">{explanationText}</p>
            </>
          )}
        </div>
      )}
    </div>
  );
}

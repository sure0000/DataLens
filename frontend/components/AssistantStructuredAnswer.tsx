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

function SectionBlock({ section }: { section: AnswerSection }) {
  return (
    <div>
      <p className="text-xs font-semibold tracking-wide text-[#4b5563]">{section.title}</p>
      <div className="mt-2 space-y-1.5">
        {section.lines.map((line, lineIdx) => {
          const content = line.replace(/^[-*•]\s*/, "");
          return (
            <p key={`${section.title}-${lineIdx}`} className="break-words text-sm leading-6 text-[#111827]">
              <span className="mr-1 text-[#6b7280]">-</span>
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
    <div className="space-y-2">
      {answerSections.length ? (
        answerSections.map((section, idx) => <SectionBlock key={`${section.title}-${idx}`} section={section} />)
      ) : (
        <p className="whitespace-pre-wrap break-words text-sm leading-7 text-[#111827]">{answerText}</p>
      )}

      {shouldShowExplanation && (
        <div className="space-y-2 rounded-xl border border-[#ddd6fe] bg-[#f5f3ff] p-3">
          <p className="text-xs font-semibold tracking-wide text-[#5b21b6]">判断依据</p>
          {explanationSections.length ? (
            explanationSections.map((section, idx) => <SectionBlock key={`exp-${section.title}-${idx}`} section={section} />)
          ) : (
            <p className="whitespace-pre-wrap break-words text-sm leading-7 text-[#312e81]">{explanationText}</p>
          )}
        </div>
      )}
    </div>
  );
}

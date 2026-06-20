/**
 * Private/PII term → placeholder map for test fixtures.
 *
 * Single source of truth: scripts/redact-map.json. This file mirrors the
 * mapping so tests can import it without runtime file reads. A governance
 * check (scripts/checks/private-info-redaction-sync.mjs) keeps the two in
 * sync.
 *
 * WHY: KBPrep is open-source. Real private information (personal names,
 * brand names, social handles, UIDs, revenue figures) must not appear in
 * version-controlled test data. Generic Chinese marketing terms
 * (公众号/扫码/入群/训练营 etc.) are legitimate cleaning-rule test samples
 * and are intentionally NOT redacted.
 *
 * Replacement order matters: longer keys are replaced before shorter ones
 * (e.g. "生财AI宝典" before "生财") so partial matches do not leak.
 */
export const REDACT_MAP: Record<string, string> = {
  "生财AI宝典": "ExampleCourse",
  "《生财AI宝典》": "《ExampleCourse》",
  "普通人的AI应用宝典": "ExampleCourseManual",
  "生财有术在AI领域看到的3个超级机会": "ExampleCommunityInsight",
  "生财有术": "ExampleCommunity",
  "生财准备": "ExampleCommunityPrep",
  "生财围绕": "ExampleCommunityAction",
  "生财": "ExampleCommunity",
  "花叔 译": "ExampleAuthor (trans.)",
  "B 站花叔v": "ExampleAuthor",
  "B站花叔v": "ExampleAuthor",
  "B 站花叔": "ExampleAuthor",
  "B站花叔": "ExampleAuthor",
  "花叔": "ExampleAuthor",
  "huasheng.ai": "example.com",
  "@AlchainHust": "@ExampleHandle",
  "@Alchain": "@ExampleHandle",
  "Alchain": "ExampleHandle",
  "space.bilibili.com/14097567": "space.bilibili.com/12345678",
  "14097567": "12345678",
  "亦仁": "ExampleFounder1",
  "@代一": "@ExampleFounder2",
  "代一": "ExampleFounder2",
  "@阿彪": "@ExampleStaff1",
  "阿彪": "ExampleStaff1",
  "Pollo AI": "ExampleVendor",
  "1400万美元": "ExampleRevenue1",
  "千万美金": "ExampleRevenue2",
  "月入3万": "ExampleRevenue3",
  "高客单赛道视频号矩阵单日获客1000+": "ExampleMarketingClaim",
  "海外 AI 自媒体博主": "ExamplePersona1",
  "海外AI自媒体博主": "ExamplePersona1",
  "AI+流量创业者": "ExamplePersona2",
  "连续创业者": "ExamplePersona3",
  "Gary": "ExampleCreator",
  "AI随风随风": "ExampleCreator2",
  "创始人行动手册": "ExampleProgramTitle",
  "AI超级标": "ExampleProgram1",
  "AI航海体系": "ExampleProgram2",
  "AI问答助手": "ExampleProgram3",
  "圈友": "ExampleMember",
  "SCAI": "ExampleOrg",
  "介绍一下我自己": "Let me introduce myself",
};

const SORTED_ENTRIES = Object.entries(REDACT_MAP).sort(
  (a, b) => b[0].length - a[0].length,
);

/** Replace every private term in ``text`` with its placeholder. */
export function redact(text: string): string {
  let out = text;
  for (const [real, placeholder] of SORTED_ENTRIES) {
    out = out.split(real).join(placeholder);
  }
  return out;
}

export const PRIVATE_TERMS: readonly string[] = Object.keys(REDACT_MAP);

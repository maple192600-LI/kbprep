"""Private/PII term to placeholder map for Python test fixtures.

Single source of truth: scripts/redact-map.json. This module mirrors the
mapping so tests can import it without runtime file reads. A governance
check keeps the two in sync.

KBPrep is open-source. Real private information must not appear in
version-controlled test data. Generic Chinese marketing terms are
legitimate cleaning-rule test samples and are intentionally NOT redacted.
"""
from __future__ import annotations

REDACT_MAP: dict[str, str] = {
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
}

# Replace longest keys first so partial matches (e.g. "生财" inside "生财AI宝典")
# do not leak.
_SORTED_ITEMS = sorted(REDACT_MAP.items(), key=lambda kv: len(kv[0]), reverse=True)


def redact(text: str) -> str:
    """Replace every private term in ``text`` with its placeholder."""
    for real, placeholder in _SORTED_ITEMS:
        text = text.replace(real, placeholder)
    return text


PRIVATE_TERMS: list[str] = list(REDACT_MAP)

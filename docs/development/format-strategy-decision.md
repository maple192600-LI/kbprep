# Format Strategy Decision

> 这是 owner 当前的格式策略决策，是开发顺序的约束，不是临时建议。
> 任何与本文档冲突的旧计划/旧描述，以本文档为准。
> 代码级 capability 真源仍是 `python/kbprep_worker/converter_capabilities.py`；本文档规定的是**投入优先级**，不改 capability 路由。

## 一句话总览

| 格式 | 策略 |
| --- | --- |
| DOCX | 深做（重点提升对象） |
| EPUB | 默认 XHTML 直接解析，不默认转 PDF |
| PPTX | 轻量（正文/标题/备注/大纲，清营销噪音） |
| XLSX | 轻量（工作表/简单表格/关键文本） |
| Legacy Office (.doc/.ppt/.xls) | 不支持，提示转 PDF 或新版 Office |
| 图片 / 音视频 / YouTube | 证据门控，不因"能跑"就宣传为稳定能力 |

## DOCX（深做）

做什么：继续提升结构、段落、表格、来源定位（SourceSpan）、清理效果。
不做什么：（无特殊限制，是主要投入方向）。
capability：归在 `office_xml`（partial），是 office_xml 内部的**重点提升对象**。

**进展（2026-06-30，格式策略 ② 落地）**：DOCX 转换器已支持外部超链接（`.rels` 解析）、有序/无序列表（`numbering.xml`）、`gridSpan`/`vMerge` 合并单元格、bold/italic/strike 字符样式；golden fixture + 端到端断言验证这些结构穿完整清理 pipeline 保留。仍 partial：待更广真实 DOCX 样本证明保真度后提 verified。已知保真度限制（Markdown 固有）：合并单元格值重复、单元格内多段落合并为一行；headers/footers、脚注、目录不在范围。

## EPUB（直接解析，不默认转 PDF）

做什么：继续提升 XHTML 章节解析质量（脚注、复杂表格、自定义 XHTML 的 fixtures）。
不做什么：不默认把 EPUB 转 PDF。只有当用户**手工判断**某本 EPUB 解析很差时，才允许作为临时备选转 PDF。
capability：`epub_xhtml`（partial），默认路线是本地 XHTML 提取，不走 MinerU/PDF。

## PPTX（轻量）

做什么：提取每页正文、标题、备注、可读大纲；清掉营销噪音。
不做什么：不追求复杂版式、动画、图表、视觉还原；不把 PPTX 当深度精细化重点；不追加复杂 relationship 语义（如 PPTX shape `embeds`/notes `annotates`）——这些只在 owner 重开 PPTX 深度语义时才做。
capability：归在 `office_xml`（partial），定位为**轻量可用**。已 shipped 的 converter-native SourceSpan（slide/shape 定位）属于轻量范围内可用的基础精度，不在此之上追加复杂版式/图表工作。

## XLSX（轻量）

做什么：识别工作表、简单表格、关键文本。
不做什么：不把复杂/庞大表格当优质知识库来源深挖；不追加复杂工作簿语义工作。
capability：归在 `office_xml`（partial），定位为**轻量可用**，非知识库主来源。

## Legacy Office（不支持）

做什么：不支持，拒绝输入并明确提示用户转 PDF 或新版 Office（.docx/.pptx/.xlsx）。
不做什么：不实现桥接转换；不给它做 fixture 工作。
capability：`legacy_office_pdf_bridge`（unsupported，owner declined adaptation）。

## 图片 / 音视频 / YouTube（证据门控）

做什么：继续补真实 fixtures 和证据，达到证据标准后才 promoted。
不做什么：不因为"能跑"就宣传为稳定/verified 能力。
capability：`image_ocr`（experimental）、`media_local_transcript`（partial）、`youtube_url_routes`（partial）。

## 当前开发顺序约束

关键路径：① 文档/治理锁定（本决策落地）→ ② DOCX 精细化 → ③ EPUB 结构质量提升 → ④ PPTX 轻量正文清理 → ⑤ XLSX 轻量表格/文本 → ⑥ 图片/音视频/YouTube 证据补强。

"""
classify_images - image classification.

Reads context from converted.md so image-only blocks can be classified by their
nearby paragraphs instead of by filename alone.
"""
import logging
import re
from pathlib import Path

from .rule_loader import LoadedCleaningRules, load_cleaning_rules

logger = logging.getLogger(__name__)


def classify_images(
    blocks: list[dict],
    run_dir: str,
    profile: str = "standard",
    document_type: str = "",
    rule_templates: list[str] | tuple[str, ...] | None = None,
) -> list[dict]:
    """
    Classify images based on context from converted.md.
    Reads the original converted.md to find surrounding text for each image.
    """
    run_p = Path(run_dir)
    rules = load_cleaning_rules(
        profile=profile,
        document_type=document_type,
        templates=tuple(rule_templates or ()),
    )
    img_context_map = _load_image_context_map(run_p)

    for block in blocks:
        _classify_image_block(block, img_context_map, rules)

    return blocks


def _load_image_context_map(run_p: Path) -> dict[str, str]:
    converted_path = run_p / "converted.md"
    if not converted_path.exists():
        return {}
    converted_text = converted_path.read_text(encoding="utf-8")
    return _build_image_context_map(converted_text) if converted_text else {}


def _classify_image_block(block: dict, img_context_map: dict[str, str], rules: LoadedCleaningRules) -> None:
    block_type = block.get("type", "")
    images = block.get("images", [])
    if not images or block_type not in ("image_evidence", "image_operation", "diagram", "unknown_review"):
        return

    heading_path = block.get("heading_path")
    heading_path = heading_path if isinstance(heading_path, list) else []
    combined = _combined_image_context(block, images, heading_path, img_context_map)
    img_type, status, reason = _classify(combined, heading_path, rules)

    block["image_type"] = img_type
    if block.get("status") != "discard":
        block["status"] = status
    block["reason"] = reason


def _combined_image_context(
    block: dict,
    images: list[dict],
    heading_path: list,
    img_context_map: dict[str, str],
) -> str:
    all_context = [
        img_context_map.get(img.get("src", ""), "")
        for img in images
        if img_context_map.get(img.get("src", ""), "")
    ]
    heading_text = " ".join(str(part) for part in heading_path)
    return block.get("text", "") + " " + " ".join(all_context) + " " + heading_text


def _build_image_context_map(converted_text: str) -> dict[str, str]:
    """
    Build a map of image_src -> surrounding_text from converted.md.
    Looks at 5 lines before and 3 lines after each image reference.
    """
    lines = converted_text.split("\n")
    img_re = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    context_map: dict[str, str] = {}
    context_window = 5
    context_after = 3

    for i, line in enumerate(lines):
        matches = list(img_re.finditer(line))
        if not matches:
            continue

        start = max(0, i - context_window)
        end = min(len(lines), i + context_after + 1)
        context_lines = []
        for j in range(start, end):
            if j != i:
                context_lines.append(lines[j].strip())

        context = " ".join(line for line in context_lines if line)

        for match in matches:
            src = match.group(2)
            if src not in context_map:
                context_map[src] = context
            else:
                context_map[src] += " " + context

    return context_map


def _classify(text: str, heading_path: list[str] | None = None, rules: LoadedCleaningRules | None = None) -> tuple[str, str, str]:
    """Classify based on combined context text and heading path."""
    if not text.strip():
        return "unknown_image", "review", "no context available"

    rules = rules or load_cleaning_rules()

    if _matches_any(text, rules.image_qr_indicators):
        return "qr_image", "discard", "QR code or CTA image detected"

    if _matches_any(text, rules.image_proof_indicators):
        return "proof_screenshot", "evidence", "proof or revenue screenshot"

    if _matches_any(text, rules.image_marketing_indicators):
        return "marketing_poster", "evidence", "marketing material"

    if _matches_any(text, rules.image_operation_indicators):
        return "operation_screenshot", "keep", "operation or tutorial screenshot"

    if heading_path:
        heading_text = " ".join(heading_path).lower()
        if _matches_any(heading_text, rules.image_educational_heading_indicators):
            return "operation_screenshot", "keep", "image in educational section"

    if len(text) > 100:
        return "unknown_review", "review", f"unclassified with {len(text)} chars context"

    return "unknown_image", "review", "insufficient context for classification"


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)

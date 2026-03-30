"""AI deep review module — prompt generation, batch splitting, response parsing.

Workflow (GUI-assisted, clipboard-based):
  1. Split rows into batches (~200 per batch)
  2. For each batch, generate prompt text
  3. User copies prompt to ChatGPT via clipboard, gets response
  4. User pastes response back, script parses "ID | 修正译文"
  5. All corrections merged into final output

Also preserves AIChecker base class for future direct API integration.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

LANG_NAMES = {
    'en': '英文', 'idn': '印尼文', 'fr': '法文', 'de': '德文',
    'tr': '土耳其文', 'es': '西班牙文', 'pt': '葡萄牙文', 'ru': '俄文',
}


def _make_prompt_header(lang: str = 'en') -> str:
    lang_name = LANG_NAMES.get(lang, lang)
    return (
        f"你是一个游戏本地化质检专家。请审查以下中{lang_name}对照翻译，检查：\n"
        f"1. 错译 / {lang_name}不自然\n"
        f"2. 漏译 / 语义偏差\n"
        f"3. 代码、标签（如 {{icon1}}、[color=xxx][/color]）、占位符格式错误\n"
        f"4. 术语一致性 — 必须命中术语表中主译法或可接受变体\n"
        f"5. 语法正确性优先 — 在保证语义正确前提下优先保证语法自然\n"
        f"6. UI文本优化 — 对UI标签/按钮文案尽量简短，但不牺牲语义和语法\n"
        f"7. 字符规范化 — 将全角字符转换为半角（如：，。！？（）％＋：）\n"
        f"\n"
        f"优先级（高->低）：语义正确 > 语法正确 > 术语命中 > 文案简短\n"
        f"规则：\n"
        f"- 只列出需要修改的行\n"
        f"- 格式严格为：ID | 修正版译文\n"
        f"- 没有问题的行不要列出\n"
        f"- 如果全部没问题，回复\"无需修改\"\n\n"
    )


def _make_term_section(lang: str = 'en') -> str:
    lang_name = LANG_NAMES.get(lang, lang)
    return (
        f"---以下是本批涉及的术语表（中文 → {lang_name}）---\n"
        f"- 命中主译法或可接受变体都算正确\n"
        f"- 此批次术语默认大小写不强制\n\n"
        f"中文 | 主译法 | 可接受变体\n"
        "{{term_lines}}\n\n"
    )


@dataclass
class AICorrection:
    """A single correction from AI review."""
    row_id: int
    corrected_translation: str


@dataclass
class BatchInfo:
    """Metadata for one review batch."""
    batch_num: int
    total_batches: int
    row_ids: list[int] = field(default_factory=list)
    prompt_text: str = ''
    response_text: str = ''
    corrections: list[AICorrection] = field(default_factory=list)
    is_done: bool = False


# ─── Batch generation ─────────────────────────────────────

def split_into_batches(
    rows: list[dict],
    batch_size: int = 200,
) -> list[list[dict]]:
    """Split rows into fixed-size batches."""
    return [rows[i:i + batch_size] for i in range(0, len(rows), batch_size)]


def _extract_relevant_terms(
    batch_rows: list[dict],
    term_lookup: dict | None,
    max_terms: int = 120,
) -> list[tuple[str, str, str]]:
    """Find terms from the lookup that appear in this batch's source texts.

    Terms are ranked by hit count in this batch and truncated to max_terms
    to keep prompt size under control.
    """
    if not term_lookup:
        return []

    combined_originals = ' '.join(str(r['original']) for r in batch_rows)
    hits: list[tuple[str, str, str, int]] = []
    for cn, term_item in term_lookup.items():
        if isinstance(term_item, dict):
            primary = str(term_item.get('primary', '')).strip()
            variants = term_item.get('variants', [])
            if isinstance(variants, str):
                variants = [variants]
            variants = [str(x).strip() for x in variants if str(x).strip()]
            variant_text = ' / '.join(variants) if variants else '-'
        else:
            primary = str(term_item).strip()
            variant_text = '-'
        count = combined_originals.count(cn)
        if count > 0:
            hits.append((cn, primary, variant_text, count))

    # More frequent terms first, then longer source terms
    hits.sort(key=lambda x: (-x[3], -len(x[0])))
    top_hits = hits[:max_terms]
    return [(cn, p, v) for cn, p, v, _ in top_hits]


def _make_term_error_priority_section(batch_rows: list[dict]) -> str:
    bad_rows = [r for r in batch_rows if str(r.get('term_status', '')) == '术语有误']
    if not bad_rows:
        return ''

    lines = []
    for r in bad_rows[:120]:
        rid = r['id']
        orig = str(r['original']).replace('\n', '\\n')
        trans = str(r['translation']).replace('\n', '\\n')
        issue_types = str(r.get('term_issue_types', '')).strip() or '-'
        ui_flag = '是' if r.get('is_ui') else '否'
        lines.append(f"{rid} | {orig} | {trans} | {issue_types} | UI:{ui_flag}")

    rows_text = '\n'.join(lines)
    return (
        "---以下是机审判定“术语有误”的优先处理行---\n"
        "请优先修正这些行；对“命中术语无误”的行，仅在语义/语法明显错误时再改。\n\n"
        "ID | 原文 | 当前译文 | 术语问题类型 | 是否UI\n"
        f"{rows_text}\n\n"
    )


def format_batch_prompt(
    batch_rows: list[dict],
    batch_num: int,
    total_batches: int,
    term_lookup: dict | None = None,
    lang: str = 'en',
    max_terms: int = 120,
) -> str:
    """Generate the AI review prompt for one batch."""
    prompt = _make_prompt_header(lang)

    relevant_terms = _extract_relevant_terms(
        batch_rows, term_lookup, max_terms=max_terms
    )
    if relevant_terms:
        term_lines = '\n'.join(f"{cn} | {primary} | {variants}" for cn, primary, variants in relevant_terms)
        prompt += _make_term_section(lang).replace('{{term_lines}}', term_lines)

    prompt += _make_term_error_priority_section(batch_rows)

    lines = []
    for r in batch_rows:
        rid = r['id']
        orig = str(r['original']).replace('\n', '\\n')
        trans = str(r['translation']).replace('\n', '\\n')
        ui_flag = '是' if r.get('is_ui') else '否'
        lines.append(f"{rid} | {orig} | {trans} | UI:{ui_flag}")

    rows_text = '\n'.join(lines)
    prompt += (
        f"---以下是待审查内容（第{batch_num}批，共{total_batches}批）---\n\n"
        + "ID | 原文 | 译文 | 是否UI\n"
        + rows_text
    )
    return prompt


def prepare_all_batches(
    rows: list[dict],
    batch_size: int = 200,
    term_lookup: dict | None = None,
    lang: str = 'en',
    max_terms: int = 120,
) -> list[BatchInfo]:
    """Prepare all batch prompts for AI review.

    Args:
        rows: list of {"id": int, "original": str, "translation": str}
        batch_size: rows per batch
        term_lookup: optional {chinese: english} term dict
        lang: target language code

    Returns:
        list of BatchInfo with prompt_text populated.
    """
    chunks = split_into_batches(rows, batch_size)
    total = len(chunks)
    batches = []

    for i, chunk in enumerate(chunks):
        info = BatchInfo(
            batch_num=i + 1,
            total_batches=total,
            row_ids=[r['id'] for r in chunk],
        )
        info.prompt_text = format_batch_prompt(
            chunk, i + 1, total, term_lookup, lang, max_terms=max_terms
        )
        batches.append(info)

    return batches


# ─── Response parsing ──────────────────────────────────────

_CORRECTION_PATTERN = re.compile(
    r'^\s*(\d+)\s*\|\s*(.+?)\s*$',
    re.MULTILINE,
)


def parse_ai_response(response_text: str) -> list[AICorrection]:
    """Parse AI response text into a list of corrections.

    Expected format per line:  ID | 修正版译文
    Lines that don't match this pattern are ignored.
    """
    if not response_text or '无需修改' in response_text:
        return []

    corrections = []
    for match in _CORRECTION_PATTERN.finditer(response_text):
        try:
            row_id = int(match.group(1))
            corrected = match.group(2).strip()
            if corrected:
                corrections.append(AICorrection(row_id=row_id, corrected_translation=corrected))
        except (ValueError, IndexError):
            continue

    return corrections


def apply_corrections(
    corrections: list[AICorrection],
    states: dict,
) -> int:
    """Apply AI corrections to RowState objects.

    Returns number of rows actually modified.
    """
    modified = 0
    for c in corrections:
        state = states.get(c.row_id)
        if not state:
            continue
        if state.fixed_translation != c.corrected_translation:
            state.fixed_translation = c.corrected_translation
            state.notes.append('AI审校修正')
            modified += 1
    return modified


# ─── Abstract interface for future API integration ─────────

class AIChecker:
    """Base class for direct API-based AI review.

    Subclass and override check_batch() to integrate with
    OpenAI, Claude, or any other LLM API.
    """

    def check_batch(
        self,
        rows: list[dict],
        term_lookup: dict[str, str] | None = None,
    ) -> list[AICorrection]:
        raise NotImplementedError


class DummyAIChecker(AIChecker):
    """No-op placeholder."""

    def check_batch(self, rows, term_lookup=None):
        return []

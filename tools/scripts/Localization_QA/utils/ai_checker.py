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
        f"4. 术语一致性 — 必须使用标准术语表中的译法\n"
        f"5. 术语语法 — 检查术语的大小写（句首/句中）、单复数、冠词搭配\n"
        f"\n"
        f"规则：\n"
        f"- 只列出需要修改的行\n"
        f"- 格式严格为：ID | 修正版译文\n"
        f"- 没有问题的行不要列出\n"
        f"- 如果全部没问题，回复\"无需修改\"\n\n"
    )


def _make_term_section(lang: str = 'en') -> str:
    lang_name = LANG_NAMES.get(lang, lang)
    return (
        f"---以下是本批涉及的标准术语表（中文 → {lang_name}），译文必须使用这些标准译法---\n\n"
        f"中文 | 标准{lang_name}\n"
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
    term_lookup: dict[str, str] | None,
) -> list[tuple[str, str]]:
    """Find terms from the lookup that appear in this batch's source texts."""
    if not term_lookup:
        return []
    combined_originals = ' '.join(str(r['original']) for r in batch_rows)
    return [
        (cn, en) for cn, en in term_lookup.items()
        if cn in combined_originals
    ]


def format_batch_prompt(
    batch_rows: list[dict],
    batch_num: int,
    total_batches: int,
    term_lookup: dict[str, str] | None = None,
    lang: str = 'en',
) -> str:
    """Generate the AI review prompt for one batch."""
    prompt = _make_prompt_header(lang)

    relevant_terms = _extract_relevant_terms(batch_rows, term_lookup)
    if relevant_terms:
        term_lines = '\n'.join(f"{cn} | {tgt}" for cn, tgt in relevant_terms)
        prompt += _make_term_section(lang).replace('{{term_lines}}', term_lines)

    lines = []
    for r in batch_rows:
        rid = r['id']
        orig = str(r['original']).replace('\n', '\\n')
        trans = str(r['translation']).replace('\n', '\\n')
        lines.append(f"{rid} | {orig} | {trans}")

    rows_text = '\n'.join(lines)
    prompt += (
        f"---以下是待审查内容（第{batch_num}批，共{total_batches}批）---\n\n"
        + "ID | 原文 | 译文\n"
        + rows_text
    )
    return prompt


def prepare_all_batches(
    rows: list[dict],
    batch_size: int = 200,
    term_lookup: dict[str, str] | None = None,
    lang: str = 'en',
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
        info.prompt_text = format_batch_prompt(chunk, i + 1, total, term_lookup, lang)
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

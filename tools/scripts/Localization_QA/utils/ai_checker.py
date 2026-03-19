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

_PROMPT_HEADER = """\
你是一个游戏本地化质检专家。请审查以下中英对照翻译，检查：
1. 错译 / 英文不自然
2. 漏译 / 语义偏差
3. 代码、标签（如 {icon1}、[color=xxx][/color]）、占位符格式错误
4. 术语不统一

规则：
- 只列出需要修改的行
- 格式严格为：ID | 修正版译文
- 没有问题的行不要列出
- 如果全部没问题，回复"无需修改"

"""


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


def format_batch_prompt(
    batch_rows: list[dict],
    batch_num: int,
    total_batches: int,
) -> str:
    """Generate the AI review prompt for one batch."""
    lines = []
    for r in batch_rows:
        rid = r['id']
        orig = str(r['original']).replace('\n', '\\n')
        trans = str(r['translation']).replace('\n', '\\n')
        lines.append(f"{rid} | {orig} | {trans}")

    rows_text = '\n'.join(lines)
    return (
        _PROMPT_HEADER
        + f"---以下是待审查内容（第{batch_num}批，共{total_batches}批）---\n\n"
        + "ID | 原文 | 译文\n"
        + rows_text
    )


def prepare_all_batches(
    rows: list[dict],
    batch_size: int = 200,
) -> list[BatchInfo]:
    """Prepare all batch prompts for AI review.

    Args:
        rows: list of {"id": int, "original": str, "translation": str}
        batch_size: rows per batch

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
        info.prompt_text = format_batch_prompt(chunk, i + 1, total)
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

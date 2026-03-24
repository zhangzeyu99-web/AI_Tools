"""Localization QA — main processing script.

Runs all checks on a language Excel file and produces:
  1. result_{lang}.xlsx   — Sheet "完整结果" + Sheet "需确认"
  2. report_{lang}.xlsx   — Sheet "总览" / "错误模式" / "学习笔记" / "详细记录"

Usage:
    python process_language.py --input language.xlsx --output-dir ./output/ --auto-fix
    python process_language.py --input language.xlsx --term-base terms.json --auto-fix
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from utils.excel_reader import read_language_file, get_text_pairs
from utils.variable_checker import check_all as check_variables
from utils.term_checker import check_term_hit, check_chinese_residue
from utils.pattern_detector import detect_patterns
from utils.ui_detector import is_ui_text
from utils.ai_checker import prepare_all_batches, apply_corrections


# ─────────────────────────────────────────────────────────────
# Row state tracker
# ─────────────────────────────────────────────────────────────

class RowState:
    __slots__ = (
        'row_id', 'original', 'translation', 'fixed_translation',
        'notes', 'is_ui', 'ui_confidence', 'issues',
        'needs_human_review', 'human_review_reason', 'ai_suggestion',
        'review_confidence',
    )

    def __init__(self, row_id: int, original: str, translation: str):
        self.row_id = row_id
        self.original = original
        self.translation = translation
        self.fixed_translation = translation
        self.notes: list[str] = []
        self.is_ui = False
        self.ui_confidence = 0.0
        self.issues: list = []
        self.needs_human_review = False
        self.human_review_reason = ''
        self.ai_suggestion = ''
        self.review_confidence = 1.0


# ─────────────────────────────────────────────────────────────
# Check phases
# ─────────────────────────────────────────────────────────────

def _load_term_base(path: str | None) -> dict[str, str]:
    """Load term base from Excel (.xlsx) or JSON (.json).

    Excel format: same as language table — ID / 原文 / 译文.
    JSON format:  {"lookup": {"中文": "English"}} or flat {"中文": "English"}.
    """
    if not path or not Path(path).exists():
        return {}

    ext = Path(path).suffix.lower()
    if ext in ('.xlsx', '.xls'):
        from utils.excel_reader import read_language_file, get_text_pairs
        import re
        df, col_map = read_language_file(path)
        pairs = get_text_pairs(df, col_map)
        lookup = {}
        strip_tags = re.compile(r'\[/?color[^\]]*\]|\{[^}]+\}')
        for _, row in pairs.iterrows():
            src = strip_tags.sub('', str(row['original'])).strip()
            tgt = strip_tags.sub('', str(row['translation'])).strip()
            if src and tgt:
                lookup[src] = tgt
        return lookup

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('lookup', data) if isinstance(data, dict) else {}


def _run_variable_checks(states: dict[int, RowState], auto_fix: bool):
    for state in states.values():
        for r in check_variables(state.row_id, state.original, state.translation):
            state.issues.append(r)
            if auto_fix and r.auto_fix and r.severity == 'error':
                state.fixed_translation = r.auto_fix
                state.notes.append(f"自动修复({r.check_type}): {r.message}")
            elif r.severity == 'error':
                state.needs_human_review = True
                state.human_review_reason = r.message
                state.ai_suggestion = r.auto_fix or state.translation
                state.review_confidence = r.confidence


def _run_term_checks(states: dict[int, RowState], term_lookup: dict, auto_fix: bool):
    if not term_lookup:
        return
    for state in states.values():
        for r in check_term_hit(state.row_id, state.original, state.fixed_translation, term_lookup):
            state.issues.append(r)
            if auto_fix and r.auto_fix and r.confidence >= 0.8:
                state.fixed_translation = r.auto_fix
                state.notes.append(f"术语修复: {r.message}")
            elif r.severity == 'error':
                state.needs_human_review = True
                state.human_review_reason = r.message
                state.ai_suggestion = r.auto_fix or state.fixed_translation
                state.review_confidence = r.confidence


def _run_chinese_residue_checks(states: dict[int, RowState]):
    for state in states.values():
        for r in check_chinese_residue(state.row_id, state.fixed_translation):
            state.issues.append(r)
            state.needs_human_review = True
            state.human_review_reason = r.message
            state.ai_suggestion = state.fixed_translation
            state.review_confidence = 0.5


def _run_pattern_checks(states: dict[int, RowState], auto_fix: bool):
    rows = [
        {'id': s.row_id, 'original': s.original, 'translation': s.fixed_translation}
        for s in states.values()
    ]
    groups, issues = detect_patterns(rows, min_group_size=3)

    for issue in issues:
        state = states.get(issue.row_id)
        if not state:
            continue
        state.issues.append(issue)

        if auto_fix and issue.auto_fix and issue.confidence >= 0.7:
            state.fixed_translation = issue.auto_fix
            state.notes.append(f"句式统一: {issue.best_pattern[:50]}")
        elif issue.confidence >= 0.6:
            state.needs_human_review = True
            state.human_review_reason = issue.message
            state.ai_suggestion = issue.auto_fix or state.fixed_translation
            state.review_confidence = issue.confidence
        else:
            state.needs_human_review = True
            state.human_review_reason = (
                f"句式存疑(置信度{issue.confidence:.0%}): {issue.message}"
            )
            state.ai_suggestion = issue.auto_fix or state.fixed_translation
            state.review_confidence = issue.confidence

    return groups


def _run_ui_detection(states: dict[int, RowState]):
    for state in states.values():
        is_ui_flag, conf, _ = is_ui_text(state.original, state.fixed_translation)
        state.is_ui = is_ui_flag
        state.ui_confidence = conf


def prepare_ai_review(
    states: dict[int, RowState],
    batch_size: int = 200,
    term_lookup: dict[str, str] | None = None,
    lang: str = 'en',
):
    """Prepare AI review batches from current states (after machine review)."""
    rows = [
        {'id': s.row_id, 'original': s.original, 'translation': s.fixed_translation}
        for s in states.values()
    ]
    return prepare_all_batches(rows, batch_size=batch_size, term_lookup=term_lookup, lang=lang)


# ─────────────────────────────────────────────────────────────
# Output builders
# ─────────────────────────────────────────────────────────────

def _build_result_full(
    df: pd.DataFrame,
    col_map: dict,
    states: dict[int, RowState],
    lang_index: int = 0,
) -> pd.DataFrame:
    """Sheet '完整结果': full data with fixes applied + notes column."""
    id_col = col_map['id_col']
    trans_col = col_map['languages'][lang_index]['translation_col']
    result = df.copy()

    note_col = '备注'
    if note_col not in result.columns:
        result[note_col] = ''

    for _, row in result.iterrows():
        rid = row[id_col]
        state = states.get(rid)
        if not state:
            continue
        if state.fixed_translation != state.translation:
            result.loc[result[id_col] == rid, trans_col] = state.fixed_translation
        if state.notes:
            result.loc[result[id_col] == rid, note_col] = '; '.join(state.notes)

    return result


def _build_result_review(states: dict[int, RowState]) -> pd.DataFrame:
    """Sheet '需确认': subset of rows needing human review."""
    rows = []
    for state in states.values():
        if not state.needs_human_review:
            continue
        rows.append({
            'ID': state.row_id,
            '原文': state.original,
            '当前译文': state.fixed_translation,
            'AI建议': state.ai_suggestion or state.fixed_translation,
            '原因': state.human_review_reason,
            '置信度': f"{state.review_confidence:.0%}",
            '是否UI': '是' if state.is_ui else '否',
        })
    if not rows:
        return pd.DataFrame(columns=['ID', '原文', '当前译文', 'AI建议', '原因', '置信度', '是否UI'])
    return pd.DataFrame(rows)


def _build_report_sheets(
    states: dict[int, RowState],
    groups: list,
    input_file: str,
    lang: str,
) -> dict[str, pd.DataFrame]:
    """Build the 4 report sheets as DataFrames."""
    total = len(states)
    auto_fixed = sum(1 for s in states.values() if s.fixed_translation != s.translation)
    human_review = sum(1 for s in states.values() if s.needs_human_review)
    no_change = max(0, total - auto_fixed - human_review)
    ui_count = sum(1 for s in states.values() if s.is_ui)

    # Sheet 1: 总览
    summary_df = pd.DataFrame([
        {'指标': '总行数', '数值': total},
        {'指标': '自动修复', '数值': auto_fixed},
        {'指标': '需人工确认', '数值': human_review},
        {'指标': '无需改动', '数值': no_change},
        {'指标': 'UI文本数', '数值': ui_count},
        {'指标': '句式组数', '数值': len(groups)},
        {'指标': '来源文件', '数值': Path(input_file).name},
        {'指标': '语言', '数值': lang},
        {'指标': '处理时间', '数值': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
    ])

    # Sheet 2: 错误模式
    pattern_counter: Counter = Counter()
    pattern_examples: dict[str, list] = defaultdict(list)
    for state in states.values():
        for issue in state.issues:
            ctype = getattr(issue, 'check_type', 'unknown')
            pattern_counter[ctype] += 1
            if len(pattern_examples[ctype]) < 5:
                pattern_examples[ctype].append(state.row_id)

    _DESC = {
        'variable_missing': '原文变量在译文中缺失',
        'variable_extra': '译文中出现原文没有的变量',
        'variable_order': '变量出现顺序与原文不同',
        'bbcode_open_mismatch': 'BBCode开标签数量不匹配',
        'bbcode_close_mismatch': 'BBCode闭标签数量不匹配',
        'bbcode_unclosed': '译文BBCode标签未闭合',
        'bbcode_color_mismatch': '颜色代码值与原文不一致',
        'newline_mismatch': '换行符数量不匹配',
        'term_missing': '标准术语未在译文中出现',
        'term_partial_hit': '多词术语仅部分匹配',
        'term_capitalization': '术语大小写问题',
        'chinese_residue': '译文中残留中文字符',
        'pattern_inconsistency': '译文句式与组内标准不一致',
    }
    error_rows = []
    for ctype, count in pattern_counter.most_common():
        error_rows.append({
            '错误类型': ctype,
            '数量': count,
            '示例ID': ', '.join(str(i) for i in pattern_examples[ctype]),
            '描述': _DESC.get(ctype, ctype),
        })
    errors_df = pd.DataFrame(error_rows) if error_rows else pd.DataFrame(
        columns=['错误类型', '数量', '示例ID', '描述']
    )

    # Sheet 3: 学习笔记
    notes = []
    if pattern_counter.get('pattern_inconsistency', 0) > 0:
        notes.append(f"发现 {pattern_counter['pattern_inconsistency']} 处句式不一致，涉及 {len(groups)} 个模板组")
    if pattern_counter.get('variable_missing', 0) > 0:
        notes.append(f"{pattern_counter['variable_missing']} 行存在变量缺失")
    if pattern_counter.get('chinese_residue', 0) > 0:
        notes.append(f"{pattern_counter['chinese_residue']} 行译文残留中文字符")
    if ui_count > 0:
        notes.append(f"{ui_count} 条文本被识别为UI元素（占比 {ui_count/total:.1%}）")
    notes_df = pd.DataFrame({'学习笔记': notes}) if notes else pd.DataFrame(columns=['学习笔记'])

    # Sheet 4: 详细记录
    detail_rows = []
    for state in states.values():
        if state.fixed_translation != state.translation or state.needs_human_review:
            detail_rows.append({
                'ID': state.row_id,
                '原文': state.original,
                '修改前': state.translation,
                '修改后': state.fixed_translation,
                '原因': '; '.join(state.notes) if state.notes else '需人工确认',
                '是否UI': '是' if state.is_ui else '否',
            })
    details_df = pd.DataFrame(detail_rows) if detail_rows else pd.DataFrame(
        columns=['ID', '原文', '修改前', '修改后', '原因', '是否UI']
    )

    return {
        '总览': summary_df,
        '错误模式': errors_df,
        '学习笔记': notes_df,
        '详细记录': details_df,
    }


# ─────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────

def run_machine_review(
    input_path: str,
    term_base_path: str | None = None,
    auto_fix: bool = True,
    lang_index: int = 0,
) -> tuple:
    """Phase 1: Run all rule-based checks.

    Returns (df, col_map, states, groups) for further processing.
    """
    print(f"[1/6] 读取输入: {input_path}")
    df, col_map = read_language_file(input_path)
    pairs = get_text_pairs(df, col_map, lang_index=lang_index)
    print(f"       {len(pairs)} 行已加载")

    states: dict[int, RowState] = {}
    for _, row in pairs.iterrows():
        rid = int(row['id'])
        states[rid] = RowState(rid, row['original'], row['translation'])

    print(f"[2/6] 加载术语库")
    term_lookup = _load_term_base(term_base_path)
    print(f"       {len(term_lookup)} 条术语" if term_lookup else "       (无术语库)")

    print(f"[3/6] 变量 & 标签检查")
    _run_variable_checks(states, auto_fix)

    print(f"[4/6] 术语检查 + 中文残留")
    _run_term_checks(states, term_lookup, auto_fix)
    _run_chinese_residue_checks(states)

    print(f"[5/6] 句式一致性检查")
    groups = _run_pattern_checks(states, auto_fix)

    print(f"[6/6] UI文本识别")
    _run_ui_detection(states)

    total_issues = sum(len(s.issues) for s in states.values())
    print(f"\n       机审发现 {total_issues} 个问题")

    return df, col_map, states, groups


def write_outputs(
    df: pd.DataFrame,
    col_map: dict,
    states: dict[int, RowState],
    groups: list,
    input_path: str,
    lang: str = 'en',
    output_dir: str = './output',
    lang_index: int = 0,
) -> dict:
    """Phase 3: Write final output files after all reviews are done.

    Writes to output root (latest, always overwritten) AND to an archive
    subfolder named {lang}_{timestamp} for history.

    Returns a summary dict.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Clean old result/report files from root before writing new ones
    for old_file in out.glob('result_*.xlsx'):
        old_file.unlink()
    for old_file in out.glob('report_*.xlsx'):
        old_file.unlink()

    # Archive subfolder: output/{source}_{lang}_{timestamp}/
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    source_name = Path(input_path).stem
    archive_dir = out / f"{source_name}_{lang}_{timestamp}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    full_df = _build_result_full(df, col_map, states, lang_index)
    review_df = _build_result_review(states)
    report_sheets = _build_report_sheets(states, groups, input_path, lang)

    # Write to both locations
    for target_dir, label in [(out, "最新"), (archive_dir, "归档")]:
        result_path = target_dir / f"result_{lang}.xlsx"
        with pd.ExcelWriter(result_path, engine='openpyxl') as writer:
            full_df.to_excel(writer, sheet_name='完整结果', index=False)
            review_df.to_excel(writer, sheet_name='需确认', index=False)

        report_path = target_dir / f"report_{lang}.xlsx"
        with pd.ExcelWriter(report_path, engine='openpyxl') as writer:
            for sheet_name, sheet_df in report_sheets.items():
                sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)

    result_path = out / f"result_{lang}.xlsx"
    report_path = out / f"report_{lang}.xlsx"

    print(f"\n  -> {result_path}  (完整结果 + 需确认 {len(review_df)} 条)")
    print(f"  -> {report_path}  (4 sheets)")
    print(f"  -> {archive_dir}/  (归档)")

    summary = {
        'total_processed': len(states),
        'auto_fixed': sum(1 for s in states.values() if s.fixed_translation != s.translation),
        'need_human_review': sum(1 for s in states.values() if s.needs_human_review),
        'no_change': max(0, len(states) - sum(1 for s in states.values() if s.fixed_translation != s.translation) - sum(1 for s in states.values() if s.needs_human_review)),
        'ui_texts': sum(1 for s in states.values() if s.is_ui),
        'total_issues': sum(len(s.issues) for s in states.values()),
        'result_path': str(result_path),
        'report_path': str(report_path),
        'archive_dir': str(archive_dir),
    }

    print(f"\n{'='*50}")
    print(f"  总行数:       {summary['total_processed']}")
    print(f"  自动修复:     {summary['auto_fixed']}")
    print(f"  需人工确认:   {summary['need_human_review']}")
    print(f"  无需改动:     {summary['no_change']}")
    print(f"  UI文本:       {summary['ui_texts']}")
    print(f"{'='*50}")

    return summary


def process(
    input_path: str,
    term_base_path: str | None = None,
    lang: str = 'en',
    output_dir: str = './output',
    auto_fix: bool = True,
    lang_index: int = 0,
) -> dict:
    """Run the full pipeline (machine review only, no AI).

    For AI-assisted review, use run_machine_review() + write_outputs()
    separately, with AI review in between.
    """
    df, col_map, states, groups = run_machine_review(
        input_path, term_base_path, auto_fix, lang_index,
    )
    return write_outputs(
        df, col_map, states, groups, input_path, lang, output_dir, lang_index,
    )


def main():
    parser = argparse.ArgumentParser(description='游戏本地化质检工具')
    parser.add_argument('--input', required=True, help='语言表 Excel 文件')
    parser.add_argument('--term-base', default=None, help='术语库 JSON 文件（可选）')
    parser.add_argument('--lang', default='en', help='目标语言代码（默认 en）')
    parser.add_argument('--output-dir', default='./output', help='输出目录')
    parser.add_argument('--auto-fix', action='store_true', help='自动修复可修复项')
    parser.add_argument('--lang-index', type=int, default=0, help='多语言文件列索引')

    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"错误: 文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    process(
        input_path=args.input,
        term_base_path=args.term_base,
        lang=args.lang,
        output_dir=args.output_dir,
        auto_fix=args.auto_fix,
        lang_index=args.lang_index,
    )


if __name__ == '__main__':
    main()

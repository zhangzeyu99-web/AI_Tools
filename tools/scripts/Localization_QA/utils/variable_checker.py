"""Variable and BBCode tag integrity checker.

Detects:
- Missing variables ({xxx} placeholders)
- Extra variables in translation
- Unclosed/mismatched BBCode tags
- Tag order/nesting issues
"""
import re
from dataclasses import dataclass, field

# Patterns
VAR_PATTERN = re.compile(r'\{[^}]+\}')
BBCODE_OPEN = re.compile(r'\[color\s*=[^\]]*\]', re.IGNORECASE)
BBCODE_CLOSE = re.compile(r'\[/color\]', re.IGNORECASE)
BBCODE_ANY = re.compile(r'\[/?color[^\]]*\]', re.IGNORECASE)
NEWLINE_TAG = re.compile(r'\\n')


@dataclass
class CheckResult:
    """Result from a single check."""
    row_id: int
    check_type: str
    severity: str  # 'error', 'warning'
    message: str
    original: str = ''
    translation: str = ''
    auto_fix: str = ''  # suggested fix, empty if unfixable
    confidence: float = 1.0


def check_variables(row_id: int, original: str, translation: str) -> list[CheckResult]:
    """Check that all variables in original appear in translation and vice versa."""
    results = []

    orig_vars = VAR_PATTERN.findall(original)
    trans_vars = VAR_PATTERN.findall(translation)

    orig_set = set(orig_vars)
    trans_set = set(trans_vars)

    missing = orig_set - trans_set
    extra = trans_set - orig_set

    if missing:
        fixed = translation
        for var in missing:
            if var not in fixed:
                fixed = fixed.rstrip() + ' ' + var

        results.append(CheckResult(
            row_id=row_id,
            check_type='variable_missing',
            severity='error',
            message=f"Missing variables in translation: {', '.join(sorted(missing))}",
            original=original,
            translation=translation,
            auto_fix=fixed,
            confidence=0.9,
        ))

    if extra:
        results.append(CheckResult(
            row_id=row_id,
            check_type='variable_extra',
            severity='warning',
            message=f"Extra variables in translation: {', '.join(sorted(extra))}",
            original=original,
            translation=translation,
        ))

    # Check variable order consistency (same count, different order may be intentional)
    if not missing and not extra and len(orig_vars) > 1:
        if orig_vars != trans_vars:
            results.append(CheckResult(
                row_id=row_id,
                check_type='variable_order',
                severity='warning',
                message=f"Variable order differs: original={orig_vars}, translation={trans_vars}",
                original=original,
                translation=translation,
                confidence=0.6,
            ))

    return results


def check_bbcode_tags(row_id: int, original: str, translation: str) -> list[CheckResult]:
    """Check BBCode tag completeness and consistency."""
    results = []

    orig_opens = BBCODE_OPEN.findall(original)
    orig_closes = BBCODE_CLOSE.findall(original)
    trans_opens = BBCODE_OPEN.findall(translation)
    trans_closes = BBCODE_CLOSE.findall(translation)

    # Tag count mismatch
    if len(orig_opens) != len(trans_opens):
        results.append(CheckResult(
            row_id=row_id,
            check_type='bbcode_open_mismatch',
            severity='error',
            message=(
                f"BBCode open tag count mismatch: "
                f"original={len(orig_opens)}, translation={len(trans_opens)}"
            ),
            original=original,
            translation=translation,
        ))

    if len(orig_closes) != len(trans_closes):
        results.append(CheckResult(
            row_id=row_id,
            check_type='bbcode_close_mismatch',
            severity='error',
            message=(
                f"BBCode close tag count mismatch: "
                f"original={len(orig_closes)}, translation={len(trans_closes)}"
            ),
            original=original,
            translation=translation,
        ))

    # Unclosed tags in translation
    if len(trans_opens) != len(trans_closes):
        results.append(CheckResult(
            row_id=row_id,
            check_type='bbcode_unclosed',
            severity='error',
            message=(
                f"Unclosed BBCode tags in translation: "
                f"{len(trans_opens)} opens vs {len(trans_closes)} closes"
            ),
            original=original,
            translation=translation,
        ))

    # Color code consistency
    orig_colors = sorted(BBCODE_OPEN.findall(original))
    trans_colors = sorted(BBCODE_OPEN.findall(translation))
    if orig_colors and trans_colors and orig_colors != trans_colors:
        results.append(CheckResult(
            row_id=row_id,
            check_type='bbcode_color_mismatch',
            severity='error',
            message=f"Color codes differ: original={orig_colors}, translation={trans_colors}",
            original=original,
            translation=translation,
            auto_fix=_fix_color_codes(original, translation),
            confidence=0.85,
        ))

    return results


def _fix_color_codes(original: str, translation: str) -> str:
    """Try to fix color code mismatches by using original's color codes."""
    orig_colors = BBCODE_OPEN.findall(original)
    trans_colors = BBCODE_OPEN.findall(translation)

    if len(orig_colors) != len(trans_colors):
        return ''

    result = translation
    for orig_c, trans_c in zip(orig_colors, trans_colors):
        if orig_c != trans_c:
            result = result.replace(trans_c, orig_c, 1)
    return result


def check_newlines(row_id: int, original: str, translation: str) -> list[CheckResult]:
    """Check that \\n counts match."""
    results = []
    orig_count = len(NEWLINE_TAG.findall(original))
    trans_count = len(NEWLINE_TAG.findall(translation))

    if orig_count != trans_count:
        results.append(CheckResult(
            row_id=row_id,
            check_type='newline_mismatch',
            severity='warning',
            message=f"Newline count mismatch: original={orig_count}, translation={trans_count}",
            original=original,
            translation=translation,
            confidence=0.7,
        ))

    return results


def check_all(row_id: int, original: str, translation: str) -> list[CheckResult]:
    """Run all variable/tag checks on a single row."""
    results = []
    results.extend(check_variables(row_id, original, translation))
    results.extend(check_bbcode_tags(row_id, original, translation))
    results.extend(check_newlines(row_id, original, translation))
    return results

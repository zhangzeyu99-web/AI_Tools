"""Term hit detection and grammar validation.

Layer 1: Check if standard terms are used in translations.
Layer 2: Check grammar correctness (capitalization, plurals, articles).
"""
import re
from dataclasses import dataclass


@dataclass
class TermCheckResult:
    """Result from a term check."""
    row_id: int
    check_type: str
    severity: str  # 'error', 'warning', 'info'
    message: str
    source_term: str = ''
    expected_target: str = ''
    actual_fragment: str = ''
    auto_fix: str = ''
    confidence: float = 1.0


def _normalize_for_search(text: str) -> str:
    """Normalize text for case-insensitive term searching."""
    t = re.sub(r'\[/?color[^\]]*\]', '', text)
    t = re.sub(r'\{[^}]+\}', '', t)
    return t.strip()


def _find_term_in_text(term: str, text: str) -> tuple[bool, str]:
    """Search for a term in text, case-insensitive.

    Returns (found, actual_match).
    """
    clean_text = _normalize_for_search(text)
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    match = pattern.search(clean_text)
    if match:
        return True, match.group()
    return False, ''


def _check_capitalization(
    term: str,
    translation: str,
    row_id: int,
    source_term: str,
) -> list[TermCheckResult]:
    """Check if term capitalization is correct in context."""
    results = []
    clean_trans = _normalize_for_search(translation)

    pattern = re.compile(re.escape(term), re.IGNORECASE)
    for match in pattern.finditer(clean_trans):
        actual = match.group()
        start = match.start()

        if actual == term:
            continue

        # Sentence start: first letter should be capitalized
        is_sentence_start = start == 0 or clean_trans[start - 2:start] in ('. ', '! ', '? ')

        if is_sentence_start:
            expected = term[0].upper() + term[1:]
            if actual != expected:
                results.append(TermCheckResult(
                    row_id=row_id,
                    check_type='term_capitalization',
                    severity='warning',
                    message=f"Term '{actual}' at sentence start should be '{expected}'",
                    source_term=source_term,
                    expected_target=expected,
                    actual_fragment=actual,
                    auto_fix=translation.replace(actual, expected, 1),
                    confidence=0.9,
                ))
        else:
            # Mid-sentence: proper nouns stay capitalized, common nouns lowercase
            # Heuristic: if the standard term has capitals, it's a proper noun → keep as-is
            if term[0].isupper():
                # Proper noun — should match exactly
                if actual != term:
                    results.append(TermCheckResult(
                        row_id=row_id,
                        check_type='term_capitalization',
                        severity='warning',
                        message=f"Proper noun '{actual}' should be '{term}'",
                        source_term=source_term,
                        expected_target=term,
                        actual_fragment=actual,
                        auto_fix=translation.replace(actual, term, 1),
                        confidence=0.85,
                    ))
            else:
                # Common noun mid-sentence: should be lowercase
                if actual[0].isupper() and not is_sentence_start:
                    expected_lower = actual[0].lower() + actual[1:]
                    results.append(TermCheckResult(
                        row_id=row_id,
                        check_type='term_capitalization',
                        severity='warning',
                        message=f"Common term '{actual}' mid-sentence should be '{expected_lower}'",
                        source_term=source_term,
                        expected_target=expected_lower,
                        actual_fragment=actual,
                        auto_fix=translation.replace(actual, expected_lower, 1),
                        confidence=0.75,
                    ))

    return results


def check_term_hit(
    row_id: int,
    original: str,
    translation: str,
    term_lookup: dict[str, str],
) -> list[TermCheckResult]:
    """Check if standard terms appear in the translation.

    Args:
        row_id: Row identifier
        original: Chinese source text
        translation: English translation
        term_lookup: Dict of {chinese_term: english_term}
    """
    results = []

    for cn_term, en_term in term_lookup.items():
        if cn_term not in original:
            continue

        # Layer 1: term hit detection
        found, actual_match = _find_term_in_text(en_term, translation)

        if not found:
            # Check for partial matches or common variants
            en_words = en_term.split()
            if len(en_words) > 1:
                # Multi-word term: check if any words appear
                hits = sum(1 for w in en_words if w.lower() in translation.lower())
                if hits > 0 and hits < len(en_words):
                    results.append(TermCheckResult(
                        row_id=row_id,
                        check_type='term_partial_hit',
                        severity='warning',
                        message=f"Partial term match: expected '{en_term}' for '{cn_term}', "
                                f"found {hits}/{len(en_words)} words",
                        source_term=cn_term,
                        expected_target=en_term,
                        confidence=0.6,
                    ))
                else:
                    results.append(TermCheckResult(
                        row_id=row_id,
                        check_type='term_missing',
                        severity='error',
                        message=f"Term not found: expected '{en_term}' for '{cn_term}'",
                        source_term=cn_term,
                        expected_target=en_term,
                        confidence=0.8,
                    ))
            else:
                results.append(TermCheckResult(
                    row_id=row_id,
                    check_type='term_missing',
                    severity='error',
                    message=f"Term not found: expected '{en_term}' for '{cn_term}'",
                    source_term=cn_term,
                    expected_target=en_term,
                    confidence=0.8,
                ))
        else:
            # Layer 2: grammar check on the matched term
            cap_results = _check_capitalization(en_term, translation, row_id, cn_term)
            results.extend(cap_results)

    return results


def check_chinese_residue(
    row_id: int,
    translation: str,
) -> list[TermCheckResult]:
    """Check for residual Chinese characters in translation."""
    results = []
    cn_chars = re.findall(r'[\u4e00-\u9fa5]+', translation)
    if cn_chars:
        results.append(TermCheckResult(
            row_id=row_id,
            check_type='chinese_residue',
            severity='error',
            message=f"Chinese characters found in translation: {'、'.join(cn_chars)}",
            actual_fragment='、'.join(cn_chars),
            confidence=1.0,
        ))
    return results

from __future__ import annotations

from interview_evidence.workers.analysis.code_units import CodeUnitAnalyzer
from interview_evidence.workers.analysis.git_commits import CommitAnalyzer, CommitInput


def test_commit_analysis_uses_multiple_identity_signals_and_never_name_only() -> None:
    analyzer = CommitAnalyzer()
    commit = CommitInput(
        commit_sha="a" * 40,
        parent_sha="b" * 40,
        author_name="지원자",
        author_email="candidate@example.com",
        changed_paths=("src/payment.py", "tests/test_payment.py"),
        patch="+def retry_payment():\n+    return True\n",
    )

    matched = analyzer.analyze(
        commit,
        candidate_identity_inputs={"emails": ["candidate@example.com"], "names": ["지원자"]},
    )
    name_only = analyzer.analyze(
        commit,
        candidate_identity_inputs={"emails": [], "names": ["지원자"]},
    )

    assert matched.ownership_confidence >= 0.8
    assert matched.ownership_class == "primary_owned"
    assert name_only.ownership_confidence < 0.6
    assert name_only.ownership_class == "context_only"


def test_code_unit_expands_symbol_and_discovers_related_tests() -> None:
    source = """def retry_payment(attempts: int) -> bool:\n    if attempts > 3:\n        return False\n    return True\n"""
    test_source = """from payment import retry_payment\n\ndef test_retry_payment():\n    assert retry_payment(1)\n"""

    units = CodeUnitAnalyzer().analyze(
        path="src/payment.py",
        source=source,
        changed_lines=(2, 3),
        repository_files={"tests/test_payment.py": test_source},
    )

    assert units[0].symbol == "retry_payment"
    assert units[0].original_line_range == (1, 4)
    assert units[0].candidate_owned_regions == ((2, 3),)
    assert units[0].related_test_ids == ("tests/test_payment.py",)

from __future__ import annotations

import ast
from pathlib import PurePosixPath

from interview_evidence.submission_analysis.domain.git_analysis import CandidateCodeUnit


class CodeUnitAnalyzer:
    __slots__ = ()

    def analyze(
        self,
        *,
        path: str,
        source: str,
        changed_lines: tuple[int, int],
        repository_files: dict[str, str],
    ) -> tuple[CandidateCodeUnit, ...]:
        language = self._language(path)
        symbols = self._python_symbols(source) if language == "python" else ()
        relevant = tuple(item for item in symbols if self._overlaps(item[1], changed_lines))
        if not relevant:
            relevant = ((PurePosixPath(path).stem, (changed_lines[0], changed_lines[1])),)
        units: list[CandidateCodeUnit] = []
        for symbol, line_range in relevant:
            related_tests = tuple(
                candidate_path
                for candidate_path, candidate_source in sorted(repository_files.items())
                if self._is_test_path(candidate_path) and symbol in candidate_source
            )
            owned_start = max(line_range[0], changed_lines[0])
            owned_end = min(line_range[1], changed_lines[1])
            units.append(
                CandidateCodeUnit(
                    path=path,
                    language=language,
                    symbol=symbol,
                    original_line_range=line_range,
                    current_line_range=line_range,
                    candidate_owned_regions=((owned_start, owned_end),),
                    related_test_ids=related_tests,
                )
            )
        return tuple(units)

    @staticmethod
    def _python_symbols(source: str) -> tuple[tuple[str, tuple[int, int]], ...]:
        tree = ast.parse(source)
        return tuple(
            (node.name, (node.lineno, node.end_lineno or node.lineno))
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        )

    @staticmethod
    def _language(path: str) -> str:
        suffix = PurePosixPath(path).suffix
        return {".py": "python", ".ts": "typescript", ".tsx": "typescript"}.get(suffix, "text")

    @staticmethod
    def _overlaps(symbol_range: tuple[int, int], changed_range: tuple[int, int]) -> bool:
        return symbol_range[0] <= changed_range[1] and changed_range[0] <= symbol_range[1]

    @staticmethod
    def _is_test_path(path: str) -> bool:
        name = PurePosixPath(path).name
        return "test" in PurePosixPath(path).parts or name.startswith("test_") or ".test." in name

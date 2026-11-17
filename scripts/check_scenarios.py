#!/usr/bin/env python3
"""시나리오 문서와 테스트의 1:1 연결을 검사한다.

- 문서: docs/domains/*/test-scenarios.md 표의 첫 칸이 `{DOMAIN}-TS-NNN`인 행
- 테스트: tests/ 의 `@pytest.mark.scenario("{DOMAIN}-TS-NNN")`

검사 규칙 (docs/design-docs/tdd-workflow.md "문서와 테스트 연결"):
1. 테스트에 붙은 ID는 모두 문서 표에 있어야 한다.
2. 한 ID는 테스트 하나에만 붙는다.
3. 문서 ID는 문서 안팎에서 중복되지 않는다.
4. 문서 표의 ID는 모두 테스트에 연결되어야 한다. 단, 문서 상단 `> 상태:`에 `구현 전`이 있으면
   아직 테스트가 없는 ID는 경고로만 알린다 (TDD의 문서 단계).

테스트 코드를 import하지 않고 AST로 읽으므로 DB 없이 실행된다.
"""

from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ID_PATTERN = re.compile(r"^[A-Z]+(?:-[A-Z]+)*-TS-\d{3}$")
ROW_PATTERN = re.compile(r"^\|\s*([A-Z]+(?:-[A-Z]+)*-TS-\d{3})\s*\|")
PENDING_MARK = "구현 전"


def read_docs() -> tuple[dict[str, Path], set[Path], list[str]]:
    ids: dict[str, Path] = {}
    pending_docs: set[Path] = set()
    errors: list[str] = []
    for doc in sorted(ROOT.glob("docs/domains/*/test-scenarios.md")):
        text = doc.read_text(encoding="utf-8")
        status = next((line for line in text.splitlines() if line.startswith("> 상태:")), "")
        if PENDING_MARK in status:
            pending_docs.add(doc)
        for line in text.splitlines():
            match = ROW_PATTERN.match(line)
            if not match:
                continue
            scenario_id = match.group(1)
            if scenario_id in ids:
                errors.append(f"문서 ID 중복: {scenario_id} ({ids[scenario_id].relative_to(ROOT)}, {doc.relative_to(ROOT)})")
            ids[scenario_id] = doc
    return ids, pending_docs, errors


def read_tests() -> tuple[dict[str, list[str]], list[str]]:
    found: dict[str, list[str]] = defaultdict(list)
    errors: list[str] = []
    for path in sorted(ROOT.glob("tests/**/test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not _is_scenario_marker(decorator):
                    continue
                location = f"{path.relative_to(ROOT)}::{node.name}"
                if len(decorator.args) != 1 or not isinstance(decorator.args[0], ast.Constant):
                    errors.append(f"scenario marker는 ID 문자열 하나를 받아야 한다: {location}")
                    continue
                scenario_id = decorator.args[0].value
                if not isinstance(scenario_id, str) or not ID_PATTERN.match(scenario_id):
                    errors.append(f"ID 형식 오류 ({{DOMAIN}}-TS-NNN): {scenario_id!r} {location}")
                    continue
                found[scenario_id].append(location)
    return found, errors


def _is_scenario_marker(decorator: ast.expr) -> bool:
    if not isinstance(decorator, ast.Call):
        return False
    func = decorator.func
    return isinstance(func, ast.Attribute) and func.attr == "scenario"


def main() -> int:
    doc_ids, pending_docs, errors = read_docs()
    test_ids, test_errors = read_tests()
    errors += test_errors
    warnings: list[str] = []

    for scenario_id, locations in sorted(test_ids.items()):
        if scenario_id not in doc_ids:
            errors.append(f"문서에 없는 ID: {scenario_id} ({', '.join(locations)})")
        if len(locations) > 1:
            errors.append(f"테스트 여러 개에 붙은 ID: {scenario_id} ({', '.join(locations)})")

    for scenario_id, doc in sorted(doc_ids.items()):
        if scenario_id in test_ids:
            continue
        message = f"테스트가 없는 ID: {scenario_id} ({doc.relative_to(ROOT)})"
        (warnings if doc in pending_docs else errors).append(message)

    for message in warnings:
        print(f"경고: {message}")
    for message in errors:
        print(f"오류: {message}", file=sys.stderr)

    linked = sum(1 for scenario_id in doc_ids if scenario_id in test_ids)
    print(f"시나리오 {len(doc_ids)}개 중 {linked}개가 테스트에 연결됨 (경고 {len(warnings)}, 오류 {len(errors)})")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

"""평가셋 러너 — extract_tags() 정확도 측정.

세 메트릭:
- exact:    set(출력) == set(expected_tags)              ← 엄격
- lenient:  expected ⊆ 출력 ⊆ accept                     ← 허용범위 (모호·정황 케이스 대응)
- jaccard:  |교집합| / |합집합|                          ← 정도(부분점수)

사용법:
    cd Backend
    python3 -m src.llm.eval.runner               # 전체 실행 + 요약 + 실패 케이스 표시
    python3 -m src.llm.eval.runner --verbose     # 모든 케이스 한 줄씩 출력
    python3 -m src.llm.eval.runner --case clear-01  # 특정 케이스만
    python3 -m src.llm.eval.runner --category 부정    # 카테고리만

extract_tags()가 API 키 있으면 Claude, 없으면 mock 폴백 (extract.py와 동일).
36건 호출 비용 ≈ $0.02 미만.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from ..extract import extract_tags

CASES_PATH = Path(__file__).resolve().parent / "cases.jsonl"


@dataclass
class CaseResult:
    case: dict
    output: list[str]
    source: str  # 'claude'|'mock'|'fallback'
    exact: int
    lenient: int
    jaccard: float


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0  # 둘 다 빈 셋은 완전 일치로 간주
    inter = sa & sb
    union = sa | sb
    return len(inter) / len(union) if union else 0.0


def _score(out: list[str], expected: list[str], accept: list[str]) -> tuple[int, int, float]:
    so, se, sa = set(out), set(expected), set(accept)
    exact = 1 if so == se else 0
    # lenient: 기대 태그를 모두 포함 + 허용 범위 안. accept가 비면 빈 출력만 통과.
    lenient = 1 if (se.issubset(so) and so.issubset(sa or se)) else 0
    return exact, lenient, _jaccard(out, expected)


def load_cases(path: Path = CASES_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run(cases: list[dict]) -> list[CaseResult]:
    out: list[CaseResult] = []
    for c in cases:
        r = extract_tags(c["query"])
        e, l, j = _score(r.tags, c["expected_tags"], c["accept_tags"])
        out.append(CaseResult(case=c, output=r.tags, source=r.source, exact=e, lenient=l, jaccard=j))
    return out


def print_case(res: CaseResult) -> None:
    c = res.case
    mark = "✓" if res.lenient else "✗"
    print(
        f"  {mark} [{c['id']:11s}] {c['query']!r:<35s} "
        f"out={res.output!s:30s} exp={c['expected_tags']!s:25s} "
        f"acc={c['accept_tags']!s:25s} j={res.jaccard:.2f} ({res.source})"
    )


def summarize(results: list[CaseResult]) -> None:
    by_cat: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by_cat[r.case["category"]].append(r)

    print("\n=== 카테고리별 ===")
    print(f"  {'카테고리':<18s} {'n':>3s}  {'exact':>7s}  {'lenient':>9s}  {'jaccard':>8s}")
    for cat in ["명확", "모호", "컨텍스트", "부정", "노이즈", "카테고리축 부재"]:
        rs = by_cat.get(cat, [])
        if not rs:
            continue
        n = len(rs)
        ex = sum(r.exact for r in rs) / n
        le = sum(r.lenient for r in rs) / n
        ja = sum(r.jaccard for r in rs) / n
        print(f"  {cat:<18s} {n:>3d}  {ex*100:>6.1f}%  {le*100:>8.1f}%  {ja:>8.2f}")

    n = len(results)
    ex = sum(r.exact for r in results) / n
    le = sum(r.lenient for r in results) / n
    ja = sum(r.jaccard for r in results) / n
    sources = defaultdict(int)
    for r in results:
        sources[r.source] += 1
    print(f"\n=== 전체 ({n}건) ===")
    print(f"  exact   : {ex*100:5.1f}%   ({sum(r.exact for r in results)}/{n})")
    print(f"  lenient : {le*100:5.1f}%   ({sum(r.lenient for r in results)}/{n})  ← 허용 범위 기준")
    print(f"  jaccard : {ja:5.2f}")
    print(f"  source  : {dict(sources)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", help="모든 케이스 출력")
    ap.add_argument("--case", help="특정 case id만 실행 (예: clear-01)")
    ap.add_argument("--category", help="특정 카테고리만 (명확/모호/컨텍스트/부정/노이즈/'카테고리축 부재')")
    args = ap.parse_args()

    cases = load_cases()
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
    if args.category:
        cases = [c for c in cases if c["category"] == args.category]
    if not cases:
        print("매칭되는 케이스 없음.")
        return

    results = run(cases)

    if args.verbose:
        print("=== 전체 케이스 ===")
        for r in results:
            print_case(r)
    else:
        failed = [r for r in results if not r.lenient]
        if failed:
            print(f"=== 실패 케이스 ({len(failed)}/{len(results)}) — lenient 기준 ===")
            for r in failed:
                print_case(r)
        else:
            print("=== 모든 케이스 lenient 통과 ===")

    summarize(results)


if __name__ == "__main__":
    main()

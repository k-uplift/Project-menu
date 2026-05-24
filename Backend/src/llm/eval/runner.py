"""평가셋 러너 — extract_tags() 정확도 측정.

네 메트릭:
- exact:        set(out.tags) == set(expected_tags)  AND  exclude 정확 일치
- lenient:      expected_tags ⊆ out.tags ⊆ accept_tags  AND  exclude 정확 일치
- jaccard:      |out.tags ∩ expected_tags| / |out.tags ∪ expected_tags|
- excl_exact:   set(out.exclude_tags) == set(expected_exclude_tags) (부정 처리 단독)

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
    output_tags: list[str]
    output_excludes: list[str]
    source: str  # 'claude'|'mock'|'fallback'
    exact: int
    lenient: int
    jaccard: float
    excl_exact: int  # 부정 처리 단독 정확도 (0/1)


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0  # 둘 다 빈 셋은 완전 일치로 간주
    inter = sa & sb
    union = sa | sb
    return len(inter) / len(union) if union else 0.0


def _score(
    out_tags: list[str],
    expected: list[str],
    accept: list[str],
    out_excludes: list[str],
    expected_excludes: list[str],
) -> tuple[int, int, float, int]:
    so, se, sa = set(out_tags), set(expected), set(accept)
    sox, sex = set(out_excludes), set(expected_excludes)

    pos_exact = so == se
    pos_lenient = se.issubset(so) and so.issubset(sa or se)
    excl_exact = sox == sex

    # combined: 긍정 통과 + 부정 통과 둘 다 만족해야 통과
    exact = 1 if (pos_exact and excl_exact) else 0
    lenient = 1 if (pos_lenient and excl_exact) else 0
    return exact, lenient, _jaccard(out_tags, expected), 1 if excl_exact else 0


def load_cases(path: Path = CASES_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run(cases: list[dict]) -> list[CaseResult]:
    out: list[CaseResult] = []
    for c in cases:
        r = extract_tags(c["query"])
        e, l, j, ex = _score(
            r.tags,
            c["expected_tags"],
            c["accept_tags"],
            r.exclude_tags,
            c.get("expected_exclude_tags", []),
        )
        out.append(
            CaseResult(
                case=c,
                output_tags=r.tags,
                output_excludes=r.exclude_tags,
                source=r.source,
                exact=e,
                lenient=l,
                jaccard=j,
                excl_exact=ex,
            )
        )
    return out


def print_case(res: CaseResult) -> None:
    c = res.case
    mark = "✓" if res.lenient else "✗"
    excl_out = res.output_excludes
    excl_exp = c.get("expected_exclude_tags", [])
    excl_part = ""
    if excl_out or excl_exp:
        em = "✓" if res.excl_exact else "✗"
        excl_part = f"  exclude{em} out={excl_out!s} exp={excl_exp!s}"
    print(
        f"  {mark} [{c['id']:11s}] {c['query']!r:<35s} "
        f"out={res.output_tags!s:30s} exp={c['expected_tags']!s:25s} "
        f"acc={c['accept_tags']!s:25s} j={res.jaccard:.2f}{excl_part}"
    )


def summarize(results: list[CaseResult]) -> None:
    by_cat: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by_cat[r.case["category"]].append(r)

    print("\n=== 카테고리별 ===")
    print(f"  {'카테고리':<18s} {'n':>3s}  {'exact':>7s}  {'lenient':>9s}  {'jaccard':>8s}  {'excl':>6s}")
    for cat in ["명확", "모호", "컨텍스트", "부정", "노이즈", "카테고리축 부재"]:
        rs = by_cat.get(cat, [])
        if not rs:
            continue
        n = len(rs)
        ex = sum(r.exact for r in rs) / n
        le = sum(r.lenient for r in rs) / n
        ja = sum(r.jaccard for r in rs) / n
        ec = sum(r.excl_exact for r in rs) / n
        print(f"  {cat:<18s} {n:>3d}  {ex*100:>6.1f}%  {le*100:>8.1f}%  {ja:>8.2f}  {ec*100:>5.1f}%")

    n = len(results)
    ex = sum(r.exact for r in results) / n
    le = sum(r.lenient for r in results) / n
    ja = sum(r.jaccard for r in results) / n
    ec = sum(r.excl_exact for r in results) / n
    sources = defaultdict(int)
    for r in results:
        sources[r.source] += 1
    print(f"\n=== 전체 ({n}건) ===")
    print(f"  exact      : {ex*100:5.1f}%   ({sum(r.exact for r in results)}/{n})")
    print(f"  lenient    : {le*100:5.1f}%   ({sum(r.lenient for r in results)}/{n})  ← 허용 범위 기준")
    print(f"  jaccard    : {ja:5.2f}")
    print(f"  excl_exact : {ec*100:5.1f}%   ({sum(r.excl_exact for r in results)}/{n})  ← 부정 처리 단독")
    print(f"  source     : {dict(sources)}")


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

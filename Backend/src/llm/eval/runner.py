"""평가셋 러너 — extract_tags() 정확도 측정.

다섯 메트릭:
- exact:        set(out.tags) == set(expected_tags)  AND  exclude 정확 일치
- lenient:      expected_tags ⊆ out.tags ⊆ accept_tags  AND  exclude 정확 일치
- jaccard:      |out.tags ∩ expected_tags| / |out.tags ∪ expected_tags|
- excl_exact:   set(out.exclude_tags) == set(expected_exclude_tags) (부정 처리 단독)
- fkw_subset:   expected_food_keywords 각 항목이 out.food_keywords에 들어있는지 (부분문자열).
                expected가 빈 배열이면 자동 통과 (open vocab이라 false-positive는 무시).
                cat-* 카테고리축 부재 케이스에서 의미 있는 회귀 신호.

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
    output_food_keywords: list[str]
    source: str  # 'claude'|'mock'|'fallback'
    exact: int
    lenient: int
    jaccard: float
    excl_exact: int  # 부정 처리 단독 정확도 (0/1)
    fkw_subset: int  # food_keywords 단독 정확도 (0/1) — expected가 비면 자동 1


def _jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0  # 둘 다 빈 셋은 완전 일치로 간주
    inter = sa & sb
    union = sa | sb
    return len(inter) / len(union) if union else 0.0


def _fkw_subset(out_fkw: list[str], expected_fkw: list[str]) -> int:
    """expected_food_keywords의 각 단어가 out_fkw의 어느 원소에든 substring으로 포함되면 1.

    open vocab이라 출력 변동성이 큼: Claude가 "고기" 대신 "고기류"라 답하거나, "회"
    대신 "사시미"만 답할 수 있다. 그래서 정확 일치가 아니라 'expected 단어 각각이
    output 어딘가에 substring으로 살아있는지'로 본다.
    expected가 비어 있으면 자동 통과(평가 대상 아님).
    """
    if not expected_fkw:
        return 1
    out_concat = " ".join(out_fkw).lower()
    return 1 if all(w.lower() in out_concat for w in expected_fkw) else 0


def _score(
    out_tags: list[str],
    expected: list[str],
    accept: list[str],
    out_excludes: list[str],
    expected_excludes: list[str],
    out_fkw: list[str],
    expected_fkw: list[str],
) -> tuple[int, int, float, int, int]:
    so, se, sa = set(out_tags), set(expected), set(accept)
    sox, sex = set(out_excludes), set(expected_excludes)

    pos_exact = so == se
    pos_lenient = se.issubset(so) and so.issubset(sa or se)
    excl_exact = sox == sex
    fkw_ok = _fkw_subset(out_fkw, expected_fkw)

    # combined: 긍정 통과 + 부정 통과 둘 다 만족해야 통과 (fkw는 단독 메트릭으로만 노출)
    exact = 1 if (pos_exact and excl_exact) else 0
    lenient = 1 if (pos_lenient and excl_exact) else 0
    return exact, lenient, _jaccard(out_tags, expected), 1 if excl_exact else 0, fkw_ok


def load_cases(path: Path = CASES_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def run(cases: list[dict]) -> list[CaseResult]:
    out: list[CaseResult] = []
    for c in cases:
        r = extract_tags(c["query"])
        e, l, j, ex, fk = _score(
            r.tags,
            c["expected_tags"],
            c["accept_tags"],
            r.exclude_tags,
            c.get("expected_exclude_tags", []),
            r.food_keywords,
            c.get("expected_food_keywords", []),
        )
        out.append(
            CaseResult(
                case=c,
                output_tags=r.tags,
                output_excludes=r.exclude_tags,
                output_food_keywords=r.food_keywords,
                source=r.source,
                exact=e,
                lenient=l,
                jaccard=j,
                excl_exact=ex,
                fkw_subset=fk,
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
    fkw_exp = c.get("expected_food_keywords", [])
    fkw_part = ""
    if res.output_food_keywords or fkw_exp:
        fm = "✓" if res.fkw_subset else "✗"
        fkw_part = (
            f"  food{fm} out={res.output_food_keywords!s} exp={fkw_exp!s}"
        )
    print(
        f"  {mark} [{c['id']:11s}] {c['query']!r:<35s} "
        f"out={res.output_tags!s:30s} exp={c['expected_tags']!s:25s} "
        f"acc={c['accept_tags']!s:25s} j={res.jaccard:.2f}{excl_part}{fkw_part}"
    )


def summarize(results: list[CaseResult]) -> None:
    by_cat: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by_cat[r.case["category"]].append(r)

    print("\n=== 카테고리별 ===")
    print(
        f"  {'카테고리':<18s} {'n':>3s}  {'exact':>7s}  {'lenient':>9s}  "
        f"{'jaccard':>8s}  {'excl':>6s}  {'fkw':>6s}"
    )
    for cat in ["명확", "모호", "컨텍스트", "부정", "노이즈", "카테고리축 부재"]:
        rs = by_cat.get(cat, [])
        if not rs:
            continue
        n = len(rs)
        ex = sum(r.exact for r in rs) / n
        le = sum(r.lenient for r in rs) / n
        ja = sum(r.jaccard for r in rs) / n
        ec = sum(r.excl_exact for r in rs) / n
        fk = sum(r.fkw_subset for r in rs) / n
        print(
            f"  {cat:<18s} {n:>3d}  {ex*100:>6.1f}%  {le*100:>8.1f}%  "
            f"{ja:>8.2f}  {ec*100:>5.1f}%  {fk*100:>5.1f}%"
        )

    n = len(results)
    ex = sum(r.exact for r in results) / n
    le = sum(r.lenient for r in results) / n
    ja = sum(r.jaccard for r in results) / n
    ec = sum(r.excl_exact for r in results) / n
    # fkw_subset은 expected가 비어있는 케이스가 자동 1이라 평균이 부풀려짐.
    # expected_food_keywords가 정의된 케이스만 모아 진짜 분모로 다시 집계한다.
    fkw_targets = [
        r for r in results if r.case.get("expected_food_keywords")
    ]
    sources = defaultdict(int)
    for r in results:
        sources[r.source] += 1
    print(f"\n=== 전체 ({n}건) ===")
    print(f"  exact      : {ex*100:5.1f}%   ({sum(r.exact for r in results)}/{n})")
    print(f"  lenient    : {le*100:5.1f}%   ({sum(r.lenient for r in results)}/{n})  ← 허용 범위 기준")
    print(f"  jaccard    : {ja:5.2f}")
    print(f"  excl_exact : {ec*100:5.1f}%   ({sum(r.excl_exact for r in results)}/{n})  ← 부정 처리 단독")
    if fkw_targets:
        fk_hits = sum(r.fkw_subset for r in fkw_targets)
        fk_n = len(fkw_targets)
        print(
            f"  fkw_subset : {fk_hits/fk_n*100:5.1f}%   ({fk_hits}/{fk_n})  "
            f"← food_keywords 단독 (expected 정의된 케이스만)"
        )
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

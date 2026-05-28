"""세트 메뉴 재분류 — Claude Batches로 IV+X 전략 실행.

§5.12 처음 enrich에서 세트 메뉴 처리가 거칠어서 '탕수육+짬뽕+만두' 같은
복수 주식 결합 세트가 kind=탕수육으로 잡힘. 결과로 짬뽕의 얼큰한·국물있는
태그가 탕수육 kind에 끌려 들어와 "얼큰한 국물" 검색에 탕수육이 뜨는 문제.

이 스크립트:
- menu_kinds.jsonl에서 '+', '세트', '셋트', 'SET'/'한글/한글' 패턴이 있는
  메뉴를 후보로 식별 (광범위 — false positive는 Claude가 판단해 단일로 분류).
- Claude가 각 후보에 대해 세트 정밀 분류 수행 (전략 X = 가장 변별력 있는
  음식 1개로). 사이드 추가형은 메인만, 복수 주식은 강한 신호 쪽, 정찬 코스는
  식당 업종 기반.
- 결과를 menu_kinds.jsonl에 부분 갱신 (영향 받은 메뉴만, 다른 행은 그대로).
- source는 "claude_reclassified"로 표시.

실행:
    cd Backend
    python scripts/reclassify_sets.py --dry-run        # 견적만
    python scripts/reclassify_sets.py                  # 본 실행
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

# Backend/ 를 import 경로에 추가
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.llm.kinds import (  # noqa: E402
    ALL_KIND_VALUES,
    CLAUDE_MODEL,
    KIND_OTHER,
    KIND_SCHEMA,
    classify_kind,
)

_HERE = pathlib.Path(__file__).resolve().parent
_BACKEND = _HERE.parent
KINDS_JSONL = _BACKEND / "src" / "llm" / "data" / "menu_kinds.jsonl"

# 세트 후보 인식 — 광범위. false positive (한우1++ 같은)는 Claude가 단일로 판단.
SET_PATTERN = re.compile(r"\+|세트|셋트|SET|set|[가-힣]/[가-힣]")

# Sonnet 4.6 단가. Batches 50% 할인.
PRICE_IN = 3.0
PRICE_OUT = 15.0
BATCH_DISCOUNT = 0.5
EST_TOK_PER_CHAR = 1.0
EST_OUT_TOK = 16  # {"kind":"..."} 짧은 응답

# 세트 정밀 분류용 system prompt — 기존 enrich 가이드 + 세트 처리 명시.
SET_SYSTEM_PROMPT = """\
한국어 메뉴명을 보고 음식 종류를 정확히 1개로 분류해.

이번 task = *세트/결합 메뉴 정밀 분류*:
- 입력은 '+', '세트', '셋트', 'SET' 같은 표시가 있어. 진짜 단일 음식일 수도,
  복수 주식 결합 세트일 수도 있어. 케이스별로 판단해.

판단 가이드:
1. *단일 음식 + 사이드/구성 추가형* ('해장국+숙주', '돈까스+육장+밥',
   '얼큰살코기해장국+숙주+당면'): 메인 음식만 분류. → '해장국', '돈까스'.
2. *복수 주식 결합형* ('탕수육+짬뽕+만두', '짜장+짬뽕', '깐풍기+짜장2',
   '한정식+초밥'): *가장 변별력 있는* 한 음식.
   - 변별력 = 매운맛·특이 재료·사용자 검색 의도가 *더 강한* 쪽
   - 예: '탕수육+짬뽕+만두' → '짬뽕' (얼큰함이 사용자가 검색할 강한 신호)
   - 예: '짜장+짬뽕' → '짬뽕' (얼큰함 더 강함)
   - 예: '깐풍기+짜장2' → '깐풍기' (특이/구체적 신호)
   - 모호하거나 둘 다 비슷하면 vocab에서 더 *구체적인* 쪽
3. *등급/할인/수량 표시* 무시:
   - '1++', '++', '1+1' → 무시. '한우1++ 꽃등심' → '꽃등심'
   - '2인', '3인', '4인' → 수량 표시. 음식 자체로 판단
4. *진짜 정찬 코스* ('패밀리세트 3인', '토치세트', '잘빠진세트', '코스'):
   식당 업종 기반 분류.
   - 일식 → '초밥' / 한식 → '한정식' 또는 '도시락' / 분식 → '도시락'
5. 메뉴명에 *세트 표시*는 있지만 실제론 단일 음식 ('매운세트(2인)'은 떡볶이집
   메뉴이므로 '떡볶이' 또는 식당 업종 한정식): 식당 업종 + 메뉴명 맥락으로 판단.

기존 분류 규칙 (변함 없음):
- 같은 메뉴 안에 여러 vocab이 매칭되면 *가장 구체적인* 쪽
  ('돼지국밥' > '국밥', '등심탕수육' > '탕수육', '내장탕'은 '내장탕'이지 '국밥' 아님)
- 글자 substring 매칭이 아니라 *음식의 조리법·재료·형태*로 판단
  ('소금구이'는 고기구이지 '소금빵' 아님)
- *진짜* 사이드/단품 (공기밥·단무지·반찬·소스·드레싱·리필·추가): "기타_사이드"
- 음료만: "기타_음료" / 주류만: "기타_주류"
- vocab에 가까운 게 정말 없으면 "기타". 글자 비슷한 단어 고르지 마.
"""


def _user_prompt(menu_name: str, category: str | None) -> str:
    cat = category or "(업종 불명)"
    return f"메뉴: {menu_name}\n식당 업종: {cat}\n→ 음식 종류 1개"


def estimate_cost(candidates: list[dict]) -> dict:
    sys_tok = len(SET_SYSTEM_PROMPT) * EST_TOK_PER_CHAR
    in_tok = 0.0
    for c in candidates:
        in_tok += sys_tok + len(_user_prompt(c["menu_name"], c["category"])) * EST_TOK_PER_CHAR
    out_tok = len(candidates) * EST_OUT_TOK
    cost = (in_tok / 1e6 * PRICE_IN + out_tok / 1e6 * PRICE_OUT) * BATCH_DISCOUNT
    return {
        "requests": len(candidates),
        "est_input_tokens": int(in_tok),
        "est_output_tokens": int(out_tok),
        "est_cost_usd": round(cost, 4),
    }


def load_all_rows() -> list[dict]:
    rows = []
    with KINDS_JSONL.open(encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def pick_set_candidates(rows: list[dict]) -> list[dict]:
    return [r for r in rows if SET_PATTERN.search(r["menu_name"])]


def build_requests(candidates: list[dict], Request, Params):
    reqs = []
    for i, c in enumerate(candidates):
        reqs.append(
            Request(
                custom_id=f"s{i}",
                params=Params(
                    model=CLAUDE_MODEL,
                    max_tokens=64,
                    system=[
                        {
                            "type": "text",
                            "text": SET_SYSTEM_PROMPT,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[
                        {"role": "user", "content": _user_prompt(c["menu_name"], c["category"])}
                    ],
                    output_config={
                        "format": {"type": "json_schema", "schema": KIND_SCHEMA}
                    },
                ),
            )
        )
    return reqs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="견적만 보고 종료")
    ap.add_argument("--yes", action="store_true", help="확인 프롬프트 건너뛰기")
    ap.add_argument("--poll", type=int, default=30, help="폴링 간격(초)")
    args = ap.parse_args()

    rows = load_all_rows()
    candidates = pick_set_candidates(rows)

    # 세트 후보가 어떤 kind에 분류돼 있는지 분포
    from collections import Counter
    kind_dist = Counter(c["kind"] for c in candidates)

    print("=== 세트 후보 식별 ===")
    print(f"전체 메뉴: {len(rows)}")
    print(f"세트 후보: {len(candidates)} ({100 * len(candidates) / len(rows):.1f}%)")
    print(f"현재 분류 top 10:")
    for k, n in kind_dist.most_common(10):
        print(f"  {k:20s} {n:4d}")

    est = estimate_cost(candidates)
    print()
    print("=== Claude Batches 재분류 견적 ===")
    print(f"요청 수: {est['requests']}  (모델 {CLAUDE_MODEL}, Batches 50% 할인)")
    print(f"vocab+OTHER enum: {len(ALL_KIND_VALUES)} 개")
    print(f"추정 입력 토큰: {est['est_input_tokens']:,}")
    print(f"추정 출력 토큰: {est['est_output_tokens']:,}")
    print(f"추정 비용: ${est['est_cost_usd']}  (한국어 토큰 추정, ±오차)")
    if args.dry_run:
        return

    if not args.yes:
        ans = input("\n진행할까요? [y/N] ").strip().lower()
        if ans != "y":
            print("취소됨.")
            return

    try:
        import anthropic
        from anthropic.types.message_create_params import (
            MessageCreateParamsNonStreaming as Params,
        )
        from anthropic.types.messages.batch_create_params import Request
    except ImportError:
        print("anthropic 미설치. pip install anthropic 후 다시 실행.")
        sys.exit(1)

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수

    print("배치 제출 중...")
    batch = client.messages.batches.create(
        requests=build_requests(candidates, Request, Params)
    )
    print(f"배치 ID: {batch.id}  상태: {batch.processing_status}")

    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        print(f"  진행 중... {batch.request_counts}")
        time.sleep(args.poll)
    print(f"완료: {batch.request_counts}")

    # 결과 수집 — idx → kind
    new_kind_by_idx: dict[int, str] = {}
    for result in client.messages.batches.results(batch.id):
        idx = int(result.custom_id[1:])
        if result.result.type == "succeeded":
            raw = next(
                (b.text for b in result.result.message.content if b.type == "text"), ""
            )
            try:
                k = json.loads(raw).get("kind")
                if k:
                    new_kind_by_idx[idx] = k
            except Exception:
                pass

    # 결과 통계 + 변경 사항 요약
    changed = 0
    unchanged = 0
    fallback = 0
    change_summary = Counter()
    for i, c in enumerate(candidates):
        if i in new_kind_by_idx:
            new_k = new_kind_by_idx[i]
            if new_k != c["kind"]:
                changed += 1
                change_summary[(c["kind"], new_k)] += 1
            else:
                unchanged += 1
        else:
            fallback += 1

    print()
    print("=== 재분류 결과 ===")
    print(f"Claude 성공: {len(new_kind_by_idx)} / 후보 {len(candidates)}")
    print(f"  변경됨: {changed}")
    print(f"  같음: {unchanged}")
    print(f"  폴백 필요: {fallback}")
    print(f"\n변경 패턴 top 15:")
    for (old, new), n in change_summary.most_common(15):
        print(f"  {old:15s} → {new:15s}  ({n})")

    # menu_kinds.jsonl 부분 갱신
    # 키 (store_id, menu_name)으로 후보 인덱스 매핑
    cand_key_to_idx = {(c["store_id"], c["menu_name"]): i for i, c in enumerate(candidates)}

    out = KINDS_JSONL
    new_rows = []
    for r in rows:
        key = (r["store_id"], r["menu_name"])
        if key in cand_key_to_idx:
            i = cand_key_to_idx[key]
            if i in new_kind_by_idx:
                # Claude 응답으로 갱신
                new_kind = new_kind_by_idx[i]
                new_rows.append(
                    {
                        **r,
                        "kind": new_kind,
                        "source": "claude_reclassified" if new_kind != r["kind"] else r["source"],
                    }
                )
                continue
            else:
                # Claude 실패 — 폴백: substring 또는 OTHER
                fb = classify_kind(r["menu_name"]) or KIND_OTHER
                new_rows.append({**r, "kind": fb, "source": "fallback_after_reclassify"})
                continue
        new_rows.append(r)

    with out.open("w", encoding="utf-8") as f:
        for r in new_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nmenu_kinds.jsonl 갱신 완료: {out}")
    print(f"  영향 받은 메뉴: {changed + fallback} / 전체 {len(rows)}")


if __name__ == "__main__":
    main()

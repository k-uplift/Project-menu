"""메뉴 태그 enrichment — Claude Batches API 일괄 호출 (50% 할인).

distinct 요리 전체를 Claude(Sonnet 4.6)로 태깅해 menu_tags.jsonl을 새로 쓴다.
실시간이 아니므로 Batches API를 쓴다(표준가의 50%). 실행 전 비용 견적을 보여주고
사용자 확인을 받는다. 실패/누락 요리는 휴리스틱으로 폴백한다.

실행:
    cd Backend
    export ANTHROPIC_API_KEY=sk-...
    pip install anthropic
    python scripts/enrich_menus.py              # 전체 재태깅 (확인 후 진행)
    python scripts/enrich_menus.py --dry-run    # 견적만 보고 종료
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

# Backend/ 를 import 경로에 추가 (src.llm.* 사용)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.llm.enrich import (  # noqa: E402
    CLAUDE_MODEL,
    DEFAULT_OUT,
    ENRICH_SCHEMA,
    ENRICH_SYSTEM_PROMPT,
    MAX_TAGS,
    _enrich_heuristic,
    _user_prompt,
    load_dishes,
)

# Sonnet 4.6 표준 단가($/1M 토큰). Batches는 절반.
PRICE_IN = 3.0
PRICE_OUT = 15.0
BATCH_DISCOUNT = 0.5
# 한국어는 대략 글자수보다 토큰이 많다 — 보수적으로 글자당 ~1토큰으로 추정.
EST_TOK_PER_CHAR = 1.0
EST_OUT_TOK = 20  # {"tags":[...]} 짧은 응답


def estimate_cost(dishes: list[tuple[int, str, str | None]]) -> dict:
    sys_tok = len(ENRICH_SYSTEM_PROMPT) * EST_TOK_PER_CHAR
    in_tok = 0.0
    for _, name, cat in dishes:
        in_tok += sys_tok + len(_user_prompt(name, cat)) * EST_TOK_PER_CHAR
    out_tok = len(dishes) * EST_OUT_TOK
    cost = (in_tok / 1e6 * PRICE_IN + out_tok / 1e6 * PRICE_OUT) * BATCH_DISCOUNT
    return {
        "requests": len(dishes),
        "est_input_tokens": int(in_tok),
        "est_output_tokens": int(out_tok),
        "est_cost_usd": round(cost, 4),
    }


def build_requests(dishes, Request, Params):
    """custom_id = 'd{index}'. dishes 순서로 결과를 되짚는다."""
    reqs = []
    for i, (_, name, cat) in enumerate(dishes):
        reqs.append(
            Request(
                custom_id=f"d{i}",
                params=Params(
                    model=CLAUDE_MODEL,
                    max_tokens=128,
                    system=[
                        {
                            "type": "text",
                            "text": ENRICH_SYSTEM_PROMPT,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": _user_prompt(name, cat)}],
                    output_config={
                        "format": {"type": "json_schema", "schema": ENRICH_SCHEMA}
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

    dishes = load_dishes()
    est = estimate_cost(dishes)
    print("=== Claude Batches enrichment 견적 ===")
    print(f"요청 수: {est['requests']}  (모델 {CLAUDE_MODEL}, Batches 50% 할인)")
    print(f"추정 입력 토큰: {est['est_input_tokens']:,}")
    print(f"추정 출력 토큰: {est['est_output_tokens']:,}")
    print(f"추정 비용: ${est['est_cost_usd']}  (한국어 토큰 추정이라 ±오차)")
    if args.dry_run:
        return

    if not args.yes:
        ans = input("진행할까요? [y/N] ").strip().lower()
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

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 사용

    print("배치 제출 중...")
    batch = client.messages.batches.create(requests=build_requests(dishes, Request, Params))
    print(f"배치 ID: {batch.id}  상태: {batch.processing_status}")

    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        print(f"  진행 중... {batch.request_counts}")
        time.sleep(args.poll)
    print(f"완료: {batch.request_counts}")

    # 결과 수집 — custom_id 'd{i}' → dishes[i]
    tags_by_idx: dict[int, list[str]] = {}
    for result in client.messages.batches.results(batch.id):
        idx = int(result.custom_id[1:])
        if result.result.type == "succeeded":
            raw = next(
                (b.text for b in result.result.message.content if b.type == "text"), ""
            )
            try:
                tags_by_idx[idx] = list(json.loads(raw).get("tags", []))[:MAX_TAGS]
            except Exception:
                tags_by_idx[idx] = []  # 파싱 실패 → 폴백 처리됨(아래)

    # 작성: 성공분은 claude, 실패/누락분은 휴리스틱 폴백
    out = pathlib.Path(DEFAULT_OUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    claude_n = fallback_n = 0
    with out.open("w", encoding="utf-8") as f:
        for i, (store_id, name, cat) in enumerate(dishes):
            if i in tags_by_idx:
                tags, source = tags_by_idx[i], "claude"
                claude_n += 1
            else:
                r = _enrich_heuristic(name, cat)
                tags, source = r.tags, "heuristic"
                fallback_n += 1
            f.write(
                json.dumps(
                    {
                        "store_id": store_id,
                        "menu_name": name,
                        "category": cat,
                        "tags": tags,
                        "source": source,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"작성 완료: {out}  (claude {claude_n} · 폴백 {fallback_n})")


if __name__ == "__main__":
    main()

"""음식 종류 enrichment — Claude Batches API 일괄 분류 (50% 할인).

메뉴 5,813개 전체를 Claude(Sonnet 4.6, enum 잠금)로 음식 종류 1개씩 분류해
`data/menu_kinds.jsonl`로 저장한다. 추천 단위가 raw 메뉴명에서 "음식 종류"
(메밀·스시·돈까스·김치찌개 등 vocab ~363개)로 한 단계 위로 올라간다.

실행:
    cd Backend
    python scripts/enrich_kinds.py --dry-run        # 견적만 확인
    python scripts/enrich_kinds.py                  # 본 실행 (확인 후 진행)

폴백: Claude 실패분은 substring 매칭(classify_kind) + OTHER 안전망.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

# Backend/ 를 import 경로에 추가
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.llm.enrich import load_dishes  # noqa: E402
from src.llm.kinds import (  # noqa: E402
    CLAUDE_MODEL,
    KIND_OTHER,
    KIND_SCHEMA,
    KIND_SYSTEM_PROMPT,
    _kind_user_prompt,
    classify_kind,
)

_HERE = pathlib.Path(__file__).resolve().parent
_BACKEND = _HERE.parent
DEFAULT_OUT = _BACKEND / "src" / "llm" / "data" / "menu_kinds.jsonl"

# Sonnet 4.6 단가. Batches는 50% 할인.
PRICE_IN = 3.0
PRICE_OUT = 15.0
BATCH_DISCOUNT = 0.5
EST_TOK_PER_CHAR = 1.0
EST_OUT_TOK = 12  # {"kind":"..."} 짧은 응답


def estimate_cost(dishes: list[tuple[int, str, str | None]]) -> dict:
    sys_tok = len(KIND_SYSTEM_PROMPT) * EST_TOK_PER_CHAR
    in_tok = 0.0
    for _, name, cat in dishes:
        in_tok += sys_tok + len(_kind_user_prompt(name, cat)) * EST_TOK_PER_CHAR
    out_tok = len(dishes) * EST_OUT_TOK
    cost = (in_tok / 1e6 * PRICE_IN + out_tok / 1e6 * PRICE_OUT) * BATCH_DISCOUNT
    return {
        "requests": len(dishes),
        "est_input_tokens": int(in_tok),
        "est_output_tokens": int(out_tok),
        "est_cost_usd": round(cost, 4),
    }


def build_requests(dishes, Request, Params):
    """custom_id = 'd{index}'. dishes 순서로 결과 매핑."""
    reqs = []
    for i, (_, name, cat) in enumerate(dishes):
        reqs.append(
            Request(
                custom_id=f"d{i}",
                params=Params(
                    model=CLAUDE_MODEL,
                    max_tokens=64,
                    system=[
                        {
                            "type": "text",
                            "text": KIND_SYSTEM_PROMPT,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": _kind_user_prompt(name, cat)}],
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

    dishes = load_dishes()
    est = estimate_cost(dishes)
    print("=== Claude Batches 음식 종류 분류 견적 ===")
    print(f"요청 수: {est['requests']}  (모델 {CLAUDE_MODEL}, Batches 50% 할인)")
    print(f"vocab 크기: {len(KIND_SCHEMA['properties']['kind']['enum'])} (OTHER 4종 포함)")
    print(f"추정 입력 토큰: {est['est_input_tokens']:,}")
    print(f"추정 출력 토큰: {est['est_output_tokens']:,}")
    print(f"추정 비용: ${est['est_cost_usd']}  (한국어 토큰 추정, ±오차)")
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

    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수

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

    # 결과 수집
    kind_by_idx: dict[int, str] = {}
    for result in client.messages.batches.results(batch.id):
        idx = int(result.custom_id[1:])
        if result.result.type == "succeeded":
            raw = next(
                (b.text for b in result.result.message.content if b.type == "text"), ""
            )
            try:
                k = json.loads(raw).get("kind")
                if k:
                    kind_by_idx[idx] = k
            except Exception:
                pass  # 폴백 처리

    # 작성: claude 성공 → claude, 실패 → substring → 그래도 없으면 KIND_OTHER
    out = pathlib.Path(DEFAULT_OUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    claude_n = sub_n = other_n = 0
    with out.open("w", encoding="utf-8") as f:
        for i, (store_id, name, cat) in enumerate(dishes):
            if i in kind_by_idx:
                kind, source = kind_by_idx[i], "claude"
                claude_n += 1
            else:
                k = classify_kind(name)
                if k:
                    kind, source = k, "substring"
                    sub_n += 1
                else:
                    kind, source = KIND_OTHER, "fallback"
                    other_n += 1
            f.write(
                json.dumps(
                    {
                        "store_id": store_id,
                        "menu_name": name,
                        "category": cat,
                        "kind": kind,
                        "source": source,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(f"작성 완료: {out}")
    print(f"  claude {claude_n} · substring {sub_n} · 기타폴백 {other_n}")


if __name__ == "__main__":
    main()

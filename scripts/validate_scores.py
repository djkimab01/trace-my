"""2일차: 뉴스 점수 검증 — workbench/day2/outputs/news_scored.jsonl을 원문과 대조한다.

검사: (1) 줄 수 = 100 (2) news_sent_0_10이 0–10 정수
      (3) label이 점수 대역과 일치(0–2 severe · 3–4 high · 5 watch · 6–10 low)
      (4) evidence가 원문 headline · body_short 안에 글자 그대로 있음
입력(읽기만): workbench/day2/outputs/news_scored.jsonl · data/checkpoints/d2_news.csv
출력: 위반 행 목록(화면). 위반이 있으면 종료 코드 1.
실행: uv run python scripts/validate_scores.py
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCORED = ROOT / "workbench/day2/outputs/news_scored.jsonl"
NEWS = ROOT / "data/checkpoints/d2_news.csv"
EXPECTED_LINES = 100


def band(score):
    if score <= 2:
        return "severe"
    if score <= 4:
        return "high"
    if score == 5:
        return "watch"
    return "low"


def main():
    with open(NEWS, encoding="utf-8-sig", newline="") as f:
        news = {r["news_id"]: r for r in csv.DictReader(f)}
    lines = SCORED.read_text(encoding="utf-8").splitlines()

    problems = []  # (줄 번호, news_id, 사유)
    if len(lines) != EXPECTED_LINES:
        problems.append((0, "-", f"줄 수 {len(lines)} ≠ {EXPECTED_LINES}"))

    for no, line in enumerate(lines, 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            problems.append((no, "-", f"JSON 파싱 실패: {e}"))
            continue
        nid = row.get("news_id", "-")
        score = row.get("news_sent_0_10")
        # bool은 int의 하위형이라 따로 막는다
        if not (isinstance(score, int) and not isinstance(score, bool) and 0 <= score <= 10):
            problems.append((no, nid, f"점수가 0–10 정수가 아님: {score!r}"))
        elif row.get("label") != band(score):
            problems.append((no, nid, f"라벨 불일치: {row.get('label')!r} (점수 {score} → {band(score)})"))
        src = news.get(nid)
        if src is None:
            problems.append((no, nid, "원문에 없는 news_id"))
            continue
        evidence = row.get("evidence") or ""
        if not evidence or (evidence not in src["headline"] and evidence not in src["body_short"]):
            problems.append((no, nid, f"evidence가 원문에 없음: {evidence!r}"))

    print(f"검사 줄 수: {len(lines)} · 위반: {len(problems)}건")
    for no, nid, why in problems:
        print(f"  줄 {no} · {nid} · {why}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

"""2일차: 바이어 정제 — workbench/day2/rules/정제규칙.md 1–7칸을 그대로 옮긴 스크립트.

입력(읽기만): data/checkpoints/d2_start.xlsx(buyers · fx_at_ref) · data/checkpoints/fx_krw_daily.csv
출력: workbench/day2/outputs/d2_buyers_clean.csv · workbench/day2/outputs/dq_report.md
실행: uv run python scripts/clean_buyers.py
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data/checkpoints/d2_start.xlsx"
FX_DAILY = ROOT / "data/checkpoints/fx_krw_daily.csv"
OUT = ROOT / "workbench/day2/outputs"
AS_OF = pd.Timestamp("2026-08-31")
LAG_DATE = pd.Timestamp("2026-08-01")  # 칸 7: 30일 전 시점

# 칸 1. 통화 매핑(raw → clean)
MAP_CCY = {"USD": "USD", "usd": "USD", "US$": "USD",
           "EUR": "EUR", "euro": "EUR",
           "JPY": "JPY", "yen": "JPY",
           "CNY": "CNY", "RMB": "CNY"}
AR_COLS = ["ar_balance", "ar_current", "ar_1_30", "ar_31_60", "ar_61_90", "ar_91p"]
FIN5 = ["current_assets", "current_liabilities", "total_liabilities", "equity", "revenue"]
FIN7 = FIN5 + ["accounts_receivable", "operating_income"]
FX_COL = {"USD": "usd_krw", "EUR": "eur_krw", "CNY": "cny_krw", "JPY": "jpy100_krw"}
FX_CCY = {"USD": "USD", "EUR": "EUR", "CNY": "CNY", "JPY": "JPY100"}
OUT_COLS = ["buyer_id", "payment_method", "ccy_clean", "amt_num", "ar_balance_usd",
            "pct_current", "pct_ar_31p", "pct_91plus", "max_dpd", "avg_days_late",
            "late_ratio", "dpd_trend", "dispute_ratio", "current_ratio", "debt_to_equity",
            "dso_buyer", "op_margin", "fin_missing", "neg_equity", "country_risk",
            "crc_unclassified", "unit_flag", "fx_chg_30d", "fx_chg_30d_lag30", "late_30d"]


def to_num(v):
    """칸 2. 콤마 · 공백 · 통화 글자 제거, 끝의 k는 ×1,000. 실패하면 멈춘다."""
    if pd.isna(v):
        return float("nan")
    s = str(v).strip().replace(",", "")
    s = re.sub(r"US\$|USD|EUR|CNY|JPY", "", s).strip()
    mult = 1000 if s.lower().endswith("k") else 1
    s = s[:-1] if mult == 1000 else s
    try:
        return float(s) * mult
    except ValueError:
        raise ValueError(f"숫자 변환 실패: {v!r} — 규칙 문서 칸 2에 패턴을 더한 뒤 다시 실행")


def is_text_num(v):
    return not re.fullmatch(r"-?\d+(\.\d+)?", str(v))


def safe_div(a, b):
    return a / b.where(b != 0)


def md_table(df):
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(x) else str(x) for x in r) + " |")
    return "\n".join(lines)


def main():
    raw = pd.read_excel(SRC, sheet_name="buyers")
    fx_ref = pd.read_excel(SRC, sheet_name="fx_at_ref")
    fx_d = pd.read_csv(FX_DAILY, encoding="utf-8-sig", parse_dates=["date"]).set_index("date").sort_index()
    b = raw.copy()

    # 칸 1. 통화
    unknown = set(b["currency"].dropna()) - set(MAP_CCY)
    if unknown or b["currency"].isna().any():
        raise ValueError(f"매핑에 없는 통화 표기: {unknown} — 칸 1 확인")
    b["ccy_clean"] = b["currency"].map(MAP_CCY)

    # 칸 2. 숫자 변환
    for c in AR_COLS:
        b[c + "_num"] = b[c].map(to_num)
    b["amt_num"] = b["ar_balance_num"]

    # 칸 7. 환율 — 기준일 2026-08-31 행만 쓴다(2026-09-30 행은 미래 정보)
    ref = fx_ref[fx_ref["ref_date"] == AS_OF].set_index("ccy")
    usd_krw = ref.loc["USD", "krw_close"]
    per_usd = {c: ref.loc[FX_CCY[c], "krw_close"] / (100 if c == "JPY" else 1) / usd_krw for c in FX_CCY}
    b["ar_balance_usd"] = b["amt_num"] * b["ccy_clean"].map(per_usd)
    b["fx_chg_30d"] = b["ccy_clean"].map(lambda c: ref.loc[FX_CCY[c], "chg_30d"])

    def chg_30d(col, t):  # t(또는 직전 영업일) 종가 ÷ 그 30일 전(또는 직전 영업일) 종가 − 1
        s = fx_d[col]
        t1 = s.loc[:t].index[-1]
        t0 = s.loc[:t1 - pd.Timedelta(days=30)].index[-1]
        return s[t1] / s[t0] - 1, t1, t0

    lag = {c: chg_30d(FX_COL[c], LAG_DATE) for c in FX_COL}
    b["fx_chg_30d_lag30"] = b["ccy_clean"].map(lambda c: round(lag[c][0], 4))
    # 같은 계산식이 fx_at_ref의 chg_30d(기준일)를 재현하는지 점검
    fx_check = [(c, round(chg_30d(FX_COL[c], AS_OF)[0], 4), ref.loc[FX_CCY[c], "chg_30d"]) for c in FX_COL]

    # 칸 4. 단위 의심 — 값은 고치지 않는다
    b["unit_flag"] = (b["ar_balance_usd"] > b["credit_limit_usd"] * 10).astype(int)
    bucket_sum = b[[c + "_num" for c in AR_COLS[1:]]].sum(axis=1)
    b["bucket_gap"] = b["amt_num"] - bucket_sum

    # 칸 5. 자본잠식 — 채우기 전 원값으로
    b["neg_equity"] = (b["equity"] <= 0).astype(int)

    # 칸 3. 결측 — 플래그 먼저, 그다음 150개사 전체 중위수
    b["fin_missing"] = b[FIN5].isna().any(axis=1).astype(int)
    medians = b[FIN7].median()
    nulls_before = b[FIN7].isna().sum()
    b[FIN7] = b[FIN7].fillna(medians)

    # 칸 6. 국가위험
    crc = pd.to_numeric(b["oecd_crc"].replace("-", pd.NA), errors="coerce")
    b["crc_unclassified"] = crc.isna().astype(int)
    b["country_risk"] = crc.fillna(0).astype(int)

    # 파생 특성
    tot = bucket_sum  # 구간 합계를 분모로 — 비율 합이 1이 되게(B072처럼 잔액과 다를 수 있음)
    b["pct_current"] = safe_div(b["ar_current_num"], tot).fillna(0)
    b["pct_ar_31p"] = safe_div(b[["ar_31_60_num", "ar_61_90_num", "ar_91p_num"]].sum(axis=1), tot).fillna(0)
    b["pct_91plus"] = safe_div(b["ar_91p_num"], tot).fillna(0)
    b["avg_days_late"] = b["avg_days_late_12m"]
    b["late_ratio"] = safe_div(b["late_invoices_12m"], b["invoices_12m"])
    b["dpd_trend"] = b["avg_dpd_last3m"] - b["avg_dpd_prev3m"]
    b["dispute_ratio"] = safe_div(b["dispute_cnt_12m"], b["invoices_12m"])
    b["current_ratio"] = safe_div(b["current_assets"], b["current_liabilities"])
    b["debt_to_equity"] = safe_div(b["total_liabilities"], b["equity"]).where(b["neg_equity"] == 0)
    b["dso_buyer"] = safe_div(b["accounts_receivable"], b["revenue"]) * 365
    b["op_margin"] = safe_div(b["operating_income"], b["revenue"])

    out = b[OUT_COLS].round(4)
    assert len(out) == 150 and out["buyer_id"].is_unique
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT / "d2_buyers_clean.csv", index=False, encoding="utf-8-sig")

    # ---- dq_report.md ----
    before_after = pd.DataFrame([
        ["통화 표기 종류", raw["currency"].nunique(), out["ccy_clean"].nunique(), "칸 1"],
        ["숫자 칸의 문자 값(ar_*)", int(sum(raw[c].map(is_text_num).sum() for c in AR_COLS)), 0, "칸 2"],
        ["재무 7열 빈칸 합계", int(nulls_before.sum()), int(b[FIN7].isna().sum().sum()), "칸 3 중위수"],
        ["fin_missing = 1", "–", int(out["fin_missing"].sum()), "칸 3"],
        ["unit_flag = 1", "–", int(out["unit_flag"].sum()), "칸 4 값은 그대로"],
        ["neg_equity = 1", int((raw["equity"] <= 0).sum()), int(out["neg_equity"].sum()), "칸 5"],
        ["oecd_crc \"-\"", int((raw["oecd_crc"].astype(str) == "-").sum()), int(out["crc_unclassified"].sum()), "칸 6 → country_risk 0"],
        ["행 수 · buyer_id 중복", f"{len(raw)} · {raw['buyer_id'].duplicated().sum()}", f"{len(out)} · {out['buyer_id'].duplicated().sum()}", ""],
    ], columns=["항목", "전", "후", "규칙"])

    ccy_tbl = raw["currency"].value_counts().rename_axis("원천 표기").reset_index(name="행")
    ccy_tbl["→ ccy_clean"] = ccy_tbl["원천 표기"].map(MAP_CCY)

    text_rows = []
    for c in AR_COLS:
        for i in raw.index[raw[c].map(is_text_num)]:
            text_rows.append([raw.at[i, "buyer_id"], c, repr(raw.at[i, c]), b.at[i, c + "_num"]])
    text_tbl = pd.DataFrame(text_rows, columns=["buyer_id", "열", "원천", "변환"])

    med_tbl = pd.DataFrame({"열": FIN7, "빈칸(전)": nulls_before.values,
                            "채운 중위수(USD)": medians.values, "빈칸(후)": b[FIN7].isna().sum().values})

    flag_tbl = b.loc[b["unit_flag"] == 1, ["buyer_id", "ccy_clean", "amt_num", "ar_balance_usd", "credit_limit_usd"]].copy()
    flag_tbl["배수"] = (flag_tbl["ar_balance_usd"] / flag_tbl["credit_limit_usd"]).round(1)
    flag_tbl["ar_balance_usd"] = flag_tbl["ar_balance_usd"].round(0)
    gap_tbl = b.loc[b["bucket_gap"].abs() > 1, ["buyer_id", "ar_balance", "amt_num", "bucket_gap"]]
    neg_tbl = raw.loc[raw["equity"] <= 0, ["buyer_id", "equity", "total_liabilities"]]

    fx_tbl = pd.DataFrame([[c, round(per_usd[c], 6), ref.loc[FX_CCY[c], "chg_30d"], round(lag[c][0], 4),
                            f"{lag[c][1]:%Y-%m-%d} / {lag[c][2]:%Y-%m-%d}"] for c in FX_COL],
                          columns=["ccy", "USD per 1단위", "fx_chg_30d", "fx_chg_30d_lag30", "lag30 관측일(t1 / t0)"])
    chk_tbl = pd.DataFrame(fx_check, columns=["ccy", "일별로 다시 계산", "fx_at_ref chg_30d"])

    na_out = out.isna().sum()[lambda s: s > 0].rename_axis("열").reset_index(name="빈칸")

    report = f"""# 데이터 품질 보고서 — 바이어 정제 전·후 (2일차)

- 입력(읽기만): `data/checkpoints/d2_start.xlsx`(buyers · fx_at_ref), `data/checkpoints/fx_krw_daily.csv`
- 출력: `workbench/day2/outputs/d2_buyers_clean.csv`({len(out)}행 × {out.shape[1]}열)
- 규칙: `workbench/day2/rules/정제규칙.md` 1–7칸 · 코드: `scripts/clean_buyers.py` · 기준일 {AS_OF:%Y-%m-%d}

## 1. 전·후 요약
{md_table(before_after)}

## 2. 통화 표기 → ccy_clean (칸 1)
{md_table(ccy_tbl)}

## 3. 숫자 칸의 문자 값 변환 (칸 2)
{md_table(text_tbl)}

## 4. 결측 채우기 (칸 3)
`fin_missing` = 유동자산·유동부채·총부채·자기자본·매출 중 하나라도 빈칸이면 1 → {int(out['fin_missing'].sum())}곳. 플래그를 먼저 만든 뒤 150개사 전체 중위수로 채움.

{md_table(med_tbl)}

## 5. 단위 의심 (칸 4) — 값은 고치지 않음, 원천 확인 필요
기준: `ar_balance_usd > credit_limit_usd × 10`

{md_table(flag_tbl)}

잔액(`amt_num`)과 구간 합계(`ar_current`~`ar_91p`)가 1 넘게 다른 행:

{md_table(gap_tbl)}

## 6. 자본잠식 (칸 5) — debt_to_equity 빈칸
{md_table(neg_tbl)}

## 7. 환율 (칸 7)
{md_table(fx_tbl)}

계산식 점검 — 같은 식(t 또는 직전 영업일 종가 ÷ t−30일 또는 직전 영업일 종가 − 1)으로 기준일 값을 다시 계산해 fx_at_ref와 비교:

{md_table(chk_tbl)}

## 8. 결과 파일에 남은 빈칸
{md_table(na_out) if len(na_out) else '없음'}

## 9. 파생 열 계산식
| 열 | 계산 |
|---|---|
| pct_current · pct_ar_31p · pct_91plus | 구간 잔액 ÷ 구간 합계(`ar_current`~`ar_91p`). 잔액 0이면 0 |
| ar_balance_usd | amt_num × 기준일 환율(통화 KRW ÷ USD KRW, JPY는 ÷100) |
| avg_days_late | avg_days_late_12m 그대로(채우지 않음) |
| late_ratio · dispute_ratio | late_invoices_12m · dispute_cnt_12m ÷ invoices_12m(0건이면 빈칸) |
| dpd_trend | avg_dpd_last3m − avg_dpd_prev3m(둘 중 빈칸이면 빈칸) |
| current_ratio | current_assets ÷ current_liabilities |
| debt_to_equity | total_liabilities ÷ equity, neg_equity = 1이면 빈칸 |
| dso_buyer | accounts_receivable ÷ revenue × 365 |
| op_margin | operating_income ÷ revenue |
"""
    (OUT / "dq_report.md").write_text(report, encoding="utf-8")
    print(f"저장: {OUT / 'd2_buyers_clean.csv'} {out.shape}")
    print(f"저장: {OUT / 'dq_report.md'}")


if __name__ == "__main__":
    main()

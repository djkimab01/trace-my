# 데이터 품질 보고서 — 바이어 정제 전·후 (2일차)

- 입력(읽기만): `data/checkpoints/d2_start.xlsx`(buyers · fx_at_ref), `data/checkpoints/fx_krw_daily.csv`
- 출력: `workbench/day2/outputs/d2_buyers_clean.csv`(150행 × 25열)
- 규칙: `workbench/day2/rules/정제규칙.md` 1–7칸 · 코드: `scripts/clean_buyers.py` · 기준일 2026-08-31

## 1. 전·후 요약
| 항목 | 전 | 후 | 규칙 |
|---|---|---|---|
| 통화 표기 종류 | 9 | 4 | 칸 1 |
| 숫자 칸의 문자 값(ar_*) | 13 | 0 | 칸 2 |
| 재무 7열 빈칸 합계 | 203 | 0 | 칸 3 중위수 |
| fin_missing = 1 | – | 47 | 칸 3 |
| unit_flag = 1 | – | 1 | 칸 4 값은 그대로 |
| neg_equity = 1 | 2 | 2 | 칸 5 |
| oecd_crc "-" | 57 | 57 | 칸 6 → country_risk 0 |
| 행 수 · buyer_id 중복 | 150 · 0 | 150 · 0 |  |

## 2. 통화 표기 → ccy_clean (칸 1)
| 원천 표기 | 행 | → ccy_clean |
|---|---|---|
| USD | 81 | USD |
| EUR | 18 | EUR |
| US$ | 15 | USD |
| usd | 14 | USD |
| JPY | 8 | JPY |
| CNY | 5 | CNY |
| euro | 5 | EUR |
| RMB | 2 | CNY |
| yen | 2 | JPY |

## 3. 숫자 칸의 문자 값 변환 (칸 2)
| buyer_id | 열 | 원천 | 변환 |
|---|---|---|---|
| B005 | ar_balance | ' 195900 ' | 195900.0 |
| B009 | ar_balance | 'CNY 317,000' | 317000.0 |
| B015 | ar_balance | '7,680' | 7680.0 |
| B034 | ar_balance | '200,520' | 200520.0 |
| B043 | ar_balance | '155,200 CNY' | 155200.0 |
| B083 | ar_balance | '2,200' | 2200.0 |
| B086 | ar_balance | 'EUR 143,620' | 143620.0 |
| B114 | ar_balance | ' 1458000 ' | 1458000.0 |
| B141 | ar_balance | '47.0k' | 47000.0 |
| B076 | ar_current | '51,970' | 51970.0 |
| B091 | ar_current | '7,980' | 7980.0 |
| B008 | ar_1_30 | '6,850' | 6850.0 |
| B072 | ar_1_30 | '8,320' | 8320.0 |

## 4. 결측 채우기 (칸 3)
`fin_missing` = 유동자산·유동부채·총부채·자기자본·매출 중 하나라도 빈칸이면 1 → 47곳. 플래그를 먼저 만든 뒤 150개사 전체 중위수로 채움.

| 열 | 빈칸(전) | 채운 중위수(USD) | 빈칸(후) |
|---|---|---|---|
| current_assets | 18 | 17593000.0 | 0 |
| current_liabilities | 39 | 11560000.0 | 0 |
| total_liabilities | 18 | 22628500.0 | 0 |
| equity | 34 | 14948000.0 | 0 |
| revenue | 18 | 44007000.0 | 0 |
| accounts_receivable | 39 | 6499000.0 | 0 |
| operating_income | 37 | 1704000.0 | 0 |

## 5. 단위 의심 (칸 4) — 값은 고치지 않음, 원천 확인 필요
기준: `ar_balance_usd > credit_limit_usd × 10`

| buyer_id | ccy_clean | amt_num | ar_balance_usd | credit_limit_usd | 배수 |
|---|---|---|---|---|---|
| B072 | EUR | 8320000.0 | 9665368.0 | 10000 | 966.5 |

잔액(`amt_num`)과 구간 합계(`ar_current`~`ar_91p`)가 1 넘게 다른 행:

| buyer_id | ar_balance | amt_num | bucket_gap |
|---|---|---|---|
| B072 | 8320000 | 8320000.0 | 8311680.0 |
| B141 | 47.0k | 47000.0 | -30.0 |

## 6. 자본잠식 (칸 5) — debt_to_equity 빈칸
| buyer_id | equity | total_liabilities |
|---|---|---|
| B013 | -15126000.0 | 109262000.0 |
| B048 | -37662000.0 | 160609000.0 |

## 7. 환율 (칸 7)
| ccy | USD per 1단위 | fx_chg_30d | fx_chg_30d_lag30 | lag30 관측일(t1 / t0) |
|---|---|---|---|---|
| USD | 1.0 | -0.0477 | -0.0734 | 2026-07-31 / 2026-07-01 |
| EUR | 1.161703 | -0.0396 | -0.0624 | 2026-07-31 / 2026-07-01 |
| CNY | 0.148818 | -0.0433 | -0.0674 | 2026-07-31 / 2026-07-01 |
| JPY | 0.00626 | -0.0512 | -0.0545 | 2026-07-31 / 2026-07-01 |

계산식 점검 — 같은 식(t 또는 직전 영업일 종가 ÷ t−30일 또는 직전 영업일 종가 − 1)으로 기준일 값을 다시 계산해 fx_at_ref와 비교:

| ccy | 일별로 다시 계산 | fx_at_ref chg_30d |
|---|---|---|
| USD | -0.0477 | -0.0477 |
| EUR | -0.0396 | -0.0396 |
| CNY | -0.0433 | -0.0433 |
| JPY | -0.0512 | -0.0512 |

## 8. 결과 파일에 남은 빈칸
| 열 | 빈칸 |
|---|---|
| avg_days_late | 11 |
| late_ratio | 11 |
| dpd_trend | 55 |
| dispute_ratio | 11 |
| debt_to_equity | 2 |

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

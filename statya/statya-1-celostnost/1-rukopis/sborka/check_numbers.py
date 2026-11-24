"""Сверка чисел табл. 4 и ключевых чисел текста с results/*.csv (версия 3.7)."""
import csv, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import build_ms as B
R = Path(__file__).resolve().parents[2] / "5-eksperiment" / "results"
t4 = {r["method"]: r for r in csv.DictReader(open(R / "rev_table4.csv", encoding="utf-8"))}
pm = {r["metric"]: r for r in csv.DictReader(open(R / "declare_pm4py.csv", encoding="utf-8"))}
f1 = lambda v: f"{100*float(v):.1f}".replace(".", ",")
ci = lambda r, k: f"{f1(r[k])} ({f1(r[k+'_lo'])}–{f1(r[k+'_hi'])})"
name = {"Б / B": "B2", "М / M": "B3", "М с допусками П": "B3-Ptol", "П без правил доверия": "P_v2",
        "П с единым окном": "P-beta", "П без удержания": "P-nohold", "П без группы T": "P-T", "П / P": "P"}
bad = 0
for row in B.T4_ROWS[1:]:
    key = next((k for k in name if row[0].startswith(k)), None)
    if key is None:          # pm4py
        exp = [f"{f1(pm['B4_fpr']['share'])} ({f1(pm['B4_fpr']['lo'])}–{f1(pm['B4_fpr']['hi'])})",
               f"{f1(pm['B4_recall_subst']['share'])} ({f1(pm['B4_recall_subst']['lo'])}–{f1(pm['B4_recall_subst']['hi'])})",
               f1(pm["B4_recall_all"]["share"])]
        got = row[1:4]
    else:
        r = t4[name[key]]
        exp = [ci(r, "fpr"), ci(r, "subst"), f1(r["integrity"]), f1(r["before_d1"]),
               str(round(float(r["lat_p90"]))), str(int(float(r["false_decisions_KV"])))]
        got = row[1:7]
    if exp != got:
        bad += 1
        print("MISMATCH", row[0].split("\n")[0], got, exp)
ce = {(r["method"], r["q_miss"]): float(r["false_decisions_KV"]) for r in
      csv.DictReader(open(R / "rev_check_error.csv", encoding="utf-8"))}
checks = [("799", int(ce[("P", "0.5")] + 0.5)), ("812", round(ce[("P-nohold", "0.5")])),
          ("854", round(ce[("P", "1.0")])), ("862", round(ce[("P-nohold", "1.0")]))]
for s, v in checks:
    if str(v) != s or s not in B.R_DEC:
        bad += 1; print("MISMATCH check_error", s, v)
print("OK" if not bad else f"{bad} mismatches")

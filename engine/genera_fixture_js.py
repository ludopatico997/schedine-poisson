#!/usr/bin/env python3
"""Genera app/js/fixture_parita.json: valori calcolati dal Python che il porting JS (app/js/motore.js) deve riprodurre.
    python3 engine/genera_fixture_js.py
Va rilanciato solo se cambiano le formule in engine/ (poi: node --test app/js/*.test.js)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

from engine import puntate, riferimento as rif  # noqa: E402
from engine.dixon_coles import matrice_punteggi  # noqa: E402
from engine.mercati import tutti_i_mercati  # noqa: E402

MATRICI = [(1.4, 1.1, -0.07), (2.2, 0.6, -0.04), (0.9, 0.8, -0.1), (1.0, 1.0, 0.0), (3.1, 2.4, -0.02), (1.7, 1.2, 0.03)]
MERCATI = [  # (q1, qx, q2, q_over25, q_under25)
    (2.10, 3.40, 3.60, 1.95, 1.90), (1.35, 5.20, 9.50, 1.60, 2.40), (3.80, 3.30, 2.05, 2.05, 1.80),
    (2.60, 3.10, 2.90, None, None), (1.15, 8.00, 19.0, 1.35, 3.10), (4.50, 3.60, 1.85, 1.75, 2.15),
]
MODELLI = [(1.5, 1.2, -0.05), (2.4, 0.7, -0.03), (1.0, 1.4, -0.08), (1.3, 1.0, -0.05), (0.8, 2.0, -0.05), (1.6, 1.3, -0.04)]


def pulisci(d):
    return json.loads(json.dumps(d, default=float))


def main() -> None:
    out = {"matrici": [], "ancoraggi": [], "riferimenti": [], "schede": [], "selezione": []}
    for lam, mu, rho in MATRICI:
        out["matrici"].append({"lam": lam, "mu": mu, "rho": rho, "mercati": tutti_i_mercati(matrice_punteggi(lam, mu, rho))})
    for q in MERCATI:
        p = rif.probabilita_mercato(*q)
        lam, mu, res = rif.lam_mu_da_mercato(p, -0.05)
        out["ancoraggi"].append({"quote": q, "p": p, "rho": -0.05, "lam": lam, "mu": mu, "residuo": res})
    for q, (lm, mm, rho) in zip(MERCATI, MODELLI):
        p = rif.probabilita_mercato(*q)
        for peso in (0.0, 0.1, 0.5, 1.0):
            r = rif.riferimento(lm, mm, rho, p, peso)
            out["riferimenti"].append({"lam_mod": lm, "mu_mod": mm, "rho": rho, "mercato": p, "peso": peso,
                                       "lam": r["lam"], "mu": r["mu"], "disaccordo": r["disaccordo"], "probabilita": r["probabilita"]})
    # senza mercato
    r = rif.riferimento(1.5, 1.2, -0.05, None, 0.1)
    out["riferimenti"].append({"lam_mod": 1.5, "mu_mod": 1.2, "rho": -0.05, "mercato": None, "peso": 0.1, "lam": r["lam"], "mu": r["mu"],
                               "disaccordo": None, "probabilita": r["probabilita"]})
    # schede e selezione di giocate
    quote_bm = {"1": 2.30, "X": 3.20, "2": 3.9, "1X": 1.40, "Over 2.5": 2.0, "Under 2.5": 1.85, "GG": 1.75, "Multigol 2-4": 1.62}
    schede_per_partita = []
    for i, (q, (lm, mm, rho)) in enumerate(zip(MERCATI, MODELLI)):
        p = rif.probabilita_mercato(*q)
        r = rif.riferimento(lm, mm, rho, p, 0.1)
        sc = rif.scheda(r, quote_bm)
        out["schede"].append({"lam_mod": lm, "mu_mod": mm, "rho": rho, "mercato": p, "peso": 0.1, "quote": quote_bm,
                              "righe": [{k: v for k, v in s.items() if k != "motivo"} | {"motivo": s["motivo"]} for s in sc]})
        for s in sc:
            schede_per_partita.append({**s, "partita": f"P{i}", "etichetta": f"P{i}: {s['mercato']}"})
    casi = [
        {"valore_unita": 1.0, "bankroll": None, "perdita_settimana": 0.0, "tetto": 3},
        {"valore_unita": 1.0, "bankroll": 2.0, "perdita_settimana": 0.0, "tetto": 3},
        {"valore_unita": 1.0, "bankroll": 30.0, "perdita_settimana": 10.0, "tetto": 3},
        {"valore_unita": 2.0, "bankroll": 5.0, "perdita_settimana": 3.0, "tetto": 1},
    ]
    for c in casi:
        s = puntate.seleziona_giocate([dict(x) for x in schede_per_partita], c["valore_unita"], c["bankroll"], c["perdita_settimana"], c["tetto"])
        out["selezione"].append({"opzioni": c, "candidati": schede_per_partita, "stato": s["stato"],
                                 "singole": [{"etichetta": x["etichetta"], "unita": x["unita"], "importo": x["importo"]} for x in s["singole"]],
                                 "multipla": None if not s["multipla"] else {"eventi": s["multipla"]["eventi"], "quota_totale": s["multipla"]["quota_totale"],
                                                                              "prob_totale": s["multipla"]["prob_totale"], "unita": s["multipla"]["unita"]},
                                 "unita_totali": s["unita_totali"]})
    # perdita ultimi giorni
    from datetime import date
    storico = [{"data": date(2026, 11, d), "profitto_unita": v} for d, v in [(1, -2.0), (2, 1.5), (3, -4.0), (4, -3.5), (10, -1.0)]]
    out["perdita"] = {"storico": [{"data": s["data"].isoformat(), "profitto_unita": s["profitto_unita"]} for s in storico],
                      "oggi": "2026-11-04", "valore": puntate.perdita_ultimi_giorni(storico, date(2026, 11, 4)),
                      "valore_3gg": puntate.perdita_ultimi_giorni(storico, date(2026, 11, 4), 3)}
    destinazione = RADICE / "app" / "js" / "fixture_parita.json"
    destinazione.write_text(json.dumps(pulisci(out), indent=0, separators=(",", ":")), encoding="utf-8")
    print(f"Scritto {destinazione} ({destinazione.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

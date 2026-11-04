#!/usr/bin/env python3
"""Passo 4 - Verifica dei mercati derivati sui RISULTATI REALI (nessuna quota di bookmaker necessaria).

Per ogni mercato (Doppia Chance, GG/NG, linee Under/Over, Multigol) confronta la log-loss di:
  - base      frequenze storiche del campionato (prima del periodo di test);
  - puro      Dixon-Coles da solo;
  - mercato   gol attesi ricavati dalle quote Pinnacle di chiusura (peso modello 0%);
  - misto     mercato + 10% modello (impostazione proposta per l'app).
Usa le previsioni gia' prodotte da `walk_forward.py valuta` (data/pulito/previsioni_<etichetta>.csv).
Analizza anche il disaccordo modello-mercato, per fissare la soglia del semaforo giallo.

    python3 backtest/verifica_mercati.py --etichetta holdout
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RADICE = Path(__file__).resolve().parents[1]
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

from backtest.walk_forward import carica, logloss_1x2, logloss_bin  # noqa: E402
from engine.mercati import esiti_reali  # noqa: E402
from engine.riferimento import probabilita_mercato, riferimento  # noqa: E402


def calcola(pred: pd.DataFrame, partite: pd.DataFrame, peso_misto: float = 0.10):
    inizio = pred["data"].min()
    passato = partite[partite["data"] < inizio]
    base_lega = {}
    for lega, g in passato.groupby("campionato"):
        e = pd.DataFrame([esiti_reali(a, b) for a, b in zip(g["gol_casa"], g["gol_ospite"])])
        base_lega[lega] = e.mean()

    righe = {"reale": [], "base": [], "puro": [], "mercato": [], "misto": []}
    extra = []
    for r in pred.itertuples(index=False):
        ou = r.fonte_ou_ch == "pinnacle"
        mer = probabilita_mercato(r.q1_ch, r.qx_ch, r.q2_ch, r.over25_ch if ou else None, r.under25_ch if ou else None)
        a = riferimento(r.lam, r.mu, r.rho, mer, peso_modello=0.0)
        b = riferimento(r.lam, r.mu, r.rho, mer, peso_modello=peso_misto)
        righe["reale"].append(esiti_reali(r.gol_casa, r.gol_ospite))
        righe["base"].append(base_lega[r.campionato].to_dict())
        righe["puro"].append(a["prob_modello"])
        righe["mercato"].append(a["probabilita"])
        righe["misto"].append(b["probabilita"])
        extra.append({"disaccordo": a["disaccordo"], "residuo": a["residuo_ancoraggio"],
                      "k": {"H": 0, "D": 1, "A": 2}[r.esito],
                      "pm": [r.p1, r.px, r.p2], "mk": [mer["1"], mer["X"], mer["2"]]})
    return {k: pd.DataFrame(v) for k, v in righe.items()}, pd.DataFrame(extra)


def tabella_mercati(d: dict[str, pd.DataFrame]) -> pd.DataFrame:
    o = d["reale"].to_numpy(float)
    out = {}
    for nome in ("base", "puro", "mercato", "misto"):
        out[nome] = logloss_bin(d[nome][d["reale"].columns].to_numpy(float), o).mean(axis=0)
    t = pd.DataFrame(out, index=d["reale"].columns)
    t.insert(0, "freq_reale", d["reale"].mean())
    t["migliore"] = t[["puro", "mercato", "misto"]].idxmin(axis=1)
    return t


def analisi_disaccordo(extra: pd.DataFrame) -> pd.DataFrame:
    k = extra["k"].to_numpy()
    pm = np.array(extra["pm"].tolist())
    mk = np.array(extra["mk"].tolist())
    l_mod, l_mer = logloss_1x2(pm, k), logloss_1x2(mk, k)
    righe = []
    for soglia in (0.0, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20):
        m = extra["disaccordo"].to_numpy() > soglia
        if m.sum() < 30:
            continue
        diff = l_mod[m] - l_mer[m]
        righe.append({"disaccordo_>": soglia, "partite": int(m.sum()), "quota_%": 100 * m.mean(),
                      "logloss_modello": l_mod[m].mean(), "logloss_mercato": l_mer[m].mean(),
                      "modello-mercato": diff.mean(), "ic95": 1.96 * diff.std(ddof=1) / np.sqrt(m.sum())})
    return pd.DataFrame(righe)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Verifica dei mercati derivati sui risultati reali")
    p.add_argument("--etichetta", default="holdout")
    p.add_argument("--peso-misto", type=float, default=0.10)
    p.add_argument("--file", type=Path, default=RADICE / "data" / "pulito" / "partite.csv")
    args = p.parse_args(argv)

    partite = carica(args.file)
    pred = pd.read_csv(RADICE / "data" / "pulito" / f"previsioni_{args.etichetta}.csv", parse_dates=["data"])
    for c in ("fonte_1x2_ch", "fonte_ou_ch"):
        pred[c] = pred[c].fillna("")
    d, extra = calcola(pred, partite, args.peso_misto)

    fmt = lambda df: df.to_string(float_format=lambda v: f"{v:.4f}")  # noqa: E731
    t = tabella_mercati(d)
    testo = [f"# Verifica mercati derivati - {args.etichetta}", "",
             f"Partite: {len(pred)}  |  periodo {pred['data'].min().date()} -> {pred['data'].max().date()}",
             f"Errore massimo dell'ancoraggio alle quote (probabilita'): medio {extra['residuo'].mean():.4f}, "
             f"massimo {extra['residuo'].max():.4f}", "",
             "## Log-loss per mercato (piu' basso = meglio)", "", "```", fmt(t), "```", "",
             "'base' = frequenze storiche; 'puro' = solo Dixon-Coles; 'mercato' = gol attesi dalle quote;",
             f"'misto' = mercato + {args.peso_misto:.0%} modello.", "",
             "## Disaccordo modello-mercato (max differenza di probabilita' su 1, X, 2)", "",
             "Log-loss 1X2 sulle sole partite con disaccordo oltre la soglia:", "", "```",
             analisi_disaccordo(extra).to_string(index=False, float_format=lambda v: f"{v:.4f}"), "```", ""]
    out = "\n".join(testo)
    (RADICE / "backtest" / "risultati" / "rapporto_mercati.md").write_text(out, encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

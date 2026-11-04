#!/usr/bin/env python3
"""Passo 5 - Confronto tra Dixon-Coles, Elo ed ensemble con lo stesso backtest walk-forward.

Regola del progetto: la scelta si fa sui numeri e ogni modello piu' complesso deve battere il piu' semplice.
  1. tarare-elo   prova una griglia (K, vantaggio casa, regressione di stagione) sul periodo di taratura;
  2. tarare-ens   sceglie il peso dell'Elo nell'ensemble (Dixon-Coles gia' tarato al passo 3);
  3. holdout      sceglie il modello finale con la log-loss del periodo di TARATURA e lo conferma una sola volta
                  sull'holdout (mai usato per tarare); scrive rapporto_modelli.md e modello_finale.json.

    python3 backtest/confronta_modelli.py tarare-elo
    python3 backtest/confronta_modelli.py tarare-ens
    python3 backtest/confronta_modelli.py holdout
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

RADICE = Path(__file__).resolve().parents[1]
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

from backtest import walk_forward as wf  # noqa: E402

RIS = RADICE / "backtest" / "risultati"
DC_PARAMETRI = {"emivita_giorni": 270.0, "ridge": 3.0}   # tarati al passo 3


def _punteggio(pred: pd.DataFrame) -> dict:
    m = wf.metriche(pred)
    return {"ll_1x2": m["1x2_logloss"]["modello"], "ll_ou": m["ou_logloss"]["modello"],
            "mercato_1x2": m["1x2_logloss"]["mercato"], "mercato_ou": m["ou_logloss"]["mercato"]}


def cmd_tarare_elo(a) -> int:
    P = wf.carica(a.file)
    righe = []
    for k, h, reg in itertools.product(a.k, a.vantaggio, a.regressione):
        t0 = time.time()
        par = {"k": k, "vantaggio_casa": h, "regressione": reg}
        s = _punteggio(wf.previsioni(P, a.da, a.fino, modello="elo", parametri=par))
        righe.append({**par, **s})
        print(f"K={k:>3} H={h:>3} reg={reg:<5} 1X2={s['ll_1x2']:.4f} O/U={s['ll_ou']:.4f} ({time.time() - t0:.1f}s)", flush=True)
    t = pd.DataFrame(righe).sort_values("ll_1x2")
    t.to_csv(RIS / "tarature_elo.csv", index=False)
    mig = t.iloc[0]
    (RIS / "elo_migliore.json").write_text(json.dumps(
        {"k": float(mig["k"]), "vantaggio_casa": float(mig["vantaggio_casa"]), "regressione": float(mig["regressione"])}))
    print("\nMigliori 8 per log-loss 1X2 (mercato nello stesso periodo: "
          f"1X2={mig['mercato_1x2']:.4f}, O/U={mig['mercato_ou']:.4f}):")
    print(t.head(8).to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print("\nControllare che il migliore non sia ai bordi della griglia.")
    return 0


def _par_ens(elo: dict, peso: float) -> dict:
    return {**elo, "peso_elo": peso, "dc": DC_PARAMETRI}


def cmd_tarare_ens(a) -> int:
    P = wf.carica(a.file)
    elo = json.loads((RIS / "elo_migliore.json").read_text())
    righe = []
    for w in a.pesi:
        s = _punteggio(wf.previsioni(P, a.da, a.fino, modello="ens", parametri=_par_ens(elo, w)))
        righe.append({"peso_elo": w, **s})
        print(f"peso Elo={w:.2f}  1X2={s['ll_1x2']:.4f}  O/U={s['ll_ou']:.4f}", flush=True)
    t = pd.DataFrame(righe)
    # riferimenti: DC solo e Elo solo nello stesso periodo
    dc = _punteggio(wf.previsioni(P, a.da, a.fino, modello="dc", parametri=DC_PARAMETRI))
    el = _punteggio(wf.previsioni(P, a.da, a.fino, modello="elo", parametri=elo))
    rif = pd.DataFrame([{"modello": "dc", **dc}, {"modello": "elo", **el}] +
                       [{"modello": f"ens w={r.peso_elo:.2f}", "ll_1x2": r.ll_1x2, "ll_ou": r.ll_ou,
                         "mercato_1x2": r.mercato_1x2, "mercato_ou": r.mercato_ou} for r in t.itertuples()])
    rif.to_csv(RIS / "tarature_modelli.csv", index=False)
    print("\nPeriodo di taratura, log-loss (mercato 1X2=%.4f, O/U=%.4f):" % (dc["mercato_1x2"], dc["mercato_ou"]))
    print(rif[["modello", "ll_1x2", "ll_ou"]].to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    ens_mig = t.sort_values("ll_1x2").iloc[0]
    candidati = {"dc": (dc["ll_1x2"], DC_PARAMETRI), "elo": (el["ll_1x2"], elo),
                 "ens": (ens_mig["ll_1x2"], _par_ens(elo, float(ens_mig["peso_elo"])))}
    scelto = min(candidati, key=lambda n: candidati[n][0])
    (RIS / "modello_finale.json").write_text(json.dumps(
        {"modello": scelto, "parametri": candidati[scelto][1], "scelto_su": f"{a.da} -> {a.fino}",
         "ll_1x2_taratura": candidati[scelto][0]}, indent=2))
    print(f"\nScelto sul periodo di taratura: {scelto}  (log-loss 1X2 {candidati[scelto][0]:.4f})")
    return 0


def cmd_holdout(a) -> int:
    P = wf.carica(a.file)
    fin = json.loads((RIS / "modello_finale.json").read_text())
    elo = json.loads((RIS / "elo_migliore.json").read_text())
    ens_par = fin["parametri"] if fin["modello"] == "ens" else _par_ens(elo, 0.5)
    cand = {"dc": ("dc", DC_PARAMETRI), "elo": ("elo", elo), "ens": ("ens", ens_par)}
    preds = {n: wf.previsioni(P, a.da, a.fino, modello=m, parametri=p) for n, (m, p) in cand.items()}
    ids = ["data", "campionato", "casa", "ospite"]
    for n in ("elo", "ens"):
        assert preds[n][ids].equals(preds["dc"][ids]), "le partite valutate devono coincidere"

    righe, ll1 = [], {}
    d1 = {}
    for n, pr in preds.items():
        a1, a2 = wf._insiemi(pr)
        d1[n] = (a1, a2)
        ll1[n] = wf.logloss_1x2(a1["mod"], a1["k"])
    mk1, mk2 = d1["dc"][0], d1["dc"][1]
    mkt_ll = wf.logloss_1x2(mk1["mer"], mk1["k"])
    nai_ll = wf.logloss_1x2(mk1["nai"], mk1["k"])

    testo = [f"# Confronto modelli - holdout {a.da} -> {a.fino}", "",
             f"Modello scelto sul periodo di taratura: **{fin['modello']}** ({fin['scelto_su']})",
             f"Parametri candidati: dc={DC_PARAMETRI}, elo={elo}, ens={ens_par}", "",
             f"Partite 1X2: {len(mkt_ll)}", "",
             "## Log-loss (piu' basso = meglio)", ""]
    tab = []
    for n in ("dc", "elo", "ens"):
        m = wf.metriche(preds[n])
        diff_dc = ll1[n] - ll1["dc"]
        diff_mk = ll1[n] - mkt_ll
        tab.append({"modello": n, "1X2": m["1x2_logloss"]["modello"], "O/U": m["ou_logloss"]["modello"],
                    "1X2 - dc": diff_dc.mean(), "ic95 vs dc": 1.96 * diff_dc.std(ddof=1) / np.sqrt(len(diff_dc)) if n != "dc" else 0.0,
                    "1X2 - mercato": diff_mk.mean(), "ic95 vs mercato": 1.96 * diff_mk.std(ddof=1) / np.sqrt(len(diff_mk))})
    tab.append({"modello": "mercato", "1X2": mkt_ll.mean(), "O/U": wf.metriche(preds["dc"])["ou_logloss"]["mercato"]})
    tab.append({"modello": "base", "1X2": nai_ll.mean(), "O/U": wf.metriche(preds["dc"])["ou_logloss"]["base"]})
    testo += ["```", pd.DataFrame(tab).to_string(index=False, float_format=lambda v: f"{v:.4f}"), "```", "",
              "## Il modello aggiunge informazione al mercato? (peso scelto sull'holdout stesso: ottimistico)", ""]
    pesi = (0, 0.05, 0.1, 0.2, 0.3, 0.5)
    rows = []
    for n in ("dc", "elo", "ens"):
        a1, a2 = d1[n]
        for w in pesi:
            rows.append({"modello": n, "peso_modello": w,
                         "1X2": wf.logloss_1x2((1 - w) * a1["mer"] + w * a1["mod"], a1["k"]).mean(),
                         "O/U": wf.logloss_bin((1 - w) * a2["mer"] + w * a2["mod"], a2["o"]).mean()})
    r = pd.DataFrame(rows)
    testo += ["```", r.pivot(index="peso_modello", columns="modello", values="1X2").to_string(float_format=lambda v: f"{v:.4f}"),
              "```", "(log-loss 1X2 della miscela mercato/modello)", "", "```",
              r.pivot(index="peso_modello", columns="modello", values="O/U").to_string(float_format=lambda v: f"{v:.4f}"),
              "```", "(log-loss Under/Over 2.5 della miscela)", ""]
    for n in ("dc", "elo", "ens"):
        testo += [f"## {n}: log-loss per campionato", "", "```", wf._fmt(wf.per_gruppo(preds[n], "campionato")), "```", ""]
    out = "\n".join(testo)
    (RIS / "rapporto_modelli.md").write_text(out, encoding="utf-8")
    for n, pr in preds.items():
        pr.to_csv(RADICE / "data" / "pulito" / f"previsioni_holdout_{n}.csv", index=False)
    print(out)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Confronto Dixon-Coles / Elo / ensemble")
    sub = p.add_subparsers(dest="cmd", required=True)
    com = argparse.ArgumentParser(add_help=False)
    com.add_argument("--file", type=Path, default=RADICE / "data" / "pulito" / "partite.csv")
    t = sub.add_parser("tarare-elo", parents=[com])
    t.add_argument("--da", default="2021-08-01"), t.add_argument("--fino", default="2024-07-31")
    t.add_argument("--k", type=float, nargs="+", default=[10, 20, 30, 40])
    t.add_argument("--vantaggio", type=float, nargs="+", default=[40, 70, 100])
    t.add_argument("--regressione", type=float, nargs="+", default=[0.05, 0.2, 0.35])
    t.set_defaults(f=cmd_tarare_elo)
    e = sub.add_parser("tarare-ens", parents=[com])
    e.add_argument("--da", default="2021-08-01"), e.add_argument("--fino", default="2024-07-31")
    e.add_argument("--pesi", type=float, nargs="+", default=[0.2, 0.35, 0.5, 0.65, 0.8])
    e.set_defaults(f=cmd_tarare_ens)
    h = sub.add_parser("holdout", parents=[com])
    h.add_argument("--da", default="2024-08-01"), h.add_argument("--fino", default="2026-12-31")
    h.set_defaults(f=cmd_holdout)
    args = p.parse_args(argv)
    return args.f(args)


if __name__ == "__main__":
    raise SystemExit(main())

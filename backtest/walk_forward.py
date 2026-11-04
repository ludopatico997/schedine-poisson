#!/usr/bin/env python3
"""Passo 3 - Backtest walk-forward di 1X2 e Under/Over 2.5 contro le quote di chiusura Pinnacle.

Come funziona (nessun look-ahead)
  Si divide il periodo di test in blocchi (default 30 giorni). Per ogni blocco e ogni campionato il
  modello viene stimato SOLO con le partite precedenti all'inizio del blocco e poi usato per prevedere
  le partite del blocco. Le partite del blocco non aggiornano il modello fino al blocco successivo.

Si confrontano tre previsori sulle stesse partite:
  - modello Dixon-Coles;
  - mercato: quote di chiusura Pinnacle con il margine tolto in modo proporzionale;
  - base: frequenze storiche del campionato (come "non so nulla").
Si usano solo le partite per cui la quota di chiusura e' davvero Pinnacle (colonna fonte_*_ch):
la media di mercato ha un margine diverso e falserebbe il confronto.

Sottocomandi:
  tarare  prova una griglia di (emivita, ridge) sul periodo di taratura e indica la migliore;
  valuta  valuta un'impostazione fissa su un periodo (di solito l'holdout, mai usato per tarare)
          e scrive un rapporto in backtest/risultati/.

Esempi:
    python3 backtest/walk_forward.py tarare
    python3 backtest/walk_forward.py valuta --emivita 365 --ridge 1 --da 2024-08-01 --etichetta holdout
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

RADICE = Path(__file__).resolve().parents[1]
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

from engine.dixon_coles import PORTE_CHIUSE_AL, PORTE_CHIUSE_DAL  # noqa: E402
from engine.modelli import crea_modello  # noqa: E402
from engine.mercati import toglie_margine  # noqa: E402

CLASSI = {"H": 0, "D": 1, "A": 2}
COLONNE_QUOTE = ["q1_ch", "qx_ch", "q2_ch", "over25_ch", "under25_ch",
                 "q1_ap", "qx_ap", "q2_ap", "over25_ap", "under25_ap",
                 "fonte_1x2_ch", "fonte_ou_ch", "fonte_1x2_ap", "fonte_ou_ap"]
SOGLIE = [-1.0, 0.0, 0.02, 0.05, 0.08, 0.10]  # -1 = punta sempre sull'esito col maggior edge


# ----------------------------------------------------------------------------- previsioni
def _job_lega(args) -> list[dict]:
    """Walk-forward su un campionato. Funzione a livello di modulo per poter girare in un altro processo."""
    df_l, da, fino, nome_modello, parametri, blocco = args
    test = df_l[(df_l["data"] >= da) & (df_l["data"] <= fino) & (df_l["fonte_1x2_ch"] == "pinnacle")]
    righe, inizio = [], da
    while inizio <= fino:
        fine = inizio + pd.Timedelta(days=blocco)  # escluso
        b = test[(test["data"] >= inizio) & (test["data"] < fine)]
        if len(b):
            modello = crea_modello(nome_modello, parametri).fit(df_l, inizio)  # solo dati < inizio
            passato = df_l[df_l["data"] < inizio]
            freq = [(passato["esito"] == e).mean() for e in "HDA"]
            f_over = ((passato["gol_casa"] + passato["gol_ospite"]) >= 3).mean()
            for r in b.itertuples(index=False):
                chiuse = PORTE_CHIUSE_DAL <= r.data <= PORTE_CHIUSE_AL
                p = modello.probabilita(r.casa, r.ospite, porte_chiuse=chiuse)
                riga = {
                    "campionato": r.campionato, "stagione": r.stagione, "data": r.data,
                    "casa": r.casa, "ospite": r.ospite, "gol_casa": r.gol_casa,
                    "gol_ospite": r.gol_ospite, "esito": r.esito,
                    "p1": p["p1"], "px": p["px"], "p2": p["p2"], "over25": p["over25"],
                    "squadre_note": p["squadre_note"], "lam": p["gol_attesi_casa"],
                    "mu": p["gol_attesi_ospite"], "rho": p["rho"],
                    "f1": freq[0], "fx": freq[1], "f2": freq[2], "f_over": f_over,
                }
                for c in COLONNE_QUOTE:
                    riga[c] = getattr(r, c)
                righe.append(riga)
        inizio = fine
    return righe


def previsioni(partite: pd.DataFrame, da, fino, emivita=365.0, ridge=1.0, blocco_giorni=30,
               processi: int = 1, modello: str = "dc", parametri: dict | None = None) -> pd.DataFrame:
    """Previsioni walk-forward per tutte le partite Pinnacle tra `da` e `fino` (estremi inclusi).

    Per il Dixon-Coles bastano emivita e ridge; per 'elo' e 'ens' si passano i `parametri` del modello."""
    da, fino = pd.Timestamp(da), pd.Timestamp(fino)
    if modello == "dc" and parametri is None:
        parametri = {"emivita_giorni": emivita, "ridge": ridge}
    lavori = [(g.reset_index(drop=True), da, fino, modello, parametri or {}, blocco_giorni)
              for _, g in partite.groupby("campionato")]
    if processi > 1 and len(lavori) > 1:
        with ProcessPoolExecutor(max_workers=min(processi, len(lavori))) as ex:
            risultati = list(ex.map(_job_lega, lavori))
    else:
        risultati = [_job_lega(j) for j in lavori]
    pred = pd.DataFrame([r for lista in risultati for r in lista])
    if pred.empty:
        raise ValueError("nessuna partita di test: controllare le date e la presenza di quote Pinnacle")
    return pred.sort_values(["data", "campionato", "casa"]).reset_index(drop=True)


# ----------------------------------------------------------------------------- metriche
def logloss_1x2(p: np.ndarray, k: np.ndarray) -> np.ndarray:
    return -np.log(np.clip(p[np.arange(len(k)), k], 1e-12, 1.0))


def brier_1x2(p: np.ndarray, k: np.ndarray) -> np.ndarray:
    return ((p - np.eye(3)[k]) ** 2).sum(axis=1)


def logloss_bin(p: np.ndarray, o: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return -(o * np.log(p) + (1 - o) * np.log(1 - p))


def brier_bin(p: np.ndarray, o: np.ndarray) -> np.ndarray:
    return (p - o) ** 2


def _insiemi(pred: pd.DataFrame):
    """Estrae gli array per 1X2 e Under/Over (solo righe con quote di chiusura Pinnacle)."""
    a = pred[pred["fonte_1x2_ch"] == "pinnacle"]
    k = a["esito"].map(CLASSI).to_numpy()
    d1 = {
        "k": k,
        "mod": a[["p1", "px", "p2"]].to_numpy(float),
        "mer": toglie_margine(a[["q1_ch", "qx_ch", "q2_ch"]].to_numpy(float)),
        "nai": a[["f1", "fx", "f2"]].to_numpy(float),
        "idx": a.index,
    }
    b = pred[pred["fonte_ou_ch"] == "pinnacle"]
    o = ((b["gol_casa"] + b["gol_ospite"]) >= 3).to_numpy(float)
    mer_ou = toglie_margine(b[["over25_ch", "under25_ch"]].to_numpy(float))[:, 0]
    d2 = {"o": o, "mod": b["over25"].to_numpy(float), "mer": mer_ou, "nai": b["f_over"].to_numpy(float),
          "idx": b.index}
    return d1, d2


def _confronto(l_mod: np.ndarray, l_mer: np.ndarray, l_nai: np.ndarray) -> dict:
    diff = l_mod - l_mer
    se = diff.std(ddof=1) / np.sqrt(len(diff)) if len(diff) > 1 else float("nan")
    return {"n": len(l_mod), "modello": l_mod.mean(), "mercato": l_mer.mean(), "base": l_nai.mean(),
            "modello-mercato": diff.mean(), "ic95": 1.96 * se}


def metriche(pred: pd.DataFrame) -> dict:
    """Log-loss e Brier di modello, mercato e base, per 1X2 e Under/Over, con intervallo sulla differenza."""
    d1, d2 = _insiemi(pred)
    out = {"1x2_logloss": _confronto(logloss_1x2(d1["mod"], d1["k"]), logloss_1x2(d1["mer"], d1["k"]),
                                      logloss_1x2(d1["nai"], d1["k"])),
           "1x2_brier": _confronto(brier_1x2(d1["mod"], d1["k"]), brier_1x2(d1["mer"], d1["k"]),
                                    brier_1x2(d1["nai"], d1["k"]))}
    if len(d2["o"]):
        out["ou_logloss"] = _confronto(logloss_bin(d2["mod"], d2["o"]), logloss_bin(d2["mer"], d2["o"]),
                                        logloss_bin(d2["nai"], d2["o"]))
        out["ou_brier"] = _confronto(brier_bin(d2["mod"], d2["o"]), brier_bin(d2["mer"], d2["o"]),
                                      brier_bin(d2["nai"], d2["o"]))
    return out


def per_gruppo(pred: pd.DataFrame, colonna: str) -> pd.DataFrame:
    """Log-loss 1X2 e Over/Under di modello e mercato per campionato, stagione o altro."""
    righe = []
    for chiave, g in pred.groupby(colonna):
        m = metriche(g)
        riga = {colonna: chiave, "n": m["1x2_logloss"]["n"],
                "1X2 modello": m["1x2_logloss"]["modello"], "1X2 mercato": m["1x2_logloss"]["mercato"]}
        if "ou_logloss" in m:
            riga.update({"O/U modello": m["ou_logloss"]["modello"], "O/U mercato": m["ou_logloss"]["mercato"],
                         "O/U base": m["ou_logloss"]["base"]})
        righe.append(riga)
    return pd.DataFrame(righe)


def calibrazione(pred: pd.DataFrame, intervalli: int = 8) -> pd.DataFrame:
    """Affidabilita' 1X2: tutte le probabilita' previste (casa, X, trasferta) raggruppate in classi."""
    d1, _ = _insiemi(pred)
    p = d1["mod"].ravel()
    visto = np.eye(3)[d1["k"]].ravel()
    mer = d1["mer"].ravel()
    bordi = np.quantile(p, np.linspace(0, 1, intervalli + 1))
    bordi[0], bordi[-1] = 0.0, 1.0
    classe = np.clip(np.searchsorted(bordi, p, side="right") - 1, 0, intervalli - 1)
    t = pd.DataFrame({"classe": classe, "prevista": p, "mercato": mer, "osservata": visto})
    r = t.groupby("classe").agg(n=("prevista", "size"), prevista=("prevista", "mean"),
                                mercato=("mercato", "mean"), osservata=("osservata", "mean"))
    r["errore_modello"] = r["prevista"] - r["osservata"]
    r["errore_mercato"] = r["mercato"] - r["osservata"]
    return r.reset_index(drop=True)


# ----------------------------------------------------------------------------- ROI simulato
def scommesse(P: np.ndarray, Q: np.ndarray, esito: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per ogni partita sceglie l'esito col maggior edge (p * quota - 1). Ritorna (edge, profitto per 1 unita')."""
    edge = P * Q - 1.0
    scelto = edge.argmax(axis=1)
    riga = np.arange(len(P))
    profitto = np.where(esito == scelto, Q[riga, scelto] - 1.0, -1.0)
    return edge[riga, scelto], profitto


def tabella_roi(edge: np.ndarray, profitto: np.ndarray, soglie=SOGLIE) -> pd.DataFrame:
    righe = []
    for s in soglie:
        m = edge > s
        n = int(m.sum())
        if n == 0:
            righe.append({"soglia_edge": s, "scommesse": 0})
            continue
        pr = profitto[m]
        se = pr.std(ddof=1) / np.sqrt(n) if n > 1 else float("nan")
        righe.append({"soglia_edge": s, "scommesse": n, "vinte_%": 100 * (pr > 0).mean(),
                      "profitto_unita": pr.sum(), "ROI_%": 100 * pr.mean(), "ic95_%": 100 * 1.96 * se})
    return pd.DataFrame(righe)


def roi(pred: pd.DataFrame, mercato: str, momento: str) -> pd.DataFrame:
    """mercato: '1x2' | 'ou'; momento: 'ch' (quote di chiusura) | 'ap' (apertura). Solo quote Pinnacle."""
    if mercato == "1x2":
        a = pred[pred[f"fonte_1x2_{momento}"] == "pinnacle"]
        P = a[["p1", "px", "p2"]].to_numpy(float)
        Q = a[[f"q1_{momento}", f"qx_{momento}", f"q2_{momento}"]].to_numpy(float)
        esito = a["esito"].map(CLASSI).to_numpy()
    else:
        a = pred[pred[f"fonte_ou_{momento}"] == "pinnacle"]
        P = np.column_stack([a["over25"], 1 - a["over25"]]).astype(float)
        Q = a[[f"over25_{momento}", f"under25_{momento}"]].to_numpy(float)
        esito = np.where((a["gol_casa"] + a["gol_ospite"]).to_numpy() >= 3, 0, 1)
    if len(a) == 0:
        return pd.DataFrame()
    return tabella_roi(*scommesse(P, Q, esito))


# ----------------------------------------------------------------------------- rapporto
def _fmt(df: pd.DataFrame) -> str:
    return df.to_string(index=False, float_format=lambda v: f"{v:.4f}" if abs(v) < 10 else f"{v:.1f}")


def rapporto(pred: pd.DataFrame, titolo: str, parametri: dict) -> str:
    m = metriche(pred)
    righe = [f"# Backtest walk-forward - {titolo}", "",
             f"Parametri: {parametri}",
             f"Periodo: {pred['data'].min().date()} -> {pred['data'].max().date()}  |  partite 1X2: {m['1x2_logloss']['n']}"
             f"  |  partite Under/Over: {m['ou_logloss']['n'] if 'ou_logloss' in m else 0}",
             f"Partite con squadre sconosciute al modello (neopromosse senza storico): "
             f"{100 * (~pred['squadre_note']).mean():.1f}%", "",
             "## Qualita' delle probabilita' (piu' basso = meglio)", ""]
    tab = pd.DataFrame(m).T
    righe += ["```", _fmt(tab.reset_index().rename(columns={"index": "metrica"})), "```", "",
              "'modello-mercato' < 0 significa modello migliore del mercato; 'ic95' e' la meta' larghezza dell'intervallo al 95%.",
              "Se l'intervallo include lo zero, la differenza non e' distinguibile dal caso.", ""]
    for col, nome in (("campionato", "per campionato"), ("stagione", "per stagione")):
        righe += [f"## Log-loss {nome}", "", "```", _fmt(per_gruppo(pred, col)), "```", ""]
    nota = pred.assign(note=np.where(pred["squadre_note"], "squadre note", "squadra sconosciuta"))
    righe += ["## Log-loss secondo la conoscenza delle squadre", "", "```", _fmt(per_gruppo(nota, "note")), "```", "",
              "## Calibrazione 1X2 (probabilita' prevista vs frequenza osservata)", "",
              "```", _fmt(calibrazione(pred)), "```", ""]
    righe += ["## ROI simulato (1 unita' per scommessa, sull'esito col maggior edge, a quote Pinnacle)", "",
              "ATTENZIONE: quote Pinnacle = ideale. Un bookmaker italiano ha margini piu' alti e limiti di puntata.",
              "Piu' soglie e piu' mercati provati = piu' probabilita' di trovare un risultato buono per puro caso.", ""]
    for mercato, nome in (("1x2", "1X2"), ("ou", "Under/Over 2.5")):
        for momento, nm in (("ch", "quote di chiusura"), ("ap", "quote di apertura")):
            t = roi(pred, mercato, momento)
            if len(t):
                righe += [f"### {nome} - {nm}", "", "```", _fmt(t), "```", ""]
    return "\n".join(righe)


# ----------------------------------------------------------------------------- comandi
def carica(file: Path) -> pd.DataFrame:
    df = pd.read_csv(file, parse_dates=["data"])
    for c in ("fonte_1x2_ch", "fonte_ou_ch", "fonte_1x2_ap", "fonte_ou_ap"):
        df[c] = df[c].fillna("")
    return df


def cmd_tarare(args) -> int:
    partite = carica(args.file)
    righe = []
    for emivita in args.emivita:
        for ridge in args.ridge:
            t0 = time.time()
            pred = previsioni(partite, args.da, args.fino, emivita, ridge, args.blocco, args.processi)
            m = metriche(pred)
            riga = {"emivita": emivita, "ridge": ridge, "n_1x2": m["1x2_logloss"]["n"],
                    "1X2_logloss": m["1x2_logloss"]["modello"], "1X2_vs_mercato": m["1x2_logloss"]["modello-mercato"],
                    "OU_logloss": m.get("ou_logloss", {}).get("modello", np.nan),
                    "OU_vs_mercato": m.get("ou_logloss", {}).get("modello-mercato", np.nan)}
            righe.append(riga)
            print(f"emivita={emivita:>5} ridge={ridge:>5}  1X2={riga['1X2_logloss']:.4f}  "
                  f"O/U={riga['OU_logloss']:.4f}  ({time.time() - t0:.1f}s)", flush=True)
    t = pd.DataFrame(righe)
    t.to_csv(RADICE / "backtest" / "risultati" / "tarature.csv", index=False)
    print(f"\nMercato di riferimento nello stesso periodo: 1X2={t['1X2_logloss'].iloc[0] - t['1X2_vs_mercato'].iloc[0]:.4f}"
          f"  O/U={t['OU_logloss'].iloc[0] - t['OU_vs_mercato'].iloc[0]:.4f}")
    print("\nOrdinate per log-loss 1X2 (criterio di scelta):")
    print(_fmt(t.sort_values("1X2_logloss")))
    migliore = t.sort_values("1X2_logloss").iloc[0]
    print(f"\nMigliore: emivita={migliore['emivita']:.0f}, ridge={migliore['ridge']}. "
          "Verificare che non sia ai bordi della griglia (in tal caso allargarla).")
    return 0


def cmd_valuta(args) -> int:
    partite = carica(args.file)
    pred = previsioni(partite, args.da, args.fino, args.emivita, args.ridge, args.blocco, args.processi)
    out_dir = RADICE / "backtest" / "risultati"
    pred.to_csv(RADICE / "data" / "pulito" / f"previsioni_{args.etichetta}.csv", index=False)  # non versionato
    testo = rapporto(pred, args.etichetta, {"emivita": args.emivita, "ridge": args.ridge, "blocco_giorni": args.blocco})
    (out_dir / f"rapporto_{args.etichetta}.md").write_text(testo, encoding="utf-8")
    print(testo)
    print(f"\nRapporto salvato in backtest/risultati/rapporto_{args.etichetta}.md")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Backtest walk-forward del Dixon-Coles")
    sub = p.add_subparsers(dest="cmd", required=True)
    comune = argparse.ArgumentParser(add_help=False)
    comune.add_argument("--file", type=Path, default=RADICE / "data" / "pulito" / "partite.csv")
    comune.add_argument("--blocco", type=int, default=30, help="giorni tra una ri-stima e l'altra")
    comune.add_argument("--processi", type=int, default=1, help="processi in parallelo (1 e' il piu' veloce: ogni stima dura pochi ms)")

    t = sub.add_parser("tarare", parents=[comune])
    t.add_argument("--da", default="2021-08-01")
    t.add_argument("--fino", default="2024-07-31")
    t.add_argument("--emivita", type=float, nargs="+", default=[120, 180, 270, 365, 540, 730])
    t.add_argument("--ridge", type=float, nargs="+", default=[0.1, 0.3, 1, 3, 10])
    t.set_defaults(f=cmd_tarare)

    v = sub.add_parser("valuta", parents=[comune])
    v.add_argument("--da", default="2024-08-01")
    v.add_argument("--fino", default="2026-12-31")
    v.add_argument("--emivita", type=float, default=365.0)
    v.add_argument("--ridge", type=float, default=1.0)
    v.add_argument("--etichetta", default="holdout")
    v.set_defaults(f=cmd_valuta)

    args = p.parse_args(argv)
    return args.f(args)


if __name__ == "__main__":
    raise SystemExit(main())

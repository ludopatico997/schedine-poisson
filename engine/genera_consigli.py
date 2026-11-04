#!/usr/bin/env python3
"""Passo 7 - Genera data/consigli.json: probabilita' di riferimento per le prossime partite.

Il file contiene SOLO probabilita' e quote minime di valore calcolate (nessuna copia dei CSV originali, nessuna
quota di bookmaker, nessun dato personale): e' pubblicabile su GitHub Pages. Le quote del bookmaker dell'utente,
il bankroll e lo storico restano nel browser. Il semaforo si calcola nell'app quando l'utente inserisce la quota.

Sorgenti delle quote di mercato:
  odds-api  The Odds API (variabile d'ambiente ODDS_API_KEY, nei Secrets di GitHub)
  file      JSON gia' normalizzato:  {"I1": [{"casa","ospite","inizio","mercato":{"1","X","2","Over 2.5","Under 2.5"},"fonte","n_bookmaker"}], ...}
  demo      ultime partite gia' giocate nei CSV con le quote medie di apertura (SOLO per provare la catena)

    python3 engine/genera_consigli.py --sorgente demo
    ODDS_API_KEY=... python3 engine/genera_consigli.py --sorgente odds-api
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

RADICE = Path(__file__).resolve().parents[1]
if str(RADICE) not in sys.path:
    sys.path.insert(0, str(RADICE))

from engine import fonte_quote, nomi, scarica_dati  # noqa: E402
from engine.mercati import quota_equa, quota_minima_valore, toglie_margine  # noqa: E402
from engine.modelli import crea_modello  # noqa: E402
from engine.puntate import (KELLY_FRAZIONE, MAX_EVENTI_MULTIPLA, PAUSA_PERDITA_SETTIMANA,  # noqa: E402
                            QUOTA_MAX_DUE_UNITA, TETTO_GIORNALIERO_UNITA, VALORE_ALTO)
from engine.riferimento import (MERCATI_DIRETTI, PESO_MODELLO, SOGLIA_DISACCORDO, SOGLIA_VALORE,  # noqa: E402
                                SOGLIA_VALORE_SENZA_MERCATO, riferimento)

NOMI_CAMPIONATI = {"I1": "Serie A", "I2": "Serie B", "E0": "Premier League", "SP1": "Liga", "F1": "Ligue 1", "D1": "Bundesliga"}
AVVISO_GIOCO = ("Il gioco d'azzardo puo' causare dipendenza. Vietato ai minori di 18 anni. Gioca solo denaro che puoi permetterti "
                "di perdere. Questi numeri sono stime: non garantiscono alcun profitto e il margine del bookmaker e' sempre un costo.")


def _arr(d: dict[str, float], nd: int = 5) -> dict[str, float]:
    return {k: round(float(v), nd) for k, v in d.items()}


def costruisci_consigli(partite: pd.DataFrame, eventi: dict[str, list[dict]], modello_spec: dict, data_rif,
                        peso_modello: float = PESO_MODELLO, demo: bool = False) -> dict:
    """Costruisce il dizionario di consigli.json. `eventi`: {codice_campionato: [evento normalizzato]}."""
    data_rif = pd.Timestamp(data_rif)
    avvisi, righe = [], []
    for cod, lista in eventi.items():
        df_l = partite[partite["campionato"] == cod]
        if df_l.empty or not lista:
            continue
        modello = crea_modello(modello_spec["modello"], modello_spec["parametri"]).fit(df_l, data_rif)
        recenti = df_l[df_l["data"] >= data_rif - pd.Timedelta(days=400)]
        squadre = sorted(set(recenti["casa"]) | set(recenti["ospite"]))
        for ev in lista:
            casa, ospite = nomi.abbina(ev["casa"], squadre), nomi.abbina(ev["ospite"], squadre)
            if casa is None or ospite is None:
                avvisi.append(f"{NOMI_CAMPIONATI.get(cod, cod)}: nome non riconosciuto in '{ev['casa']} - {ev['ospite']}': partita saltata")
                continue
            lam, mu, noti = modello.tassi(casa, ospite)
            rif = riferimento(lam, mu, modello.rho, ev.get("mercato"), peso_modello)
            ha_ou = bool(ev.get("mercato")) and "Over 2.5" in ev["mercato"]
            qeq, qmin = {}, {}
            for nome, p in rif["probabilita"].items():
                diretto = ev.get("mercato") is not None and nome in MERCATI_DIRETTI and (nome not in ("Over 2.5", "Under 2.5") or ha_ou)
                qeq[nome] = round(quota_equa(p), 3)
                qmin[nome] = round(quota_minima_valore(p, SOGLIA_VALORE if diretto else SOGLIA_VALORE_SENZA_MERCATO), 3)
            righe.append({
                "id": f"{cod}_{str(ev['inizio'])[:10]}_{casa}_{ospite}".replace(" ", "-"),
                "campionato": cod, "nome_campionato": NOMI_CAMPIONATI.get(cod, cod), "inizio": ev["inizio"],
                "casa": casa, "ospite": ospite,
                "modello": {"lam": round(lam, 4), "mu": round(mu, 4), "rho": round(float(modello.rho), 4), "squadre_note": bool(noti)},
                "mercato": None if not ev.get("mercato") else {"fonte": ev.get("fonte", "?"), "n_bookmaker": ev.get("n_bookmaker"),
                                                               "prob": _arr(ev["mercato"])},
                "riferimento": {"peso_modello": peso_modello, "fonte": rif["fonte"],
                                "disaccordo": None if rif["disaccordo"] is None else round(rif["disaccordo"], 4),
                                "probabilita": _arr(rif["probabilita"]), "quota_equa": qeq, "quota_minima": qmin},
            })
            if not noti:
                avvisi.append(f"{casa} - {ospite}: squadra senza storico recente, stima poco affidabile")
            if not ev.get("mercato"):
                avvisi.append(f"{casa} - {ospite}: nessuna quota di mercato, uso solo il modello (soglia di valore piu' alta)")
    righe.sort(key=lambda r: (r["inizio"], r["campionato"], r["casa"]))
    return {
        "versione": 1, "demo": demo, "generato": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "modello": {"nome": modello_spec["modello"], "parametri": modello_spec["parametri"], "stimato_fino_a": str(data_rif.date())},
        "parametri": {
            "peso_modello": peso_modello,
            "soglie": {"valore_mercato_diretto": SOGLIA_VALORE, "valore_senza_mercato": SOGLIA_VALORE_SENZA_MERCATO,
                       "disaccordo": SOGLIA_DISACCORDO},
            "puntate": {"unita_euro": 1.0, "tetto_giornaliero_unita": TETTO_GIORNALIERO_UNITA,
                        "pausa_dopo_perdita_unita": PAUSA_PERDITA_SETTIMANA, "max_eventi_multipla": MAX_EVENTI_MULTIPLA,
                        "kelly_frazione": KELLY_FRAZIONE, "valore_alto_due_unita": VALORE_ALTO,
                        "quota_max_due_unita": QUOTA_MAX_DUE_UNITA},
            "mercati_diretti": sorted(MERCATI_DIRETTI),
        },
        "avvisi": avvisi, "avviso_gioco": AVVISO_GIOCO, "partite": righe,
    }


def eventi_demo(cartella_raw: Path, giorni: int = 7) -> tuple[dict[str, list[dict]], pd.Timestamp]:
    """Partite dell'ultima settimana dei CSV scaricati, con le quote MEDIE DI APERTURA come 'mercato' (solo prova)."""
    eventi: dict[str, list[dict]] = {}
    inizio_demo = None
    file_raw = sorted(cartella_raw.glob("*_*.csv"))
    stagione_ultima = max(f.stem.split("_")[0] for f in file_raw)      # solo la stagione piu' recente
    for f in [x for x in file_raw if x.stem.startswith(stagione_ultima)]:
        cod = f.stem.split("_")[1]
        df, _ = scarica_dati.leggi_csv(f.read_bytes())
        df["data_dt"] = scarica_dati._data(df["Date"])
        df = df.dropna(subset=["data_dt"])
        if df.empty:
            continue
        r = df[df["data_dt"] > df["data_dt"].max() - pd.Timedelta(days=giorni)]
        for d in r.to_dict("records"):
            try:
                q3 = np.array([float(d["AvgH"]), float(d["AvgD"]), float(d["AvgA"])])
            except (KeyError, TypeError, ValueError):
                continue
            p = toglie_margine(q3)
            m = {"1": float(p[0]), "X": float(p[1]), "2": float(p[2])}
            try:
                po = toglie_margine(np.array([float(d["Avg>2.5"]), float(d["Avg<2.5"])]))
                m["Over 2.5"], m["Under 2.5"] = float(po[0]), float(po[1])
            except (KeyError, TypeError, ValueError):
                pass
            eventi.setdefault(cod, []).append({"casa": d["HomeTeam"], "ospite": d["AwayTeam"],
                                               "inizio": f"{d['data_dt'].date()}T15:00:00Z", "mercato": m,
                                               "fonte": "media-apertura (demo)", "n_bookmaker": None})
            if inizio_demo is None or d["data_dt"] < inizio_demo:
                inizio_demo = d["data_dt"]
    return eventi, inizio_demo


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Genera consigli.json")
    p.add_argument("--sorgente", choices=["odds-api", "file", "demo"], default="demo")
    p.add_argument("--quote-file", type=Path)
    p.add_argument("--campionati", nargs="+", default=list(NOMI_CAMPIONATI), choices=list(NOMI_CAMPIONATI))
    p.add_argument("--peso-modello", type=float, default=PESO_MODELLO)
    p.add_argument("--file", type=Path, default=RADICE / "data" / "pulito" / "partite.csv")
    p.add_argument("--modello", type=Path, default=RADICE / "backtest" / "risultati" / "modello_finale.json")
    p.add_argument("--output", type=Path, default=RADICE / "data" / "consigli.json")
    a = p.parse_args(argv)

    partite = pd.read_csv(a.file, parse_dates=["data"])
    spec = json.loads(a.modello.read_text())
    avvisi_fonte: list[str] = []
    if a.sorgente == "demo":
        eventi, data_rif = eventi_demo(RADICE / "data" / "raw")
        eventi = {c: v for c, v in eventi.items() if c in a.campionati}
    elif a.sorgente == "file":
        eventi = {c: v for c, v in json.loads(a.quote_file.read_text()).items() if c in a.campionati}
        data_rif = pd.Timestamp(datetime.now(timezone.utc).date())
    else:
        eventi, data_rif = {}, pd.Timestamp(datetime.now(timezone.utc).date())
        for cod in a.campionati:
            try:
                dati, rimasti = fonte_quote.scarica_eventi(cod)
                eventi[cod] = fonte_quote.analizza_eventi(dati)
                print(f"{cod}: {len(eventi[cod])} partite con quote  {rimasti}")
            except Exception as e:  # una lega che fallisce non ferma le altre
                avvisi_fonte.append(f"{NOMI_CAMPIONATI[cod]}: quote non scaricate ({type(e).__name__})")
    out = costruisci_consigli(partite, eventi, spec, data_rif, a.peso_modello, demo=a.sorgente == "demo")
    out["avvisi"] = avvisi_fonte + out["avvisi"]
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Scritto {a.output} - {len(out['partite'])} partite, {len(out['avvisi'])} avvisi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

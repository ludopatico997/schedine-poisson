#!/usr/bin/env python3
"""Passo 9 - Controllo di sicurezza e qualita' di data/consigli.json PRIMA della pubblicazione.

Il repository e il sito sono pubblici: questo script e' l'ultima barriera prima del deploy su GitHub Pages.
Esiti:
  pubblica  il file e' valido e contiene partite  -> il workflow pubblica
  salta     nessuna partita ma nessun errore (pausa dei campionati) -> si tiene la versione di ieri
  errore    file mancante/rotto, chiave API presente nel testo, quote non scaricate: il workflow FALLISCE e non pubblica

    python3 engine/controlla_consigli.py data/consigli.json          (la chiave si legge da ODDS_API_KEY)
Se esiste GITHUB_OUTPUT scrive `pubblica=true|false` per i passaggi successivi.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MAX_BYTE = 5_000_000      # il file reale pesa poche centinaia di KB; oltre 5 MB qualcosa non va
TOLLERANZA_1X2 = 0.01


def controlla(testo: str, chiave: str | None = None) -> tuple[str, list[str], list[str]]:
    """Ritorna (esito, errori, avvisi). `testo` = contenuto del file; `chiave` = valore del segreto da NON trovare nel testo."""
    errori: list[str] = []
    avvisi: list[str] = []
    if len(testo.encode("utf-8")) > MAX_BYTE:
        errori.append(f"file troppo grande (> {MAX_BYTE} byte)")
    if chiave and len(chiave) >= 8 and chiave in testo:
        errori.append("la chiave API compare nel file: NON pubblicare")
    try:
        d = json.loads(testo)
    except json.JSONDecodeError as e:
        return "errore", errori + [f"JSON non valido ({e})"], avvisi
    if not isinstance(d, dict) or not isinstance(d.get("partite"), list):
        return "errore", errori + ["struttura inattesa: manca la lista 'partite'"], avvisi

    for p in d["partite"]:
        try:
            pr = p["riferimento"]["probabilita"]
            s = pr["1"] + pr["X"] + pr["2"]
            if abs(s - 1) > TOLLERANZA_1X2:
                errori.append(f"{p.get('id', '?')}: 1X2 somma {s:.3f}")
            if not (p["modello"]["lam"] > 0 and p["modello"]["mu"] > 0):
                errori.append(f"{p.get('id', '?')}: gol attesi non positivi")
        except (KeyError, TypeError) as e:
            errori.append(f"{p.get('id', '?') if isinstance(p, dict) else '?'}: campo mancante ({e})")
        if len(errori) >= 5:
            break

    fonte_ko = [a for a in d.get("avvisi", []) if "quote non scaricate" in a]
    if fonte_ko and not d["partite"]:
        errori.append("nessuna partita e quote non scaricate: " + "; ".join(fonte_ko))
    elif fonte_ko:
        avvisi.extend(fonte_ko)
    if errori:
        return "errore", errori, avvisi
    if not d["partite"]:
        return "salta", [], ["nessuna partita con quote: si tiene la versione precedente del sito"]
    return "pubblica", [], avvisi


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    percorso = Path(argv[0]) if argv else Path("data/consigli.json")
    if not percorso.exists():
        print(f"::error::{percorso} non esiste")
        return 1
    esito, errori, avvisi = controlla(percorso.read_text(encoding="utf-8"), os.environ.get("ODDS_API_KEY"))
    for e in errori:
        print(f"::error::{e}")
    for a in avvisi:
        print(f"::warning::{a}")
    print(f"Esito controllo: {esito}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"pubblica={'true' if esito == 'pubblica' else 'false'}\n")
    return 1 if esito == "errore" else 0


if __name__ == "__main__":
    raise SystemExit(main())

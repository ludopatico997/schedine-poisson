"""Passo 7 - Fonte delle quote di mercato per le partite future.

Fonte scelta: The Odds API (piano gratuito, chiave nei Secrets di GitHub, mai nel codice). Da verificare al primo
lancio con la chiave: chiavi dei campionati, bookmaker disponibili, crediti consumati (cfr. verifica_chiavi()).
Il test storico mostra che la media dei bookmaker senza margine e' precisa quasi quanto Pinnacle in chiusura
(log-loss 1X2 0.9754 vs 0.9752), quindi se Pinnacle manca si usa il consenso dei bookmaker.

NIENTE scraping dei siti dei bookmaker: solo API ufficiali o file forniti dall'utente.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from statistics import mean

import numpy as np

from engine.mercati import toglie_margine

URL_BASE = "https://api.the-odds-api.com/v4"
CHIAVI_SPORT = {   # da verificare con verifica_chiavi()
    "I1": "soccer_italy_serie_a", "I2": "soccer_italy_serie_b", "E0": "soccer_epl",
    "SP1": "soccer_spain_la_liga", "F1": "soccer_france_ligue_one", "D1": "soccer_germany_bundesliga",
}
MIN_BOOKMAKER_CONSENSO = 3


def _chiama(percorso: str, parametri: dict, timeout: int = 30):
    url = f"{URL_BASE}{percorso}?{urllib.parse.urlencode(parametri)}"
    req = urllib.request.Request(url, headers={"User-Agent": "app-schedine-poisson/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8")), dict(r.headers)


def chiavi_da_elenco(sport: list[dict]) -> dict:
    """Dato l'elenco /sports, dice quali chiavi di CHIAVI_SPORT esistono."""
    esistenti = {s["key"] for s in sport}
    return {cod: (k in esistenti) for cod, k in CHIAVI_SPORT.items()}


def verifica_chiavi(api_key: str | None = None) -> dict:
    """Elenca gli sport disponibili e dice quali chiavi di CHIAVI_SPORT esistono (questa chiamata non costa crediti)."""
    api_key = api_key or os.environ["ODDS_API_KEY"]
    sport, _ = _chiama("/sports", {"apiKey": api_key})
    return chiavi_da_elenco(sport)


def main() -> int:
    """`python3 -m engine.fonte_quote`: controlla la chiave e le chiavi dei campionati (gratis). Mai stampa la chiave."""
    api_key = os.environ.get("ODDS_API_KEY", "")
    if not api_key:
        print("ODDS_API_KEY non impostata")
        return 1
    try:
        sport, intest = _chiama("/sports", {"apiKey": api_key})
    except urllib.error.HTTPError as e:
        print(f"Errore HTTP {e.code}: chiave non valida o limite raggiunto" if e.code in (401, 429) else f"Errore HTTP {e.code}")
        return 1
    esito = chiavi_da_elenco(sport)
    for cod, ok in esito.items():
        print(f"{cod:4s} {CHIAVI_SPORT[cod]:32s} {'OK' if ok else 'NON TROVATA'}")
    if not all(esito.values()):
        print("Chiavi di calcio disponibili:", ", ".join(sorted(s["key"] for s in sport if s["key"].startswith("soccer_"))))
    print({k: v for k, v in intest.items() if k.lower().startswith("x-requests")})
    return 0 if all(esito.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())


def scarica_eventi(codice_campionato: str, api_key: str | None = None, regioni: str = "eu") -> tuple[list, dict]:
    """Quote 1X2 (h2h) e Under/Over (totals) delle prossime partite. Costo: 1 credito per mercato e regione."""
    api_key = api_key or os.environ["ODDS_API_KEY"]
    dati, intest = _chiama(f"/sports/{CHIAVI_SPORT[codice_campionato]}/odds",
                           {"apiKey": api_key, "regions": regioni, "markets": "h2h,totals",
                            "oddsFormat": "decimal", "dateFormat": "iso"})
    rimasti = {k: v for k, v in intest.items() if k.lower().startswith("x-requests")}
    return dati, rimasti


def _prob_bookmaker(bm: dict, casa: str, ospite: str) -> dict | None:
    """Probabilita' senza margine di un singolo bookmaker (1X2 obbligatorio, Under/Over 2.5 se c'e')."""
    out: dict[str, float] = {}
    for mk in bm.get("markets", []):
        if mk["key"] == "h2h":
            quote = {}
            for o in mk["outcomes"]:
                chiave = "1" if o["name"] == casa else "2" if o["name"] == ospite else "X" if o["name"].lower() == "draw" else None
                if chiave:
                    quote[chiave] = float(o["price"])
            if set(quote) == {"1", "X", "2"}:
                p = toglie_margine(np.array([quote["1"], quote["X"], quote["2"]]))
                out.update({"1": float(p[0]), "X": float(p[1]), "2": float(p[2])})
        elif mk["key"] == "totals":
            ov = un = None
            for o in mk["outcomes"]:
                if abs(float(o.get("point", 0)) - 2.5) < 1e-9:
                    ov, un = (float(o["price"]), un) if o["name"] == "Over" else (ov, float(o["price"]))
            if ov and un:
                p = toglie_margine(np.array([ov, un]))
                out.update({"Over 2.5": float(p[0]), "Under 2.5": float(p[1])})
    return out if {"1", "X", "2"} <= set(out) else None


def analizza_eventi(eventi: list) -> list[dict]:
    """Da risposta The Odds API a [{casa, ospite, inizio, mercato:{...}, fonte, n_bookmaker}].

    Se c'e' Pinnacle si usa quello; altrimenti la media delle probabilita' (senza margine) di almeno 3 bookmaker."""
    risultato = []
    for ev in eventi:
        casa, ospite = ev["home_team"], ev["away_team"]
        per_bm = {}
        for bm in ev.get("bookmakers", []):
            p = _prob_bookmaker(bm, casa, ospite)
            if p:
                per_bm[bm["key"]] = p
        if "pinnacle" in per_bm:
            mercato, fonte, n = per_bm["pinnacle"], "pinnacle", 1
        elif len(per_bm) >= MIN_BOOKMAKER_CONSENSO:
            chiavi = set.intersection(*[set(p) for p in per_bm.values()])
            if not {"1", "X", "2"} <= chiavi:
                continue
            chiavi_ou = [k for k in ("Over 2.5", "Under 2.5") if sum(k in p for p in per_bm.values()) >= MIN_BOOKMAKER_CONSENSO]
            mercato = {k: mean(p[k] for p in per_bm.values()) for k in ("1", "X", "2")}
            if len(chiavi_ou) == 2:
                ou = [mean(p[k] for p in per_bm.values() if k in p) for k in ("Over 2.5", "Under 2.5")]
                s = sum(ou)
                mercato["Over 2.5"], mercato["Under 2.5"] = ou[0] / s, ou[1] / s
            fonte, n = "consenso", len(per_bm)
        else:
            continue
        risultato.append({"casa": casa, "ospite": ospite, "inizio": ev["commence_time"],
                          "mercato": mercato, "fonte": fonte, "n_bookmaker": n})
    return risultato

#!/usr/bin/env python3
"""Passo 1 - Download e pulizia dei CSV storici di football-data.co.uk.

Cosa fa:
  1. scarica un CSV per ogni (stagione, campionato) in data/raw/ (cache locale);
  2. li pulisce e li unisce in un'unica tabella data/pulito/partite.csv;
  3. scrive data/pulito/copertura_quote.csv e stampa un riepilogo della copertura
     delle quote per campionato e stagione (da controllare prima del backtest).

Le cartelle data/raw/ e data/pulito/ NON vanno nel repository pubblico (.gitignore):
i CSV originali hanno una licenza che non ne consente la ridistribuzione.

Uso:
    python3 engine/scarica_dati.py                  # 2019/20 -> stagione in corso, 6 campionati
    python3 engine/scarica_dati.py --campionati I1 I2 --da 2021
    python3 engine/scarica_dati.py --offline        # usa solo i file gia' scaricati
    python3 engine/scarica_dati.py --forza          # riscarica tutto
"""
from __future__ import annotations

import argparse
import io
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

BASE_URL = "https://www.football-data.co.uk/mmz4281/{stagione}/{codice}.csv"
CAMPIONATI = {
    "I1": "Serie A",
    "I2": "Serie B",
    "E0": "Premier League",
    "SP1": "Liga",
    "F1": "Ligue 1",
    "D1": "Bundesliga",
}
RADICE = Path(__file__).resolve().parents[1]

# Fonti delle quote, in ordine di preferenza (riga per riga si usa la prima completa e valida).
# Pinnacle e' il riferimento preferito; la media di mercato e Bet365 sono i ripieghi.
FONTI_1X2_CH = [
    ("pinnacle", ("PSCH", "PSCD", "PSCA")),
    ("media", ("AvgCH", "AvgCD", "AvgCA")),
    ("bet365", ("B365CH", "B365CD", "B365CA")),
]
FONTI_1X2_AP = [
    ("pinnacle", ("PSH", "PSD", "PSA")),
    ("media", ("AvgH", "AvgD", "AvgA")),
    ("media", ("BbAvH", "BbAvD", "BbAvA")),
    ("bet365", ("B365H", "B365D", "B365A")),
]
FONTI_OU_CH = [
    ("pinnacle", ("PC>2.5", "PC<2.5")),
    ("media", ("AvgC>2.5", "AvgC<2.5")),
    ("bet365", ("B365C>2.5", "B365C<2.5")),
]
FONTI_OU_AP = [
    ("pinnacle", ("P>2.5", "P<2.5")),
    ("media", ("Avg>2.5", "Avg<2.5")),
    ("media", ("BbAv>2.5", "BbAv<2.5")),
    ("bet365", ("B365>2.5", "B365<2.5")),
]
# Controllo di coerenza: somma delle probabilita' implicite (1 / quota) = 1 + margine.
OVERROUND_MIN, OVERROUND_MAX = 0.99, 1.30


# ----------------------------------------------------------------------------- stagioni
def stagione_corrente(oggi: date | None = None) -> int:
    """Anno di inizio della stagione in corso (da luglio in poi inizia la nuova)."""
    oggi = oggi or date.today()
    return oggi.year if oggi.month >= 7 else oggi.year - 1


def codice_stagione(anno: int) -> str:
    """2025 -> '2526' (formato usato negli URL di football-data.co.uk)."""
    return f"{anno % 100:02d}{(anno + 1) % 100:02d}"


def etichetta_stagione(anno: int) -> str:
    """2025 -> '2025/26'."""
    return f"{anno}/{(anno + 1) % 100:02d}"


def partite_attese(codice: str, anno: int) -> int:
    """Numero di partite di una stagione completa (serve solo a segnalare file incompleti)."""
    if codice == "D1":
        return 306
    if codice == "F1":
        return 306 if anno >= 2023 else 380
    return 380


# ----------------------------------------------------------------------------- download
def scarica(url: str, timeout: int = 30) -> bytes:
    richiesta = urllib.request.Request(url, headers={"User-Agent": "app-schedine-poisson/1.0"})
    with urllib.request.urlopen(richiesta, timeout=timeout) as risposta:
        contenuto = risposta.read()
    inizio = contenuto[:200].lstrip(b"\xef\xbb\xbf").lower()
    if not inizio.startswith(b"div") or b"<html" in inizio:
        raise ValueError("la risposta non sembra un CSV di football-data.co.uk")
    return contenuto


def leggi_csv(contenuto: bytes) -> tuple[pd.DataFrame, int]:
    """Legge il CSV (tutto come testo). Ritorna (tabella, righe_del_file_non_lette)."""
    testo = None
    for codifica in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            testo = contenuto.decode(codifica)
            break
        except UnicodeDecodeError:
            continue
    righe_file = sum(1 for riga in testo.splitlines()[1:] if riga.strip(", \t\r"))
    df = pd.read_csv(
        io.StringIO(testo), dtype=str, skip_blank_lines=True,
        index_col=False, on_bad_lines="skip",
    )
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    df = df.dropna(how="all")
    return df, max(0, righe_file - len(df))


# ----------------------------------------------------------------------------- pulizia
def estrai_quote(df: pd.DataFrame, fonti, nomi_out: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    """Per ogni riga prende la prima fonte con tutte le quote valide (> 1, margine plausibile)."""
    risultato = pd.DataFrame(np.nan, index=df.index, columns=nomi_out)
    fonte = pd.Series("", index=df.index, dtype=object)
    for nome, colonne in fonti:
        if not all(c in df.columns for c in colonne):
            continue
        v = df[list(colonne)].apply(pd.to_numeric, errors="coerce")
        v = v.where(v > 1.0)
        margine = (1.0 / v).sum(axis=1, min_count=len(colonne))
        valide = v.notna().all(axis=1) & margine.between(OVERROUND_MIN, OVERROUND_MAX) & (fonte == "")
        if valide.any():
            risultato.loc[valide, nomi_out] = v.loc[valide].to_numpy()
            fonte[valide] = nome
    return risultato, fonte


def _data(serie: pd.Series) -> pd.Series:
    s = serie.astype(str).str.strip()
    d = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
    resto = d.isna()
    if resto.any():
        d[resto] = pd.to_datetime(s[resto], format="%d/%m/%y", errors="coerce")
    return d


def pulisci(df: pd.DataFrame, anno: int, codice: str) -> tuple[pd.DataFrame, dict]:
    """Normalizza una tabella grezza. Ritorna (tabella_pulita, problemi_riscontrati)."""
    obbligatorie = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]
    mancanti = [c for c in obbligatorie if c not in df.columns]
    if mancanti:
        raise ValueError(f"colonne obbligatorie assenti: {mancanti}")

    problemi = {"senza_risultato": 0, "data_non_valida": 0, "esito_incoerente": 0}
    df = df.copy()
    gc = pd.to_numeric(df["FTHG"], errors="coerce")
    go = pd.to_numeric(df["FTAG"], errors="coerce")
    data = _data(df["Date"])
    squadre_ok = df["HomeTeam"].notna() & df["AwayTeam"].notna()

    problemi["senza_risultato"] = int((squadre_ok & (gc.isna() | go.isna())).sum())  # partite non giocate
    problemi["data_non_valida"] = int((squadre_ok & gc.notna() & go.notna() & data.isna()).sum())
    tieni = squadre_ok & gc.notna() & go.notna() & data.notna()
    df, gc, go, data = df[tieni], gc[tieni], go[tieni], data[tieni]

    out = pd.DataFrame(index=df.index)
    out["stagione"] = etichetta_stagione(anno)
    out["campionato"] = codice
    out["data"] = data
    out["ora"] = df["Time"].fillna("").str.strip() if "Time" in df.columns else ""
    for nuova, vecchia in (("casa", "HomeTeam"), ("ospite", "AwayTeam")):
        out[nuova] = df[vecchia].str.strip().str.replace(r"\s+", " ", regex=True)
    out["gol_casa"] = gc.astype(int)
    out["gol_ospite"] = go.astype(int)
    out["esito"] = np.where(gc > go, "H", np.where(gc < go, "A", "D"))
    if "FTR" in df.columns:
        ftr = df["FTR"].fillna("").str.strip()
        problemi["esito_incoerente"] = int(((ftr != "") & (ftr != out["esito"])).sum())

    for nuova, vecchia in (("tiri_casa", "HS"), ("tiri_ospite", "AS"),
                           ("tiri_porta_casa", "HST"), ("tiri_porta_ospite", "AST")):
        out[nuova] = pd.to_numeric(df[vecchia], errors="coerce") if vecchia in df.columns else np.nan

    for suffisso, fonti in (("ap", FONTI_1X2_AP), ("ch", FONTI_1X2_CH)):
        q, f = estrai_quote(df, fonti, [f"q1_{suffisso}", f"qx_{suffisso}", f"q2_{suffisso}"])
        out = out.join(q)
        out[f"fonte_1x2_{suffisso}"] = f
    for suffisso, fonti in (("ap", FONTI_OU_AP), ("ch", FONTI_OU_CH)):
        q, f = estrai_quote(df, fonti, [f"over25_{suffisso}", f"under25_{suffisso}"])
        out = out.join(q)
        out[f"fonte_ou_{suffisso}"] = f
    return out.reset_index(drop=True), problemi


# ----------------------------------------------------------------------------- riepilogo
def _fonte_prevalente(serie: pd.Series) -> str:
    valori = serie[serie != ""]
    return valori.mode().iloc[0] if len(valori) else "-"


def riepilogo(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["campionato", "stagione"], sort=True)
    perc = lambda col: g[col].apply(lambda s: round(100 * s.notna().mean(), 1))  # noqa: E731
    r = pd.DataFrame({
        "partite": g.size(),
        "quote_1x2_ch_%": perc("q1_ch"),
        "quote_ou_ch_%": perc("over25_ch"),
        "fonte_1x2_ch": g["fonte_1x2_ch"].agg(_fonte_prevalente),
        "fonte_ou_ch": g["fonte_ou_ch"].agg(_fonte_prevalente),
    }).reset_index()
    r["attese"] = [partite_attese(c, int(s[:4])) for c, s in zip(r["campionato"], r["stagione"])]
    return r


# ----------------------------------------------------------------------------- main
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Scarica e pulisce i CSV storici di football-data.co.uk")
    p.add_argument("--da", type=int, default=2019, help="anno di inizio della prima stagione (2019 = 2019/20)")
    p.add_argument("--a", type=int, default=None, help="anno di inizio dell'ultima stagione (default: in corso)")
    p.add_argument("--campionati", nargs="+", default=list(CAMPIONATI), choices=list(CAMPIONATI))
    p.add_argument("--forza", action="store_true", help="riscarica anche le stagioni gia' in cache")
    p.add_argument("--offline", action="store_true", help="non scaricare nulla, usa solo la cache")
    p.add_argument("--cartella-dati", type=Path, default=RADICE / "data")
    args = p.parse_args(argv)

    corrente = stagione_corrente()
    ultimo = args.a if args.a is not None else corrente
    raw_dir, out_dir = args.cartella_dati / "raw", args.cartella_dati / "pulito"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    tabelle, avvisi = [], []
    for anno in range(args.da, ultimo + 1):
        for codice in args.campionati:
            sigla = f"{etichetta_stagione(anno)} {CAMPIONATI[codice]}"
            percorso = raw_dir / f"{codice_stagione(anno)}_{codice}.csv"
            contenuto = None
            # La stagione in corso si riscarica sempre (si aggiorna ogni settimana); le passate una volta sola.
            if not args.offline and (args.forza or anno >= corrente or not percorso.exists()):
                url = BASE_URL.format(stagione=codice_stagione(anno), codice=codice)
                try:
                    contenuto = scarica(url)
                    tmp = percorso.with_suffix(".tmp")
                    tmp.write_bytes(contenuto)
                    tmp.replace(percorso)
                    print(f"scaricato  {sigla}")
                    time.sleep(0.5)
                except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
                    avvisi.append(f"{sigla}: download non riuscito ({e})")
            if contenuto is None and percorso.exists():
                contenuto = percorso.read_bytes()
                print(f"da cache   {sigla}")
            if contenuto is None:
                avvisi.append(f"{sigla}: file non disponibile")
                continue
            try:
                grezzo, scartate = leggi_csv(contenuto)
                pulito, problemi = pulisci(grezzo, anno, codice)
            except Exception as e:  # un file rotto non deve fermare gli altri
                avvisi.append(f"{sigla}: file non leggibile ({e})")
                continue
            if scartate:
                avvisi.append(f"{sigla}: {scartate} righe del file non lette (formato irregolare)")
            for chiave, testo in (("data_non_valida", "con data non valida (scartate)"),
                                  ("esito_incoerente", "con esito FTR diverso dai gol (esito ricalcolato dai gol)")):
                if problemi[chiave]:
                    avvisi.append(f"{sigla}: {problemi[chiave]} partite {testo}")
            tabelle.append(pulito)

    if not tabelle:
        print("\nNessun dato disponibile.", *avvisi, sep="\n  ", file=sys.stderr)
        return 1

    partite = pd.concat(tabelle, ignore_index=True)
    prima = len(partite)
    partite = partite.drop_duplicates(subset=["campionato", "data", "casa", "ospite"])
    if len(partite) < prima:
        avvisi.append(f"rimosse {prima - len(partite)} partite duplicate")
    partite = partite.sort_values(["data", "campionato", "casa"]).reset_index(drop=True)
    partite.to_csv(out_dir / "partite.csv", index=False, date_format="%Y-%m-%d")

    r = riepilogo(partite)
    r.to_csv(out_dir / "copertura_quote.csv", index=False)
    print(f"\nPartite totali: {len(partite)} -> {out_dir / 'partite.csv'}\n")
    print(r.to_string(index=False))

    # Avvisi di copertura (sono segnalazioni da verificare, non errori)
    for _, riga in r.iterrows():
        sigla = f"{riga['stagione']} {CAMPIONATI[riga['campionato']]}"
        passata = int(riga["stagione"][:4]) < corrente
        if passata and riga["partite"] != riga["attese"]:
            avvisi.append(f"{sigla}: {riga['partite']} partite, attese {riga['attese']} "
                          "(puo' essere legittimo, es. stagione interrotta)")
        if riga["quote_1x2_ch_%"] < 90:
            avvisi.append(f"{sigla}: quote 1X2 di chiusura solo sul {riga['quote_1x2_ch_%']}% delle partite")
        if riga["quote_ou_ch_%"] < 90:
            avvisi.append(f"{sigla}: quote Under/Over di chiusura solo sul {riga['quote_ou_ch_%']}% delle partite")
    if avvisi:
        print("\nATTENZIONE:", *avvisi, sep="\n  - ")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Abbinamento dei nomi delle squadre tra fonti diverse (stessa logica di app/js/parser_quote.js)."""
from __future__ import annotations

import re
import unicodedata

ALIAS = {
    "paris sg": "paris saint germain", "psg": "paris saint germain", "internazionale": "inter",
    "inter milan": "inter", "ac milan": "milan", "atletico madrid": "ath madrid",
    "athletic bilbao": "ath bilbao", "athletic club": "ath bilbao", "borussia monchengladbach": "mgladbach",
    "gladbach": "mgladbach", "eintracht francoforte": "ein frankfurt", "eintracht frankfurt": "ein frankfurt",
    "bayern monaco": "bayern munich", "bayern munchen": "bayern munich", "manchester united": "man united",
    "manchester city": "man city", "newcastle united": "newcastle", "tottenham hotspur": "tottenham",
    "real sociedad": "sociedad", "celta vigo": "celta", "nottingham forest": "nottm forest",
    "wolverhampton wanderers": "wolves", "brighton and hove albion": "brighton", "west ham united": "west ham",
    "leeds united": "leeds", "real betis": "betis", "rayo vallecano": "vallecano", "deportivo alaves": "alaves",
    "rcd espanyol": "espanol", "espanyol": "espanol", "olympique marseille": "marseille",
    "olympique de marseille": "marseille", "olympique lyonnais": "lyon", "stade rennais": "rennes",
    "fc koln": "fc koln", "koln": "fc koln", "cologne": "fc koln", "hellas verona": "verona",
    "sudtirol": "sudtirol", "fc sudtirol": "sudtirol", "sud tirol": "sudtirol", "hamburger sv": "hamburg",
    "fc st pauli": "st pauli", "bayer leverkusen": "leverkusen", "borussia dortmund": "dortmund",
    "1 fc union berlin": "union berlin", "fsv mainz 05": "mainz", "tsg hoffenheim": "hoffenheim",
    "sc freiburg": "freiburg", "vfb stuttgart": "stuttgart", "fc augsburg": "augsburg", "sc paderborn": "paderborn",
    "la coruna": "la coruna", "deportivo la coruna": "la coruna", "racing santander": "santander",
    "sampdoria": "sampdoria", "juve stabia": "juve stabia", "virtus entella": "virtus entella",
}
VUOTE = {"fc", "ac", "as", "ssc", "us", "cf", "sc", "cfc", "calcio", "afc", "rc", "ud", "sd", "ca", "cd", "sv",
         "vfb", "vfl", "tsg", "fsv", "fk", "of", "1909", "1913", "1899", "1900", "1907", "1927", "04", "05", "96"}


def normalizza(nome: str) -> str:
    s = unicodedata.normalize("NFD", str(nome).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"['’`.]", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = ALIAS.get(s, s)
    tok = [t for t in s.split(" ") if t and t not in VUOTE]
    return " ".join(tok if tok else s.split(" "))


def _bigrammi(s: str) -> dict[str, int]:
    t = s.replace(" ", "")
    b: dict[str, int] = {}
    for i in range(len(t) - 1):
        b[t[i:i + 2]] = b.get(t[i:i + 2], 0) + 1
    return b


def _dice(a: str, b: str) -> float:
    A, B = _bigrammi(a), _bigrammi(b)
    na, nb = sum(A.values()), sum(B.values())
    if not na + nb:
        return 0.0
    return 2 * sum(min(v, B[g]) for g, v in A.items() if g in B) / (na + nb)


def punteggio(a: str, b: str) -> float:
    x, y = normalizza(a), normalizza(b)
    if not x or not y:
        return 0.0
    if x == y:
        return 1.0
    tx, ty = x.split(" "), y.split(" ")
    corti, lunghi = (tx, ty) if len(tx) <= len(ty) else (ty, tx)
    prefissi = all(len(c) >= 3 and any(l.startswith(c) for l in lunghi) for c in corti)
    return max(_dice(x, y), 0.9 if prefissi else 0.0)


def abbina(nome: str, elenco: list[str], soglia: float = 0.6) -> str | None:
    """Il nome piu' simile nell'elenco, oppure None se sotto soglia o ambiguo (due candidati quasi pari)."""
    if not elenco:
        return None
    cl = sorted(((punteggio(nome, e), e) for e in elenco), reverse=True)
    if cl[0][0] < soglia:
        return None
    if len(cl) > 1 and cl[1][0] >= cl[0][0] - 0.02:
        return None
    return cl[0][1]

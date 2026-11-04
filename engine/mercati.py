"""Passo 4 - Tutti i mercati del perimetro a partire dalla matrice dei punteggi.

matrice[i, j] = probabilita' che la squadra di casa faccia i gol e l'ospite j gol.
I nomi dei mercati sono gli stessi in tutto il progetto (modello, backtest, app).
"""
from __future__ import annotations

import numpy as np

LINEE_UO = [0.5, 1.5, 2.5, 3.5, 4.5]
MULTIGOL = [(1, 2), (1, 3), (1, 4), (1, 5), (2, 3), (2, 4), (2, 5), (2, 6), (3, 5), (3, 6)]


def toglie_margine(quote: np.ndarray) -> np.ndarray:
    """Probabilita' del mercato: 1/quota normalizzata a somma 1 (metodo proporzionale), per riga."""
    inv = 1.0 / np.asarray(quote, dtype=float)
    return inv / inv.sum(axis=-1, keepdims=True)


def _nome_uo(lato: str, linea: float) -> str:
    return f"{lato} {linea}"


def tutti_i_mercati(matrice: np.ndarray) -> dict[str, float]:
    """Probabilita' di ogni esito: 1X2, Doppia Chance, Under/Over (0.5-4.5), GG/NG, Multigol."""
    i, j = np.indices(matrice.shape)
    tot = i + j
    p1 = float(np.tril(matrice, -1).sum())
    px = float(np.trace(matrice))
    p2 = float(np.triu(matrice, 1).sum())
    gg = float(matrice[1:, 1:].sum())
    out = {"1": p1, "X": px, "2": p2, "1X": p1 + px, "X2": px + p2, "12": p1 + p2, "GG": gg, "NG": 1.0 - gg}
    for linea in LINEE_UO:
        over = float(matrice[tot > linea].sum())
        out[_nome_uo("Over", linea)] = over
        out[_nome_uo("Under", linea)] = 1.0 - over
    for a, b in MULTIGOL:
        out[f"Multigol {a}-{b}"] = float(matrice[(tot >= a) & (tot <= b)].sum())
    return out


def esiti_reali(gol_casa: int, gol_ospite: int) -> dict[str, int]:
    """Per un risultato noto, 1 se l'esito del mercato si e' verificato, altrimenti 0 (stessi nomi di tutti_i_mercati)."""
    tot = gol_casa + gol_ospite
    r = {"1": gol_casa > gol_ospite, "X": gol_casa == gol_ospite, "2": gol_casa < gol_ospite}
    r["1X"], r["X2"], r["12"] = r["1"] or r["X"], r["X"] or r["2"], r["1"] or r["2"]
    r["GG"] = gol_casa > 0 and gol_ospite > 0
    r["NG"] = not r["GG"]
    for linea in LINEE_UO:
        r[_nome_uo("Over", linea)] = tot > linea
        r[_nome_uo("Under", linea)] = tot < linea
    for a, b in MULTIGOL:
        r[f"Multigol {a}-{b}"] = a <= tot <= b
    return {k: int(v) for k, v in r.items()}


def quota_equa(p: float) -> float:
    """Quota giusta per una probabilita' p (senza margine)."""
    return 1.0 / p


def quota_minima_valore(p: float, soglia: float = 0.02) -> float:
    """Quota sotto la quale la giocata non ha il valore richiesto: (1 + soglia) / p."""
    return (1.0 + soglia) / p

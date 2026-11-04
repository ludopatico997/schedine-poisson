#!/usr/bin/env python3
"""Passo 5 - Secondo modello indipendente: Elo con differenza reti, mappato su gol attesi.

Perche' e' diverso dal Dixon-Coles
  Il Dixon-Coles stima attacco e difesa di ogni squadra su tutta la storia (con pesi temporali).
  L'Elo ha un solo numero per squadra, aggiornato dopo ogni partita in base a quanto il risultato
  sorprende (e di quanti gol). Reagisce piu' in fretta ai cambi di forma ma non separa attacco e difesa.

Come passa da rating a probabilita'
  1. differenza di rating d = R_casa - R_ospite (prima della partita);
  2. differenza reti attesa  gd = a + b * d   (a, b stimati con una regressione sulle partite passate);
  3. gol totali attesi T = media dei ritmi di gol delle due squadre (con riporto verso la media di lega);
  4. lam = (T + gd) / 2,  mu = (T - gd) / 2, poi la stessa matrice Poisson+rho del Dixon-Coles.
  Cosi' tutti i mercati (1X2, DC, Under/Over, Multigol, GG/NG) escono dalla stessa matrice.

Stessa interfaccia del DixonColes: fit(partite, data_rif), tassi(), matrice(), probabilita().
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.dixon_coles import matrice_punteggi, mercati_base


def moltiplicatore_gol(differenza: int) -> float:
    """Piu' e' larga la vittoria, piu' il rating si muove (schema standard dell'Elo calcistico)."""
    g = abs(int(differenza))
    if g <= 1:
        return 1.0
    return 1.5 if g == 2 else (11 + g) / 8.0


class Elo:
    def __init__(self, k: float = 20.0, vantaggio_casa: float = 70.0, regressione: float = 0.15,
                 offset_neopromossa: float = -40.0, decadimento_gol: float = 0.97, pseudo_partite: float = 8.0,
                 emivita_regressione_giorni: float = 730.0, rho: float = -0.05, max_gol: int = 10):
        self.k, self.vantaggio_casa, self.regressione = k, vantaggio_casa, regressione
        self.offset_neopromossa, self.decadimento_gol, self.pseudo_partite = offset_neopromossa, decadimento_gol, pseudo_partite
        self.emivita_regressione_giorni, self.rho, self.max_gol = emivita_regressione_giorni, rho, max_gol
        self.fitted = False

    def _rating_nuova(self, rating: dict) -> float:
        # una squadra che compare dopo che il campionato e' avviato (neopromossa) parte un po' sotto la media
        return float(np.mean(list(rating.values()))) + self.offset_neopromossa if len(rating) >= 10 else 1500.0

    def fit(self, partite: pd.DataFrame, data_rif: pd.Timestamp | None = None) -> "Elo":
        df = partite.copy()
        df["data"] = pd.to_datetime(df["data"])
        if data_rif is None:
            data_rif = df["data"].max() + pd.Timedelta(days=1)
        data_rif = pd.Timestamp(data_rif)
        df = df[df["data"] < data_rif].sort_values("data", kind="stable")
        if len(df) < 50:
            raise ValueError(f"troppe poche partite per stimare il modello ({len(df)})")

        rating: dict[str, float] = {}
        gol_somma: dict[str, float] = {}
        gol_n: dict[str, float] = {}
        d_pre, gd_vere, tot_vere, date = [], [], [], []
        stagione_prec = None
        dec = self.decadimento_gol
        for r in df.itertuples(index=False):
            stagione = getattr(r, "stagione", None)
            if stagione != stagione_prec:
                if stagione_prec is not None and self.regressione > 0 and rating:
                    media = float(np.mean(list(rating.values())))
                    for t in rating:   # a inizio stagione i rating tornano un po' verso la media
                        rating[t] = media + (1 - self.regressione) * (rating[t] - media)
                stagione_prec = stagione
            rh = rating.setdefault(r.casa, self._rating_nuova(rating))
            ra = rating.setdefault(r.ospite, self._rating_nuova(rating))
            d = rh - ra
            gd = int(r.gol_casa) - int(r.gol_ospite)
            tot = int(r.gol_casa) + int(r.gol_ospite)
            d_pre.append(d), gd_vere.append(gd), tot_vere.append(tot), date.append(r.data)

            atteso = 1.0 / (1.0 + 10.0 ** (-(d + self.vantaggio_casa) / 400.0))
            reale = 1.0 if gd > 0 else (0.5 if gd == 0 else 0.0)
            delta = self.k * moltiplicatore_gol(gd) * (reale - atteso)
            rating[r.casa], rating[r.ospite] = rh + delta, ra - delta
            for t in (r.casa, r.ospite):
                gol_somma[t] = dec * gol_somma.get(t, 0.0) + tot
                gol_n[t] = dec * gol_n.get(t, 0.0) + 1.0

        giorni = (data_rif - pd.Series(date)).dt.days.to_numpy(float)
        w = 0.5 ** (giorni / self.emivita_regressione_giorni)
        self.b, self.a = np.polyfit(np.array(d_pre), np.array(gd_vere, float), 1, w=np.sqrt(w))
        self.t_lega = float(np.average(tot_vere, weights=w))
        self.rating = pd.Series(rating)
        self._gol_somma, self._gol_n = gol_somma, gol_n
        self._iniziale = self._rating_nuova(rating)
        self.squadre = sorted(rating)
        self.n_partite = len(df)
        self.data_rif = data_rif
        self.convergenza = True
        self.fitted = True
        return self

    def _ritmo_gol(self, squadra: str) -> float:
        m = self.pseudo_partite
        return (self._gol_somma.get(squadra, 0.0) + m * self.t_lega) / (self._gol_n.get(squadra, 0.0) + m)

    def tassi(self, casa: str, ospite: str, porte_chiuse: bool = False) -> tuple[float, float, bool]:
        assert self.fitted, "chiamare prima fit()"
        noti = casa in self.rating.index and ospite in self.rating.index
        d = self.rating.get(casa, self._iniziale) - self.rating.get(ospite, self._iniziale)
        gd = self.a + self.b * d
        tot = (self._ritmo_gol(casa) + self._ritmo_gol(ospite)) / 2.0
        lam, mu = max((tot + gd) / 2.0, 0.15), max((tot - gd) / 2.0, 0.15)
        return float(lam), float(mu), noti

    def matrice(self, casa: str, ospite: str, porte_chiuse: bool = False) -> np.ndarray:
        lam, mu, _ = self.tassi(casa, ospite, porte_chiuse)
        return matrice_punteggi(lam, mu, self.rho, self.max_gol)

    def probabilita(self, casa: str, ospite: str, porte_chiuse: bool = False) -> dict:
        lam, mu, noti = self.tassi(casa, ospite, porte_chiuse)
        out = mercati_base(matrice_punteggi(lam, mu, self.rho, self.max_gol))
        out.update({"gol_attesi_casa": lam, "gol_attesi_ospite": mu, "rho": self.rho, "squadre_note": noti})
        return out

    def classifica(self) -> pd.DataFrame:
        return self.rating.sort_values(ascending=False).round(1).to_frame("rating")

"""Passo 5 - Ensemble: media (pesata) dei gol attesi di Dixon-Coles ed Elo.

Si mediano i gol attesi (non le probabilita') cosi' da avere ancora un'unica matrice dei punteggi da cui
ricavare tutti i mercati. Il rho e' quello del Dixon-Coles. Stessa interfaccia degli altri modelli.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.dixon_coles import DixonColes, matrice_punteggi, mercati_base
from engine.elo import Elo


class Ensemble:
    def __init__(self, peso_elo: float = 0.5, dc: DixonColes | None = None, elo: Elo | None = None):
        self.peso_elo = peso_elo
        self.dc = dc or DixonColes()
        self.elo = elo or Elo()
        self.fitted = False

    def fit(self, partite: pd.DataFrame, data_rif=None) -> "Ensemble":
        self.dc.fit(partite, data_rif)
        self.elo.fit(partite, data_rif)
        self.data_rif, self.n_partite, self.squadre = self.dc.data_rif, self.dc.n_partite, self.dc.squadre
        self.fitted = True
        return self

    @property
    def rho(self) -> float:
        return self.dc.rho

    @property
    def max_gol(self) -> int:
        return self.dc.max_gol

    def tassi(self, casa: str, ospite: str, porte_chiuse: bool = False) -> tuple[float, float, bool]:
        ld, md, noti = self.dc.tassi(casa, ospite, porte_chiuse)
        le, me, _ = self.elo.tassi(casa, ospite, porte_chiuse)
        w = self.peso_elo
        return (1 - w) * ld + w * le, (1 - w) * md + w * me, noti

    def matrice(self, casa: str, ospite: str, porte_chiuse: bool = False) -> np.ndarray:
        lam, mu, _ = self.tassi(casa, ospite, porte_chiuse)
        return matrice_punteggi(lam, mu, self.rho, self.max_gol)

    def probabilita(self, casa: str, ospite: str, porte_chiuse: bool = False) -> dict:
        lam, mu, noti = self.tassi(casa, ospite, porte_chiuse)
        out = mercati_base(matrice_punteggi(lam, mu, self.rho, self.max_gol))
        out.update({"gol_attesi_casa": lam, "gol_attesi_ospite": mu, "rho": self.rho, "squadre_note": noti})
        return out

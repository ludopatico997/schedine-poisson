#!/usr/bin/env python3
"""Passo 2 - Modello Dixon-Coles con pesi temporali.

Idea in breve
  Per ogni partita i gol di casa e ospite sono Poisson con medie
      lam = exp(c + vantaggio_casa + attacco[casa] - difesa[ospite])
      mu  = exp(c +                  attacco[ospite] - difesa[casa])
  (difesa piu' alta = squadra che subisce meno). Dixon e Coles correggono la
  probabilita' dei punteggi bassi (0-0, 1-0, 0-1, 1-1) con il parametro rho.
  Le partite vecchie pesano meno: peso = 0.5 ** (giorni_trascorsi / emivita).

Scelte di questa versione (tutte da verificare nel backtest del passo 3)
  - un modello per campionato (le squadre di campionati diversi non si incontrano);
  - leggera regolarizzazione ridge su attacco/difesa: stabilizza le squadre con pochi dati
    (neopromosse) e rende unica la soluzione;
  - vantaggio casa separato per il periodo a porte chiuse post-Covid (16/05/2020 - 30/06/2021,
    approssimazione uguale per tutti i campionati), con ridge che lo avvicina al valore normale se i dati sono pochi;
  - squadre mai viste: attacco = difesa = 0 (squadra media del campionato), segnalato nell'output.

Uso:
    python3 engine/dixon_coles.py --campionato I1 --data 2026-11-03
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import gammaln

RADICE = Path(__file__).resolve().parents[1]
PORTE_CHIUSE_DAL = pd.Timestamp("2020-05-16")
PORTE_CHIUSE_AL = pd.Timestamp("2021-06-30")


def segna_porte_chiuse(date: pd.Series) -> np.ndarray:
    """1.0 per le partite giocate nel periodo a porte chiuse/pubblico ridotto, altrimenti 0.0."""
    return ((date >= PORTE_CHIUSE_DAL) & (date <= PORTE_CHIUSE_AL)).to_numpy(float)


def _poisson_pmf(k: np.ndarray, media: float) -> np.ndarray:
    return np.exp(k * np.log(media) - media - gammaln(k + 1))


def matrice_punteggi(lam: float, mu: float, rho: float, max_gol: int = 10) -> np.ndarray:
    """Matrice[gol_casa, gol_ospite] con la correzione Dixon-Coles sui punteggi bassi, normalizzata a somma 1."""
    g = np.arange(max_gol + 1)
    m = np.outer(_poisson_pmf(g, lam), _poisson_pmf(g, mu))
    m[0, 0] *= max(1 - lam * mu * rho, 1e-10)
    m[0, 1] *= max(1 + lam * rho, 1e-10)
    m[1, 0] *= max(1 + mu * rho, 1e-10)
    m[1, 1] *= max(1 - rho, 1e-10)
    return m / m.sum()


def mercati_base(matrice: np.ndarray) -> dict:
    """Da matrice[gol_casa, gol_ospite] ricava 1X2 e Under/Over 2.5."""
    i, j = np.indices(matrice.shape)
    tot = i + j
    return {
        "p1": float(np.tril(matrice, -1).sum()),
        "px": float(np.trace(matrice)),
        "p2": float(np.triu(matrice, 1).sum()),
        "over25": float(matrice[tot >= 3].sum()),
        "under25": float(matrice[tot <= 2].sum()),
    }


class DixonColes:
    def __init__(self, emivita_giorni: float = 365.0, ridge: float = 1.0, max_gol: int = 10):
        self.emivita_giorni = emivita_giorni
        self.ridge = ridge
        self.max_gol = max_gol
        self.fitted = False

    # ------------------------------------------------------------------ pesi
    def pesi(self, date: pd.Series, data_rif: pd.Timestamp) -> np.ndarray:
        giorni = (data_rif - date).dt.days.to_numpy(float)
        return 0.5 ** (giorni / self.emivita_giorni)

    # ------------------------------------------------------------------ funzione obiettivo
    def _nll(self, th, h, a, x, y, w, chiuse, n):
        """Log-verosimiglianza pesata cambiata di segno, con gradiente analitico."""
        c, ha, hac, rho = th[0], th[1], th[2], th[3]
        att, dif = th[4:4 + n], th[4 + n:]
        lm_l = c + (1 - chiuse) * ha + chiuse * hac + att[h] - dif[a]
        lm_m = c + att[a] - dif[h]
        lam, mu = np.exp(lm_l), np.exp(lm_m)

        m00 = (x == 0) & (y == 0)
        m01 = (x == 0) & (y == 1)
        m10 = (x == 1) & (y == 0)
        m11 = (x == 1) & (y == 1)
        tau = np.ones_like(lam)
        tau = np.where(m00, 1 - lam * mu * rho, tau)
        tau = np.where(m01, 1 + lam * rho, tau)
        tau = np.where(m10, 1 + mu * rho, tau)
        tau = np.where(m11, 1 - rho, tau)
        tau = np.maximum(tau, 1e-10)

        ll = (w * (x * lm_l - lam + y * lm_m - mu + np.log(tau))).sum()

        # derivate rispetto a log(lam), log(mu), rho
        g_l = x - lam + np.where(m00, -lam * mu * rho / tau, 0.0) + np.where(m01, lam * rho / tau, 0.0)
        g_m = y - mu + np.where(m00, -lam * mu * rho / tau, 0.0) + np.where(m10, mu * rho / tau, 0.0)
        g_r = (np.where(m00, -lam * mu / tau, 0.0) + np.where(m01, lam / tau, 0.0)
               + np.where(m10, mu / tau, 0.0) + np.where(m11, -1.0 / tau, 0.0))
        wl, wm = w * g_l, w * g_m

        grad = np.empty_like(th)
        grad[0] = wl.sum() + wm.sum()
        grad[1] = (wl * (1 - chiuse)).sum()
        grad[2] = (wl * chiuse).sum()
        grad[3] = (w * g_r).sum()
        grad[4:4 + n] = np.bincount(h, wl, n) + np.bincount(a, wm, n)
        grad[4 + n:] = -np.bincount(a, wl, n) - np.bincount(h, wm, n)

        r = self.ridge
        pen = r * (att @ att + dif @ dif) + r * (hac - ha) ** 2
        grad = -grad
        grad[4:4 + n] += 2 * r * att
        grad[4 + n:] += 2 * r * dif
        grad[2] += 2 * r * (hac - ha)
        grad[1] -= 2 * r * (hac - ha)
        return -ll + pen, grad

    # ------------------------------------------------------------------ stima
    def fit(self, partite: pd.DataFrame, data_rif: pd.Timestamp | None = None) -> "DixonColes":
        """Stima il modello con le partite precedenti a data_rif (escluse quelle del giorno stesso e dopo)."""
        df = partite.copy()
        df["data"] = pd.to_datetime(df["data"])
        if data_rif is None:
            data_rif = df["data"].max() + pd.Timedelta(days=1)
        data_rif = pd.Timestamp(data_rif)
        df = df[df["data"] < data_rif]
        if len(df) < 50:
            raise ValueError(f"troppe poche partite per stimare il modello ({len(df)})")

        squadre = sorted(set(df["casa"]) | set(df["ospite"]))
        indice = {s: i for i, s in enumerate(squadre)}
        n = len(squadre)
        h = df["casa"].map(indice).to_numpy()
        a = df["ospite"].map(indice).to_numpy()
        x = df["gol_casa"].to_numpy(float)
        y = df["gol_ospite"].to_numpy(float)
        w = self.pesi(df["data"], data_rif)
        chiuse = segna_porte_chiuse(df["data"])

        th0 = np.zeros(4 + 2 * n)
        th0[0] = np.log(max((x.mean() + y.mean()) / 2, 0.5))
        th0[1] = th0[2] = 0.25
        limiti = [(-2, 2), (-0.5, 1.0), (-0.5, 1.0), (-0.5, 0.5)] + [(-3, 3)] * (2 * n)
        ris = minimize(self._nll, th0, args=(h, a, x, y, w, chiuse, n), jac=True,
                       method="L-BFGS-B", bounds=limiti, options={"maxiter": 1000})

        th = ris.x
        att, dif = th[4:4 + n], th[4 + n:]
        centro = att.mean()  # sposta attacco e difesa insieme: le probabilita' non cambiano
        self.c, self.ha, self.ha_chiuse, self.rho = th[0], th[1], th[2], th[3]
        self.att = pd.Series(att - centro, index=squadre)
        self.dif = pd.Series(dif - centro, index=squadre)
        self.squadre = squadre
        self.n_partite = len(df)
        self.data_rif = data_rif
        self.convergenza = bool(ris.success)
        self.messaggio = str(ris.message)
        self.fitted = True
        return self

    # ------------------------------------------------------------------ previsione
    def tassi(self, casa: str, ospite: str, porte_chiuse: bool = False) -> tuple[float, float, bool]:
        """Gol attesi (casa, ospite) e flag: True se entrambe le squadre sono note al modello."""
        assert self.fitted, "chiamare prima fit()"
        noti = casa in self.att.index and ospite in self.att.index
        ac, dc = self.att.get(casa, 0.0), self.dif.get(casa, 0.0)
        ao, do = self.att.get(ospite, 0.0), self.dif.get(ospite, 0.0)
        vantaggio = self.ha_chiuse if porte_chiuse else self.ha
        lam = float(np.exp(self.c + vantaggio + ac - do))
        mu = float(np.exp(self.c + ao - dc))
        return lam, mu, noti

    def matrice(self, casa: str, ospite: str, porte_chiuse: bool = False) -> np.ndarray:
        """Probabilita' di ogni punteggio: matrice[gol_casa, gol_ospite], somma 1."""
        lam, mu, _ = self.tassi(casa, ospite, porte_chiuse)
        return matrice_punteggi(lam, mu, self.rho, self.max_gol)

    def probabilita(self, casa: str, ospite: str, porte_chiuse: bool = False) -> dict:
        lam, mu, noti = self.tassi(casa, ospite, porte_chiuse)
        out = mercati_base(self.matrice(casa, ospite, porte_chiuse))
        out.update({"gol_attesi_casa": lam, "gol_attesi_ospite": mu, "rho": self.rho, "squadre_note": noti})
        return out

    def classifica(self) -> pd.DataFrame:
        """Forza delle squadre (attacco + difesa), dalla piu' forte."""
        t = pd.DataFrame({"attacco": self.att, "difesa": self.dif})
        t["forza"] = t["attacco"] + t["difesa"]
        return t.sort_values("forza", ascending=False)


def adatta_tutte(partite: pd.DataFrame, data_rif=None, **kw) -> dict[str, DixonColes]:
    """Un modello per campionato: {codice_campionato: DixonColes}."""
    return {cod: DixonColes(**kw).fit(g, data_rif) for cod, g in partite.groupby("campionato")}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Stima il Dixon-Coles su un campionato e mostra le forze delle squadre")
    p.add_argument("--campionato", default="I1", choices=["I1", "I2", "E0", "SP1", "F1", "D1"])
    p.add_argument("--data", default=None, help="usa solo le partite precedenti a questa data (AAAA-MM-GG)")
    p.add_argument("--emivita", type=float, default=365.0, help="emivita dei pesi in giorni")
    p.add_argument("--file", type=Path, default=RADICE / "data" / "pulito" / "partite.csv")
    args = p.parse_args(argv)

    partite = pd.read_csv(args.file, parse_dates=["data"])
    partite = partite[partite["campionato"] == args.campionato]
    m = DixonColes(emivita_giorni=args.emivita).fit(partite, args.data)
    print(f"{args.campionato}: {m.n_partite} partite fino al {(m.data_rif - pd.Timedelta(days=1)).date()}, "
          f"convergenza={m.convergenza}")
    print(f"vantaggio casa={m.ha:.3f}  (porte chiuse={m.ha_chiuse:.3f})  rho={m.rho:.3f}  c={m.c:.3f}")
    attive = m.classifica()
    recenti = set(partite[partite["data"] >= m.data_rif - pd.Timedelta(days=400)][["casa", "ospite"]].stack())
    print(attive[attive.index.isin(recenti)].round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

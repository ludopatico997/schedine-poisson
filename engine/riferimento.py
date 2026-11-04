"""Passo 4 - Quota di riferimento: mercato + modello, valore e semaforo.

Idea
  1. Dalle quote del mercato (1X2 e, se ci sono, Under/Over 2.5) si tolgono i margini e si ricavano i gol
     attesi (lam, mu) che le riproducono meglio. Cosi' il mercato porta con se' infortuni, formazioni, notizie.
  2. I gol attesi del modello e quelli del mercato si mescolano (media geometrica, peso_modello di default 10%).
  3. Da un'unica matrice dei punteggi si ricavano TUTTI i mercati, anche quelli senza quota di confronto
     (Multigol, GG/NG, linee Under/Over diverse da 2.5).
  4. Il valore di una giocata = probabilita' di riferimento x quota del bookmaker - 1.
  5. Semaforo: verde (valore sopra soglia e modello d'accordo con il mercato), giallo (valore ma forte
     disaccordo), rosso (valore insufficiente).
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

from engine.dixon_coles import matrice_punteggi, mercati_base
from engine.mercati import quota_minima_valore, toglie_margine, tutti_i_mercati

PESO_MODELLO = 0.10
SOGLIA_VALORE = 0.02                 # mercati con quota di mercato diretta (1X2, DC, Under/Over 2.5)
SOGLIA_VALORE_SENZA_MERCATO = 0.08   # Multigol, GG/NG, altre linee: nessuna quota di confronto; GG/NG e Multigol
                                     # nel backtest sono quasi pari alle frequenze storiche (vedi rapporto_mercati.md)
SOGLIA_DISACCORDO = 0.10             # oltre questa differenza di probabilita' il modello perde chiaramente col mercato
                                     # (backtest: >0.10 su 29% delle partite, -0.057 di log-loss, IC95 +-0.016)
MERCATI_DIRETTI = {"1", "X", "2", "1X", "X2", "12", "Over 2.5", "Under 2.5"}


def probabilita_mercato(q1: float, qx: float, q2: float, q_over25: float | None = None,
                        q_under25: float | None = None) -> dict[str, float]:
    """Probabilita' del mercato senza margine (metodo proporzionale)."""
    p = toglie_margine(np.array([q1, qx, q2]))
    out = {"1": float(p[0]), "X": float(p[1]), "2": float(p[2])}
    if q_over25 and q_under25:
        po = toglie_margine(np.array([q_over25, q_under25]))
        out["Over 2.5"], out["Under 2.5"] = float(po[0]), float(po[1])
    return out


def lam_mu_da_mercato(p: dict[str, float], rho: float = -0.07, max_gol: int = 10) -> tuple[float, float, float]:
    """Gol attesi (lam, mu) che riproducono al meglio le probabilita' del mercato. Ritorna anche l'errore massimo."""
    def residui(x):
        b = mercati_base(matrice_punteggi(np.exp(x[0]), np.exp(x[1]), rho, max_gol))
        r = [b["p1"] - p["1"], b["px"] - p["X"], b["p2"] - p["2"]]
        if "Over 2.5" in p:
            r.append(b["over25"] - p["Over 2.5"])
        return r

    sol = least_squares(residui, x0=[np.log(1.4), np.log(1.1)], bounds=([-3, -3], [2.5, 2.5]))
    return float(np.exp(sol.x[0])), float(np.exp(sol.x[1])), float(np.abs(sol.fun).max())


def riferimento(lam_mod: float, mu_mod: float, rho: float, mercato: dict[str, float] | None = None,
                peso_modello: float = PESO_MODELLO, max_gol: int = 10) -> dict:
    """Probabilita' di riferimento di tutti i mercati, mescolando mercato e modello."""
    prob_mod = tutti_i_mercati(matrice_punteggi(lam_mod, mu_mod, rho, max_gol))
    if mercato is None:
        lam, mu, fonte, disaccordo, residuo = lam_mod, mu_mod, "modello", None, None
    else:
        lam_k, mu_k, residuo = lam_mu_da_mercato(mercato, rho, max_gol)
        w = float(np.clip(peso_modello, 0.0, 1.0))
        lam, mu = lam_k ** (1 - w) * lam_mod ** w, mu_k ** (1 - w) * mu_mod ** w
        fonte = "mercato+modello" if w > 0 else "mercato"
        disaccordo = max(abs(prob_mod[k] - v) for k, v in mercato.items())
    return {"lam": lam, "mu": mu, "rho": rho, "fonte": fonte, "disaccordo": disaccordo,
            "residuo_ancoraggio": residuo, "peso_modello": peso_modello if mercato else 1.0,
            "probabilita": tutti_i_mercati(matrice_punteggi(lam, mu, rho, max_gol)),
            "prob_modello": prob_mod, "prob_mercato": mercato}


def valore(prob: float, quota_bookmaker: float) -> float:
    """Guadagno atteso per 1 unita' puntata: prob x quota - 1."""
    return prob * quota_bookmaker - 1.0


def semaforo(val: float, disaccordo: float | None, diretto: bool, soglia_valore: float = SOGLIA_VALORE,
             soglia_senza_mercato: float = SOGLIA_VALORE_SENZA_MERCATO,
             soglia_disaccordo: float = SOGLIA_DISACCORDO) -> tuple[str, str]:
    soglia = soglia_valore if diretto else soglia_senza_mercato
    if val < soglia:
        return "rosso", f"valore {val:+.1%} sotto la soglia richiesta ({soglia:+.0%})"
    if disaccordo is not None and disaccordo > soglia_disaccordo:
        return "giallo", (f"valore {val:+.1%}, ma modello e mercato differiscono di {disaccordo:.0%}: "
                          "controlla infortuni e formazioni")
    nota = "" if diretto else " (stima non verificabile con quote di mercato)"
    return "verde", f"valore {val:+.1%} sopra la soglia ({soglia:+.0%}){nota}"


def scheda(rif: dict, quote_bookmaker: dict[str, float], **soglie) -> list[dict]:
    """Per ogni quota del bookmaker: probabilita', quota equa, valore, quota minima e semaforo."""
    righe = []
    pm = rif["prob_mercato"] or {}
    for nome, q in quote_bookmaker.items():
        p = rif["probabilita"][nome]
        diretto = nome in MERCATI_DIRETTI and (nome not in ("Over 2.5", "Under 2.5") or nome in pm) and bool(pm)
        v = valore(p, q)
        colore, motivo = semaforo(v, rif["disaccordo"], diretto, **soglie)
        righe.append({"mercato": nome, "prob_riferimento": p, "quota_equa": 1 / p, "quota_bookmaker": q,
                      "diretto": diretto, "valore": v, "quota_minima": quota_minima_valore(
                          p, soglie.get("soglia_valore", SOGLIA_VALORE) if diretto
                          else soglie.get("soglia_senza_mercato", SOGLIA_VALORE_SENZA_MERCATO)),
                      "semaforo": colore, "motivo": motivo})
    return righe

"""Fabbrica dei modelli: 'dc' = Dixon-Coles, 'elo' = Elo, 'ens' = ensemble (media dei gol attesi)."""
from __future__ import annotations

from engine.dixon_coles import DixonColes
from engine.elo import Elo
from engine.ensemble import Ensemble


def crea_modello(nome: str, parametri: dict):
    """parametri per 'ens': peso_elo, dc={...parametri Dixon-Coles}, piu' i parametri dell'Elo."""
    p = dict(parametri)
    if nome == "dc":
        return DixonColes(**p)
    if nome == "elo":
        return Elo(**p)
    if nome == "ens":
        peso = p.pop("peso_elo", 0.5)
        dc = DixonColes(**p.pop("dc", {}))
        return Ensemble(peso_elo=peso, dc=dc, elo=Elo(**p))
    raise ValueError(f"modello sconosciuto: {nome}")

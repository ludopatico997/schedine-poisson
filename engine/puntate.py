"""Passo 6 - Gestione delle puntate: Kelly frazionato, unita' fisse, tetti e multipla.

Regole del progetto (budget 30 EUR al mese, 1 unita' = 1 EUR):
  - si gioca solo con semaforo VERDE; i gialli vanno controllati a mano, i rossi non si giocano;
  - Kelly (f = (p*q - 1) / (q - 1), frazione 1/4) serve a ORDINARE le giocate; la puntata e' poi in unita' fisse;
  - singola: 1 unita'; 2 unita' solo con valore molto alto su un mercato con quota di mercato diretta
    (probabilita' piu' affidabile) e quota non troppo alta;
  - multipla: sempre 1 unita', massimo 3 eventi, mai due eventi della stessa partita;
  - tetto giornaliero 3 unita'; pausa obbligatoria se in una settimana si perdono 10 unita';
  - una sola giocata per partita (due mercati della stessa partita sono correlati).
Nessuna garanzia di profitto: il valore stimato e' incerto e il margine del bookmaker e' sempre un costo.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

KELLY_FRAZIONE = 0.25
TETTO_GIORNALIERO_UNITA = 3
PAUSA_PERDITA_SETTIMANA = 10
MAX_EVENTI_MULTIPLA = 3
VALORE_ALTO = 0.06           # valore atteso minimo per puntare 2 unita'
QUOTA_MAX_DUE_UNITA = 3.5    # sopra questa quota la probabilita' e' bassa e piu' incerta: resta 1 unita'


def kelly(p: float, q: float) -> float:
    """Frazione del bankroll di Kelly pieno (0 se la giocata non ha valore)."""
    if q <= 1.0:
        return 0.0
    return max((p * q - 1.0) / (q - 1.0), 0.0)


def kelly_frazionato(p: float, q: float, frazione: float = KELLY_FRAZIONE) -> float:
    return frazione * kelly(p, q)


def unita_singola(valore: float, quota: float, diretto: bool) -> int:
    """1 unita', oppure 2 con valore molto alto, mercato diretto e quota moderata."""
    return 2 if (diretto and valore >= VALORE_ALTO and quota <= QUOTA_MAX_DUE_UNITA) else 1


def perdita_ultimi_giorni(storico: list[dict], oggi: date, giorni: int = 7) -> float:
    """Perdita netta (in unita', >= 0) negli ultimi `giorni`. storico: [{'data': date, 'profitto_unita': float}]."""
    da = oggi - timedelta(days=giorni - 1)
    netto = sum(s["profitto_unita"] for s in storico if da <= s["data"] <= oggi)
    return max(-netto, 0.0)


def seleziona_giocate(candidati: list[dict], valore_unita: float = 1.0, bankroll: float | None = None,
                      perdita_settimana: float = 0.0, tetto: int = TETTO_GIORNALIERO_UNITA,
                      max_multipla: int = MAX_EVENTI_MULTIPLA) -> dict:
    """Sceglie singole e (eventualmente) una multipla tra le giocate proposte.

    candidati: righe di riferimento.scheda() con in piu' 'partita' (id) e 'etichetta' (testo da mostrare).
    """
    msg: list[str] = []
    vuoto = {"stato": "nessuna", "singole": [], "multipla": None, "unita_totali": 0, "importo_totale": 0.0, "messaggi": msg}
    if perdita_settimana >= PAUSA_PERDITA_SETTIMANA:
        msg.append(f"PAUSA: in una settimana hai perso {perdita_settimana:.0f} unita'. Nessuna giocata finche' non fai una revisione.")
        return {**vuoto, "stato": "pausa"}

    gialli = [c for c in candidati if c["semaforo"] == "giallo"]
    if gialli:
        msg.append(f"{len(gialli)} giocate in giallo: modello e mercato sono in disaccordo, controlla infortuni e formazioni prima di decidere.")
    verdi = [c for c in candidati if c["semaforo"] == "verde"]
    if not verdi:
        msg.append("Nessuna giocata con valore sufficiente: oggi non giocare e' la scelta migliore.")
        return vuoto

    for c in verdi:
        c["kelly"] = kelly_frazionato(c["prob_riferimento"], c["quota_bookmaker"])
    verdi.sort(key=lambda c: (c["kelly"], c["valore"]), reverse=True)

    scelte, viste = [], set()
    for c in verdi:                                  # una sola giocata per partita
        if c["partita"] in viste:
            msg.append(f"{c['etichetta']}: scartata, hai gia' una giocata su questa partita (esiti correlati).")
            continue
        viste.add(c["partita"])
        scelte.append(c)

    limite = tetto
    if bankroll is not None:
        limite = min(limite, int(bankroll // valore_unita))
        if limite < tetto:
            msg.append(f"Bankroll basso: massimo {limite} unita' disponibili.")
    singole, usate = [], 0
    for c in scelte:
        u = unita_singola(c["valore"], c["quota_bookmaker"], c.get("diretto", False))
        if usate + u > limite:
            u = limite - usate
        if u <= 0:
            msg.append(f"{c['etichetta']}: oltre il tetto di {tetto} unita' al giorno, non giocata.")
            continue
        usate += u
        singole.append({**c, "unita": u, "importo": u * valore_unita})

    multipla = None
    legs = scelte[:max_multipla]
    if len(legs) >= 2 and usate + 1 <= limite:
        quota = math.prod(c["quota_bookmaker"] for c in legs)
        prob = math.prod(c["prob_riferimento"] for c in legs)
        multipla = {"eventi": [c["etichetta"] for c in legs], "partite": [c["partita"] for c in legs],
                    "quota_totale": quota, "prob_totale": prob, "valore": prob * quota - 1.0,
                    "unita": 1, "importo": valore_unita,
                    "nota": "Ogni evento in piu' aggiunge il margine del bookmaker e fa salire la varianza: una sola unita'."}
        usate += 1
    elif len(legs) >= 2:
        msg.append("Multipla non proposta: tetto giornaliero raggiunto con le singole.")

    return {"stato": "ok" if singole or multipla else "nessuna", "singole": singole, "multipla": multipla,
            "unita_totali": usate, "importo_totale": usate * valore_unita, "messaggi": msg}

"""Test di puntate.py.  python3 -m unittest engine.test_puntate -v"""
import unittest
from datetime import date

from engine import puntate as pu


def cand(partita, mercato, p, q, semaforo="verde", diretto=True):
    v = p * q - 1
    return {"partita": partita, "etichetta": f"{partita} {mercato}", "mercato": mercato, "prob_riferimento": p,
            "quota_bookmaker": q, "valore": v, "semaforo": semaforo, "diretto": diretto}


class TestKelly(unittest.TestCase):
    def test_formula(self):
        self.assertAlmostEqual(pu.kelly(0.5, 2.2), (0.5 * 2.2 - 1) / 1.2)
        self.assertEqual(pu.kelly(0.4, 2.0), 0.0)          # senza valore
        self.assertEqual(pu.kelly(0.9, 1.0), 0.0)
        self.assertAlmostEqual(pu.kelly_frazionato(0.5, 2.2), 0.25 * pu.kelly(0.5, 2.2))

    def test_unita(self):
        self.assertEqual(pu.unita_singola(0.03, 2.0, True), 1)
        self.assertEqual(pu.unita_singola(0.08, 2.0, True), 2)
        self.assertEqual(pu.unita_singola(0.08, 4.0, True), 1)     # quota alta
        self.assertEqual(pu.unita_singola(0.08, 2.0, False), 1)    # senza mercato diretto


class TestPerdita(unittest.TestCase):
    def test_ultimi_sette_giorni(self):
        oggi = date(2026, 11, 10)
        st = [{"data": date(2026, 11, 3), "profitto_unita": -4}, {"data": date(2026, 11, 4), "profitto_unita": -8},
              {"data": date(2026, 11, 9), "profitto_unita": 3}, {"data": date(2026, 11, 2), "profitto_unita": -50}]
        self.assertEqual(pu.perdita_ultimi_giorni(st, oggi), 5.0)   # finestra 4-10/11: -8 +3; il 2 e 3/11 sono fuori
        self.assertEqual(pu.perdita_ultimi_giorni([{"data": oggi, "profitto_unita": 5}], oggi), 0.0)


class TestSelezione(unittest.TestCase):
    def test_pausa_dopo_dieci_unita_perse(self):
        r = pu.seleziona_giocate([cand("A", "1", 0.5, 2.2)], perdita_settimana=10)
        self.assertEqual(r["stato"], "pausa")
        self.assertEqual(r["unita_totali"], 0)

    def test_nessun_verde(self):
        r = pu.seleziona_giocate([cand("A", "1", 0.5, 1.9, "rosso"), cand("B", "X", 0.3, 3.5, "giallo")])
        self.assertEqual(r["stato"], "nessuna")
        self.assertTrue(any("giallo" in m for m in r["messaggi"]))

    def test_una_giocata_per_partita(self):
        r = pu.seleziona_giocate([cand("A", "1", 0.5, 2.2), cand("A", "Over 2.5", 0.55, 2.0)])
        self.assertEqual(len(r["singole"]), 1)
        self.assertEqual(r["singole"][0]["partita"], "A")

    def test_ordine_per_kelly_e_tetto(self):
        cs = [cand("A", "1", 0.50, 2.20), cand("B", "1", 0.55, 2.10), cand("C", "2", 0.40, 2.80),
              cand("D", "1", 0.60, 1.80), cand("E", "X", 0.30, 3.50)]
        r = pu.seleziona_giocate(cs)
        self.assertLessEqual(r["unita_totali"], 3)
        kel = [c["kelly"] for c in r["singole"]]
        self.assertEqual(kel, sorted(kel, reverse=True))
        self.assertTrue(any("tetto" in m or "Multipla non proposta" in m for m in r["messaggi"]))

    def test_due_unita_solo_con_valore_alto(self):
        r = pu.seleziona_giocate([cand("A", "1", 0.55, 2.10)])    # valore +15.5%, mercato diretto
        self.assertEqual(r["singole"][0]["unita"], 2)
        r2 = pu.seleziona_giocate([cand("A", "1", 0.50, 2.10)])   # valore +5%
        self.assertEqual(r2["singole"][0]["unita"], 1)

    def test_multipla_una_unita_eventi_diversi(self):
        r = pu.seleziona_giocate([cand("A", "1", 0.50, 2.10), cand("B", "X", 0.30, 3.60)])
        m = r["multipla"]
        self.assertIsNotNone(m)
        self.assertEqual(m["unita"], 1)
        self.assertAlmostEqual(m["quota_totale"], 2.10 * 3.60)
        self.assertAlmostEqual(m["prob_totale"], 0.5 * 0.3)
        self.assertEqual(len(set(m["partite"])), len(m["partite"]))
        self.assertLessEqual(r["unita_totali"], 3)

    def test_multipla_massimo_tre_eventi(self):
        cs = [cand(p, "1", 0.5, 2.1) for p in "ABCDE"]
        r = pu.seleziona_giocate(cs, tetto=10)
        self.assertEqual(len(r["multipla"]["eventi"]), 3)

    def test_bankroll_limita_le_unita(self):
        r = pu.seleziona_giocate([cand("A", "1", 0.55, 2.10), cand("B", "2", 0.5, 2.2)], bankroll=1.0)
        self.assertEqual(r["unita_totali"], 1)
        self.assertTrue(any("Bankroll" in m for m in r["messaggi"]))

    def test_importo_in_euro(self):
        r = pu.seleziona_giocate([cand("A", "1", 0.50, 2.10)], valore_unita=0.5)
        self.assertAlmostEqual(r["singole"][0]["importo"], 0.5)


if __name__ == "__main__":
    unittest.main()

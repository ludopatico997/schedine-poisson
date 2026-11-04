"""Test di nomi.py, fonte_quote.py e genera_consigli.py.  python3 -m unittest engine.test_consigli -v"""
import unittest

import numpy as np
import pandas as pd

from engine import fonte_quote as fq
from engine import genera_consigli as gc
from engine import nomi
from engine.test_dixon_coles import simula

SQUADRE = {
    "I1": ["Atalanta", "Inter", "Milan", "Verona", "Roma", "Napoli", "Juventus"],
    "E0": ["Man City", "Man United", "Nott'm Forest", "Wolves", "Tottenham", "Newcastle", "Leeds", "West Ham"],
    "SP1": ["Ath Madrid", "Ath Bilbao", "Betis", "Sociedad", "Vallecano", "Alaves", "Espanol", "Celta"],
    "F1": ["Paris SG", "Paris FC", "Marseille", "Lyon", "Monaco", "Rennes"],
    "D1": ["Leverkusen", "Dortmund", "M'gladbach", "Ein Frankfurt", "FC Koln", "Union Berlin", "Schalke 04", "Mainz"],
}


class TestNomi(unittest.TestCase):
    def test_alias_e_varianti_comuni(self):
        attesi = {
            "I1": {"Inter Milan": "Inter", "AC Milan": "Milan", "Hellas Verona": "Verona", "AS Roma": "Roma", "SSC Napoli": "Napoli"},
            "E0": {"Manchester City": "Man City", "Manchester United": "Man United", "Nottingham Forest": "Nott'm Forest",
                   "Wolverhampton Wanderers": "Wolves", "Tottenham Hotspur": "Tottenham", "Newcastle United": "Newcastle",
                   "Leeds United": "Leeds", "West Ham United": "West Ham"},
            "SP1": {"Atlético Madrid": "Ath Madrid", "Athletic Bilbao": "Ath Bilbao", "Real Betis": "Betis",
                    "Real Sociedad": "Sociedad", "Rayo Vallecano": "Vallecano", "Deportivo Alavés": "Alaves",
                    "RCD Espanyol": "Espanol", "Celta Vigo": "Celta"},
            "F1": {"Paris Saint-Germain": "Paris SG", "Paris FC": "Paris FC", "Olympique Marseille": "Marseille",
                   "Olympique Lyonnais": "Lyon", "AS Monaco": "Monaco", "Stade Rennais": "Rennes"},
            "D1": {"Bayer 04 Leverkusen": "Leverkusen", "Borussia Dortmund": "Dortmund", "Borussia Mönchengladbach": "M'gladbach",
                   "Eintracht Frankfurt": "Ein Frankfurt", "FC Köln": "FC Koln", "1. FC Union Berlin": "Union Berlin",
                   "FC Schalke 04": "Schalke 04", "FSV Mainz 05": "Mainz"},
        }
        for lega, coppie in attesi.items():
            for esterno, nostro in coppie.items():
                self.assertEqual(nomi.abbina(esterno, SQUADRE[lega]), nostro, f"{lega}: {esterno}")

    def test_sconosciuto_o_ambiguo(self):
        self.assertIsNone(nomi.abbina("Pippo United", SQUADRE["E0"]))
        self.assertIsNone(nomi.abbina("Manchester", ["Man City", "Man United"]))
        self.assertIsNone(nomi.abbina("Inter", []))


def risposta_api():
    def h2h(casa, ospite, a, b, c):
        return {"key": "h2h", "outcomes": [{"name": casa, "price": a}, {"name": ospite, "price": c}, {"name": "Draw", "price": b}]}

    def tot(over, under, punto=2.5):
        return {"key": "totals", "outcomes": [{"name": "Over", "price": over, "point": punto}, {"name": "Under", "price": under, "point": punto}]}

    def bm(chiave, mercati):
        return {"key": chiave, "title": chiave, "markets": mercati}

    return [
        {"home_team": "Inter Milan", "away_team": "AC Milan", "commence_time": "2026-11-08T19:45:00Z", "bookmakers": [
            bm("pinnacle", [h2h("Inter Milan", "AC Milan", 1.95, 3.6, 4.2), tot(1.9, 2.0)]),
            bm("altro", [h2h("Inter Milan", "AC Milan", 1.8, 3.4, 3.9)])]},
        {"home_team": "Roma", "away_team": "Napoli", "commence_time": "2026-11-09T19:45:00Z", "bookmakers": [
            bm("a", [h2h("Roma", "Napoli", 2.6, 3.2, 2.7), tot(2.0, 1.85)]),
            bm("b", [h2h("Roma", "Napoli", 2.7, 3.3, 2.6), tot(1.95, 1.9)]),
            bm("c", [h2h("Roma", "Napoli", 2.65, 3.25, 2.65), tot(1.9, 1.95, 3.5), ]),
            bm("d", [h2h("Roma", "Napoli", 2.62, 3.3, 2.68), tot(1.98, 1.88)])]},
        {"home_team": "Juventus", "away_team": "Verona", "commence_time": "2026-11-09T15:00:00Z", "bookmakers": [
            bm("a", [h2h("Juventus", "Verona", 1.4, 4.5, 8.0)]), bm("b", [h2h("Juventus", "Verona", 1.42, 4.4, 7.5)])]},  # solo 2 bookmaker
    ]


class TestFonteQuote(unittest.TestCase):
    def test_pinnacle_ha_la_precedenza(self):
        ev = fq.analizza_eventi(risposta_api())
        e0 = ev[0]
        self.assertEqual((e0["fonte"], e0["n_bookmaker"]), ("pinnacle", 1))
        m = e0["mercato"]
        self.assertAlmostEqual(m["1"] + m["X"] + m["2"], 1.0)
        self.assertAlmostEqual(m["Over 2.5"] + m["Under 2.5"], 1.0)
        self.assertGreater(m["1"], m["2"])

    def test_consenso_con_almeno_tre_bookmaker(self):
        ev = fq.analizza_eventi(risposta_api())
        self.assertEqual(len(ev), 2)            # la terza partita ha solo 2 bookmaker: scartata
        e1 = ev[1]
        self.assertEqual((e1["fonte"], e1["n_bookmaker"]), ("consenso", 4))
        m = e1["mercato"]
        self.assertAlmostEqual(m["1"] + m["X"] + m["2"], 1.0)
        self.assertAlmostEqual(m["Over 2.5"] + m["Under 2.5"], 1.0)   # il bookmaker 'c' quota la linea 3.5: ignorata
        self.assertAlmostEqual(m["1"], m["2"], delta=0.02)

    def test_senza_chiave_non_chiama_la_rete(self):
        with self.assertRaises(KeyError):
            fq.scarica_eventi("I1", api_key=None)   # ODDS_API_KEY assente nell'ambiente di test


class TestConsigli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        df, _, _ = simula(seed=11, n_squadre=8, stagioni=6, inizio="2024-08-20")
        df["campionato"] = "I1"
        df["stagione"] = "x"
        df["data"] = pd.to_datetime(df["data"])
        # squadre con nomi "esterni" mappabili: S00 -> Inter ... solo per il test
        cls.df = df
        cls.spec = {"modello": "ens", "parametri": {"k": 20.0, "vantaggio_casa": 40.0, "regressione": 0.05,
                                                    "peso_elo": 0.5, "dc": {"emivita_giorni": 270.0, "ridge": 3.0}}}
        cls.data_rif = df["data"].max() + pd.Timedelta(days=1)

    def evento(self, casa="S00", ospite="S01", mercato="auto"):
        if mercato == "auto":
            mercato = {"1": 0.45, "X": 0.27, "2": 0.28, "Over 2.5": 0.52, "Under 2.5": 0.48}
        return {"casa": casa, "ospite": ospite, "inizio": "2030-01-01T15:00:00Z", "mercato": mercato,
                "fonte": "test", "n_bookmaker": 5}

    def test_struttura_e_coerenza(self):
        out = gc.costruisci_consigli(self.df, {"I1": [self.evento()]}, self.spec, self.data_rif)
        self.assertEqual(len(out["partite"]), 1)
        p = out["partite"][0]
        pr = p["riferimento"]["probabilita"]
        self.assertAlmostEqual(pr["1"] + pr["X"] + pr["2"], 1.0, places=3)
        self.assertAlmostEqual(pr["GG"] + pr["NG"], 1.0, places=3)
        for nome in pr:
            self.assertGreater(p["riferimento"]["quota_minima"][nome], p["riferimento"]["quota_equa"][nome])
        # soglia piu' alta per i mercati senza quota di confronto
        self.assertGreater(p["riferimento"]["quota_minima"]["GG"] / p["riferimento"]["quota_equa"]["GG"], 1.07)
        self.assertLess(p["riferimento"]["quota_minima"]["1"] / p["riferimento"]["quota_equa"]["1"], 1.03)
        self.assertIn("avviso_gioco", out)
        self.assertEqual(out["parametri"]["soglie"]["valore_senza_mercato"], 0.08)

    def test_nessun_dato_sensibile_o_quote_bookmaker(self):
        import json
        testo = json.dumps(gc.costruisci_consigli(self.df, {"I1": [self.evento()]}, self.spec, self.data_rif))
        for vietato in ("bankroll", "apiKey", "ODDS_API_KEY"):
            self.assertNotIn(vietato, testo)

    def test_nome_non_riconosciuto_e_saltato_con_avviso(self):
        out = gc.costruisci_consigli(self.df, {"I1": [self.evento(casa="Squadra Inventata")]}, self.spec, self.data_rif)
        self.assertEqual(len(out["partite"]), 0)
        self.assertTrue(any("non riconosciuto" in a for a in out["avvisi"]))

    def test_senza_mercato_usa_il_modello(self):
        out = gc.costruisci_consigli(self.df, {"I1": [self.evento(mercato=None)]}, self.spec, self.data_rif)
        p = out["partite"][0]
        self.assertIsNone(p["mercato"])
        self.assertEqual(p["riferimento"]["fonte"], "modello")
        self.assertTrue(any("nessuna quota di mercato" in a for a in out["avvisi"]))
        self.assertGreater(p["riferimento"]["quota_minima"]["1"] / p["riferimento"]["quota_equa"]["1"], 1.07)

    def test_peso_modello_cambia_le_probabilita(self):
        a = gc.costruisci_consigli(self.df, {"I1": [self.evento()]}, self.spec, self.data_rif, peso_modello=0.0)
        b = gc.costruisci_consigli(self.df, {"I1": [self.evento()]}, self.spec, self.data_rif, peso_modello=1.0)
        self.assertNotEqual(a["partite"][0]["riferimento"]["probabilita"]["1"], b["partite"][0]["riferimento"]["probabilita"]["1"])


if __name__ == "__main__":
    unittest.main()

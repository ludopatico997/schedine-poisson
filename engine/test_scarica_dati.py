"""Test di scarica_dati.py con dati sintetici (nessun accesso alla rete).

Esecuzione:  python3 -m unittest engine.test_scarica_dati -v   (dalla radice del progetto)
"""
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from engine import scarica_dati as sd

INTESTAZIONE = ("Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HS,AS,HST,AST,"
                "PSCH,PSCD,PSCA,AvgCH,AvgCD,AvgCA,B365CH,B365CD,B365CA,"
                "PC>2.5,PC<2.5,AvgC>2.5,AvgC<2.5")
RIGHE = [
    # 0: tutte le fonti presenti -> Pinnacle; data a 4 cifre; nome con accento
    "I1,15/08/2025,18:30,Atalanta ,Roma,2,1,H,10,8,5,3,1.80,3.60,4.50,1.82,3.55,4.40,1.83,3.50,4.30,1.90,1.95,1.92,1.93",
    # 1: Pinnacle assente -> ripiego sulla media; data a 2 cifre; FTR incoerente (gol dicono pareggio)
    "I1,16/08/25,20:45,Inter,Napoli,1,1,H,12,9,4,4,,,,2.10,3.40,3.60,2.12,3.40,3.50,,,1.85,2.00",
    # 2: Pinnacle con quota non valida (0.5) e media assente -> Bet365; niente Under/Over
    "I1,17/08/2025,,Milan,Lazio,0,2,A,7,11,2,6,0.5,3.2,3.9,,,,1.60,3.90,5.50,,,,",
    # 3: partita non ancora giocata -> scartata
    "I1,01/12/2030,20:45,Juventus,Torino,,,,,,,,,,,,,,,,,,,,",
    # 4: duplicato della riga 0 (stesso giorno e squadre)
    "I1,15/08/2025,18:30,Atalanta,Roma,2,1,H,10,8,5,3,1.80,3.60,4.50,1.82,3.55,4.40,1.83,3.50,4.30,1.90,1.95,1.92,1.93",
    # 5: data illeggibile -> scartata con avviso
    "I1,boh,20:45,Bologna,Genoa,1,0,H,5,5,2,1,2.0,3.3,3.8,,,,,,,,,,",
    "",
    ",,,,,,,,,,,,,,,,,,,,,,,,",
]


def csv_sintetico() -> bytes:
    return ("\n".join([INTESTAZIONE] + RIGHE) + "\n").encode("latin-1")


class TestStagioni(unittest.TestCase):
    def test_codici(self):
        self.assertEqual(sd.codice_stagione(2025), "2526")
        self.assertEqual(sd.codice_stagione(1999), "9900")
        self.assertEqual(sd.etichetta_stagione(2025), "2025/26")

    def test_stagione_corrente(self):
        from datetime import date
        self.assertEqual(sd.stagione_corrente(date(2026, 11, 4)), 2026)
        self.assertEqual(sd.stagione_corrente(date(2027, 3, 1)), 2026)
        self.assertEqual(sd.stagione_corrente(date(2026, 6, 30)), 2025)
        self.assertEqual(sd.stagione_corrente(date(2026, 7, 1)), 2026)


class TestPulizia(unittest.TestCase):
    def setUp(self):
        grezzo, self.scartate = sd.leggi_csv(csv_sintetico())
        self.df, self.problemi = sd.pulisci(grezzo, 2025, "I1")
        self.df = self.df.drop_duplicates(subset=["campionato", "data", "casa", "ospite"])

    def test_righe_tenute(self):
        # restano 0, 1, 2 (3 non giocata, 4 duplicato, 5 data errata, ultime vuote)
        self.assertEqual(list(self.df["casa"]), ["Atalanta", "Inter", "Milan"])
        self.assertEqual(self.problemi["senza_risultato"], 1)
        self.assertEqual(self.problemi["data_non_valida"], 1)

    def test_date_e_esito(self):
        self.assertEqual(self.df["data"].dt.strftime("%Y-%m-%d").tolist(),
                         ["2025-08-15", "2025-08-16", "2025-08-17"])
        self.assertEqual(self.df["esito"].tolist(), ["H", "D", "A"])
        self.assertEqual(self.problemi["esito_incoerente"], 1)  # riga 1: FTR=H ma 1-1

    def test_fonti_1x2_chiusura(self):
        self.assertEqual(self.df["fonte_1x2_ch"].tolist(), ["pinnacle", "media", "bet365"])
        self.assertAlmostEqual(self.df.loc[0, "q1_ch"], 1.80)
        self.assertAlmostEqual(self.df.loc[1, "q1_ch"], 2.10)   # dalla media
        self.assertAlmostEqual(self.df.loc[2, "q1_ch"], 1.60)   # Pinnacle 0.5 scartata -> Bet365

    def test_fonti_over_under(self):
        self.assertEqual(self.df["fonte_ou_ch"].tolist(), ["pinnacle", "media", ""])
        self.assertTrue(pd.isna(self.df.loc[2, "over25_ch"]))

    def test_apertura_assente_ma_senza_errori(self):
        self.assertTrue(self.df["q1_ap"].isna().all())

    def test_tiri(self):
        self.assertEqual(self.df["tiri_casa"].tolist(), [10, 12, 7])

    def test_colonne_obbligatorie(self):
        with self.assertRaises(ValueError):
            sd.pulisci(pd.DataFrame({"Date": ["01/01/2025"]}), 2025, "I1")


class TestMargine(unittest.TestCase):
    def test_quote_con_margine_assurdo_scartate(self):
        df = pd.DataFrame({"PSCH": ["1.20"], "PSCD": ["1.20"], "PSCA": ["1.20"]})  # somma prob. = 2.5
        q, f = sd.estrai_quote(df, sd.FONTI_1X2_CH, ["a", "b", "c"])
        self.assertTrue(q.isna().all().all())
        self.assertEqual(f.iloc[0], "")


class TestMainOffline(unittest.TestCase):
    def test_pipeline_da_cache(self):
        with tempfile.TemporaryDirectory() as d:
            dati = Path(d)
            (dati / "raw").mkdir()
            (dati / "raw" / "2526_I1.csv").write_bytes(csv_sintetico())
            esito = sd.main(["--offline", "--da", "2025", "--a", "2025",
                             "--campionati", "I1", "--cartella-dati", str(dati)])
            self.assertEqual(esito, 0)
            partite = pd.read_csv(dati / "pulito" / "partite.csv")
            self.assertEqual(len(partite), 3)
            copertura = pd.read_csv(dati / "pulito" / "copertura_quote.csv")
            self.assertEqual(copertura.loc[0, "partite"], 3)
            self.assertAlmostEqual(copertura.loc[0, "quote_1x2_ch_%"], 100.0)

    def test_senza_dati_fallisce(self):
        with tempfile.TemporaryDirectory() as d:
            esito = sd.main(["--offline", "--da", "2025", "--a", "2025",
                             "--campionati", "I1", "--cartella-dati", d])
            self.assertEqual(esito, 1)


if __name__ == "__main__":
    unittest.main()

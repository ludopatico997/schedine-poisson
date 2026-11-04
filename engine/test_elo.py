"""Test di elo.py ed ensemble.py.  python3 -m unittest engine.test_elo -v"""
import unittest

import numpy as np
import pandas as pd

from engine.ensemble import Ensemble
from engine.elo import Elo, moltiplicatore_gol
from engine.test_dixon_coles import simula


class TestElo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df, cls.att, cls.dif = simula(seed=5, n_squadre=10, stagioni=30)
        cls.m = Elo(regressione=0.0).fit(cls.df)

    def test_moltiplicatore(self):
        self.assertEqual([moltiplicatore_gol(x) for x in (0, 1, -1, 2, -2)], [1.0, 1.0, 1.0, 1.5, 1.5])
        self.assertAlmostEqual(moltiplicatore_gol(3), 14 / 8)

    def test_rating_correlati_alla_forza_vera(self):
        vera = (self.att + self.dif)
        self.assertGreater(np.corrcoef(self.m.rating[vera.index], vera)[0, 1], 0.85)

    def test_regressione_positiva_su_differenza_rating(self):
        self.assertGreater(self.m.b, 0)

    def test_gol_attesi_coerenti_con_la_media(self):
        lam, mu, noti = self.m.tassi(self.m.squadre[0], self.m.squadre[1])
        self.assertTrue(noti)
        self.assertTrue(0.15 <= lam < 6 and 0.15 <= mu < 6)
        self.assertAlmostEqual((lam + mu), self.m.t_lega, delta=0.8)

    def test_probabilita_somma_uno_e_squadra_forte(self):
        vera = (self.att + self.dif).sort_values()
        debole, forte = vera.index[0], vera.index[-1]
        p = self.m.probabilita(forte, debole)
        self.assertAlmostEqual(p["p1"] + p["px"] + p["p2"], 1.0, places=9)
        self.assertGreater(p["p1"], p["p2"])
        self.assertGreater(p["p1"], self.m.probabilita(debole, forte)["p1"])

    def test_nessun_look_ahead(self):
        data = self.df["data"].iloc[300]
        m = Elo().fit(self.df, data_rif=data)
        self.assertEqual(m.n_partite, int((self.df["data"] < data).sum()))
        manomesso = self.df.copy()
        manomesso.loc[manomesso["data"] >= data, ["gol_casa", "gol_ospite"]] = [7, 0]
        m2 = Elo().fit(manomesso, data_rif=data)
        self.assertEqual(m.tassi("S00", "S01"), m2.tassi("S00", "S01"))

    def test_squadra_sconosciuta(self):
        p = self.m.probabilita("Neopromossa", self.m.squadre[0])
        self.assertFalse(p["squadre_note"])

    def test_regressione_a_inizio_stagione_riduce_la_dispersione(self):
        df = self.df.copy()
        df["stagione"] = (np.arange(len(df)) // 90).astype(str)   # 90 partite per "stagione"
        senza = Elo(regressione=0.0).fit(df)
        con = Elo(regressione=0.6).fit(df)
        self.assertLess(con.rating.std(), senza.rating.std())

    def test_poche_partite(self):
        with self.assertRaises(ValueError):
            Elo().fit(self.df.head(10))


class TestEnsemble(unittest.TestCase):
    def test_peso_estremi_e_somma(self):
        df, _, _ = simula(seed=2, n_squadre=8, stagioni=6)
        e0 = Ensemble(peso_elo=0.0).fit(df)
        e1 = Ensemble(peso_elo=1.0).fit(df)
        em = Ensemble(peso_elo=0.5).fit(df)
        a, b = e0.dc.squadre[0], e0.dc.squadre[1]
        self.assertEqual(e0.tassi(a, b)[:2], e0.dc.tassi(a, b)[:2])
        self.assertAlmostEqual(e1.tassi(a, b)[0], e1.elo.tassi(a, b)[0])
        lam_dc, lam_elo = em.dc.tassi(a, b)[0], em.elo.tassi(a, b)[0]
        self.assertAlmostEqual(em.tassi(a, b)[0], (lam_dc + lam_elo) / 2)
        p = em.probabilita(a, b)
        self.assertAlmostEqual(p["p1"] + p["px"] + p["p2"], 1.0, places=9)
        self.assertIn("rho", p)


if __name__ == "__main__":
    unittest.main()

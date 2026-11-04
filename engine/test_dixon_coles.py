"""Test di dixon_coles.py con dati simulati (nessun accesso alla rete).

Esecuzione:  python3 -m unittest engine.test_dixon_coles -v   (dalla radice del progetto)
"""
import unittest

import numpy as np
import pandas as pd
from scipy.optimize import approx_fprime

from engine import dixon_coles as dc


def simula(seed=0, n_squadre=10, stagioni=3, ha=0.30, rho=0.0, c=0.15, inizio="2022-08-20"):
    """Campionato simulato (andata e ritorno per `stagioni` stagioni) con forze note."""
    rng = np.random.default_rng(seed)
    nomi = [f"S{i:02d}" for i in range(n_squadre)]
    att = rng.normal(0, 0.25, n_squadre)
    dif = rng.normal(0, 0.25, n_squadre)
    righe, giorno = [], pd.Timestamp(inizio)
    for _ in range(stagioni):
        for i in range(n_squadre):
            for j in range(n_squadre):
                if i == j:
                    continue
                lam = np.exp(c + ha + att[i] - dif[j])
                mu = np.exp(c + att[j] - dif[i])
                righe.append((giorno, "T", nomi[i], nomi[j], rng.poisson(lam), rng.poisson(mu)))
                giorno += pd.Timedelta(days=2)
    df = pd.DataFrame(righe, columns=["data", "campionato", "casa", "ospite", "gol_casa", "gol_ospite"])
    return df, pd.Series(att, nomi), pd.Series(dif, nomi)


class TestFunzioneObiettivo(unittest.TestCase):
    def test_gradiente_analitico_uguale_a_quello_numerico(self):
        df, _, _ = simula(seed=1, n_squadre=6, stagioni=1)
        m = dc.DixonColes(ridge=0.7)
        squadre = sorted(set(df.casa))
        idx = {s: i for i, s in enumerate(squadre)}
        n = len(squadre)
        h, a = df.casa.map(idx).to_numpy(), df.ospite.map(idx).to_numpy()
        x, y = df.gol_casa.to_numpy(float), df.gol_ospite.to_numpy(float)
        w = m.pesi(df["data"], df["data"].max() + pd.Timedelta(days=1))
        chiuse = (np.arange(len(df)) % 3 == 0).astype(float)  # forza anche i casi a porte chiuse
        rng = np.random.default_rng(5)
        th = np.concatenate([[0.1, 0.25, 0.1, -0.08], rng.normal(0, 0.2, 2 * n)])
        f = lambda t: m._nll(t, h, a, x, y, w, chiuse, n)[0]  # noqa: E731
        g_num = approx_fprime(th, f, 1e-6)
        g_an = m._nll(th, h, a, x, y, w, chiuse, n)[1]
        np.testing.assert_allclose(g_an, g_num, rtol=1e-4, atol=1e-4)


class TestStima(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 30 stagioni simulate: con pochi dati la correlazione dipende troppo dal caso
        cls.df, cls.att, cls.dif = simula(seed=5, n_squadre=10, stagioni=30)
        cls.m = dc.DixonColes(emivita_giorni=1e9).fit(cls.df)  # emivita enorme = pesi uniformi

    def test_converge(self):
        self.assertTrue(self.m.convergenza, self.m.messaggio)

    def test_recupera_forze_vere(self):
        att_v, dif_v = self.att - self.att.mean(), self.dif - self.att.mean()
        self.assertGreater(np.corrcoef(self.m.att[att_v.index], att_v)[0, 1], 0.95)
        self.assertGreater(np.corrcoef(self.m.dif[dif_v.index], dif_v)[0, 1], 0.95)

    def test_recupera_vantaggio_casa_e_rho_nullo(self):
        self.assertAlmostEqual(self.m.ha, 0.30, delta=0.12)
        self.assertAlmostEqual(self.m.rho, 0.0, delta=0.12)

    def test_porte_chiuse_vicino_al_normale_senza_dati(self):
        # nessuna partita simulata nel periodo Covid: il ridge tiene ha_chiuse ~ ha
        self.assertAlmostEqual(self.m.ha_chiuse, self.m.ha, delta=0.02)

    def test_poche_partite_errore(self):
        with self.assertRaises(ValueError):
            dc.DixonColes().fit(self.df.head(10))

    def test_nessun_look_ahead(self):
        data = self.df["data"].iloc[200]
        m = dc.DixonColes().fit(self.df, data_rif=data)
        self.assertEqual(m.n_partite, int((self.df["data"] < data).sum()))


class TestPesi(unittest.TestCase):
    def test_emivita(self):
        m = dc.DixonColes(emivita_giorni=100)
        date = pd.Series(pd.to_datetime(["2025-01-01", "2024-09-23", "2024-06-15"]))
        w = m.pesi(date, pd.Timestamp("2025-01-01"))
        self.assertAlmostEqual(w[0], 1.0)
        self.assertAlmostEqual(w[1], 0.5, places=2)   # 100 giorni prima
        self.assertAlmostEqual(w[2], 0.25, places=1)  # circa 200 giorni prima


class TestPrevisione(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        df, _, _ = simula(seed=7, n_squadre=8, stagioni=4)
        cls.m = dc.DixonColes().fit(df)
        cls.s = cls.m.squadre

    def test_matrice_somma_uno(self):
        mat = self.m.matrice(self.s[0], self.s[1])
        self.assertAlmostEqual(mat.sum(), 1.0, places=9)
        self.assertTrue((mat >= 0).all())

    def test_probabilita_coerenti(self):
        p = self.m.probabilita(self.s[0], self.s[1])
        self.assertAlmostEqual(p["p1"] + p["px"] + p["p2"], 1.0, places=9)
        self.assertAlmostEqual(p["over25"] + p["under25"], 1.0, places=9)
        self.assertTrue(p["squadre_note"])

    def test_vantaggio_casa(self):
        a, b = self.s[0], self.s[1]
        self.assertGreater(self.m.tassi(a, b)[0] / self.m.tassi(b, a)[1], 1.0)  # a in casa segna piu' di a in trasferta

    def test_porte_chiuse_cambiano_il_tasso(self):
        self.m.ha_chiuse = self.m.ha - 0.2
        l_norm = self.m.tassi(self.s[0], self.s[1], porte_chiuse=False)[0]
        l_chiu = self.m.tassi(self.s[0], self.s[1], porte_chiuse=True)[0]
        self.assertAlmostEqual(l_chiu / l_norm, np.exp(-0.2), places=6)

    def test_squadra_sconosciuta_segnalata(self):
        p = self.m.probabilita("Neopromossa", self.s[0])
        self.assertFalse(p["squadre_note"])
        self.assertAlmostEqual(p["p1"] + p["px"] + p["p2"], 1.0, places=9)


class TestPorteChiuse(unittest.TestCase):
    def test_finestra(self):
        d = pd.Series(pd.to_datetime(["2020-05-15", "2020-05-16", "2021-01-10", "2021-06-30", "2021-07-01"]))
        self.assertEqual(dc.segna_porte_chiuse(d).tolist(), [0, 1, 1, 1, 0])


if __name__ == "__main__":
    unittest.main()

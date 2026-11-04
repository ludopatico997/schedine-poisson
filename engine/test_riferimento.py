"""Test di riferimento.py.  python3 -m unittest engine.test_riferimento -v"""
import unittest

from engine import riferimento as rf
from engine.dixon_coles import matrice_punteggi, mercati_base


def prob_da(lam, mu, rho):
    b = mercati_base(matrice_punteggi(lam, mu, rho))
    return {"1": b["p1"], "X": b["px"], "2": b["p2"], "Over 2.5": b["over25"], "Under 2.5": b["under25"]}


class TestAncoraggio(unittest.TestCase):
    def test_recupera_gol_attesi(self):
        p = prob_da(1.6, 1.0, -0.07)
        lam, mu, err = rf.lam_mu_da_mercato(p, rho=-0.07)
        self.assertAlmostEqual(lam, 1.6, places=2)
        self.assertAlmostEqual(mu, 1.0, places=2)
        self.assertLess(err, 1e-4)

    def test_solo_1x2_senza_under_over(self):
        p = prob_da(1.3, 1.3, -0.05)
        p.pop("Over 2.5"), p.pop("Under 2.5")
        lam, mu, err = rf.lam_mu_da_mercato(p, rho=-0.05)
        self.assertAlmostEqual(lam, mu, places=2)
        self.assertLess(err, 1e-3)

    def test_probabilita_mercato_da_quote(self):
        p = rf.probabilita_mercato(2.0, 4.0, 4.0, 1.9, 1.9)
        self.assertAlmostEqual(p["1"] + p["X"] + p["2"], 1.0)
        self.assertAlmostEqual(p["1"], 0.5)
        self.assertAlmostEqual(p["Over 2.5"], 0.5)


class TestRiferimento(unittest.TestCase):
    def setUp(self):
        self.mer = prob_da(1.8, 0.9, -0.07)
        self.mod = (1.2, 1.4)  # il modello vede la partita in modo diverso

    def test_peso_zero_e_uno(self):
        r0 = rf.riferimento(*self.mod, -0.07, self.mer, peso_modello=0.0)
        self.assertAlmostEqual(r0["lam"], 1.8, places=2)
        self.assertEqual(r0["fonte"], "mercato")
        r1 = rf.riferimento(*self.mod, -0.07, self.mer, peso_modello=1.0)
        self.assertAlmostEqual(r1["lam"], 1.2, places=9)
        self.assertAlmostEqual(r1["mu"], 1.4, places=9)

    def test_peso_intermedio_sta_in_mezzo(self):
        r = rf.riferimento(*self.mod, -0.07, self.mer, peso_modello=0.5)
        self.assertTrue(1.2 < r["lam"] < 1.8)

    def test_senza_mercato_usa_il_modello(self):
        r = rf.riferimento(*self.mod, -0.07, None)
        self.assertEqual(r["fonte"], "modello")
        self.assertIsNone(r["disaccordo"])
        self.assertAlmostEqual(r["probabilita"]["1"], r["prob_modello"]["1"])

    def test_disaccordo_e_tutti_i_mercati(self):
        r = rf.riferimento(*self.mod, -0.07, self.mer)
        self.assertGreater(r["disaccordo"], 0.1)  # 1.8-0.9 contro 1.2-1.4: molto diversi
        self.assertIn("Multigol 1-3", r["probabilita"])
        self.assertAlmostEqual(r["probabilita"]["GG"] + r["probabilita"]["NG"], 1.0)
        r_uguale = rf.riferimento(1.8, 0.9, -0.07, self.mer)
        self.assertLess(r_uguale["disaccordo"], 0.01)


class TestSemaforo(unittest.TestCase):
    def test_valore(self):
        self.assertAlmostEqual(rf.valore(0.48, 2.15), 0.032, places=3)
        self.assertAlmostEqual(rf.valore(0.48, 1.95), -0.064, places=3)

    def test_colori(self):
        self.assertEqual(rf.semaforo(-0.06, 0.02, True)[0], "rosso")
        self.assertEqual(rf.semaforo(0.03, 0.02, True)[0], "verde")
        self.assertEqual(rf.semaforo(0.03, 0.25, True)[0], "giallo")
        self.assertEqual(rf.semaforo(0.06, 0.02, False)[0], "rosso")   # senza mercato serve +8%
        self.assertEqual(rf.semaforo(0.09, 0.02, False)[0], "verde")
        self.assertEqual(rf.semaforo(0.03, None, True)[0], "verde")

    def test_scheda(self):
        mer = prob_da(1.8, 0.9, -0.07)
        r = rf.riferimento(1.8, 0.9, -0.07, mer)
        quota_equa_1 = 1 / r["probabilita"]["1"]
        s = rf.scheda(r, {"1": quota_equa_1 * 0.92, "X": 1 / r["probabilita"]["X"] * 1.10, "GG": 1 / r["probabilita"]["GG"] * 1.10})
        per = {x["mercato"]: x for x in s}
        self.assertEqual(per["1"]["semaforo"], "rosso")        # 8% sotto la quota equa
        self.assertEqual(per["X"]["semaforo"], "verde")        # 10% sopra, mercato diretto
        self.assertEqual(per["GG"]["semaforo"], "verde")       # +10% > 8% (senza mercato diretto)
        self.assertAlmostEqual(per["X"]["valore"], 0.10, places=6)
        self.assertGreater(per["1"]["quota_minima"], per["1"]["quota_equa"])


if __name__ == "__main__":
    unittest.main()

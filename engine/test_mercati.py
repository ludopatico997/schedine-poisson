"""Test di mercati.py.  python3 -m unittest engine.test_mercati -v"""
import unittest

import numpy as np

from engine import mercati as mk
from engine.dixon_coles import matrice_punteggi


class TestMercati(unittest.TestCase):
    def setUp(self):
        self.m = matrice_punteggi(1.5, 1.1, -0.05)
        self.t = mk.tutti_i_mercati(self.m)

    def test_coerenze(self):
        t = self.t
        self.assertAlmostEqual(t["1"] + t["X"] + t["2"], 1.0, places=9)
        self.assertAlmostEqual(t["1X"], t["1"] + t["X"])
        self.assertAlmostEqual(t["12"], 1 - t["X"])
        self.assertAlmostEqual(t["GG"] + t["NG"], 1.0)
        for linea in mk.LINEE_UO:
            self.assertAlmostEqual(t[f"Over {linea}"] + t[f"Under {linea}"], 1.0)
        self.assertLess(t["Over 3.5"], t["Over 2.5"])
        self.assertLess(t["Over 2.5"], t["Over 1.5"])

    def test_multigol_somma_di_tot(self):
        # Multigol 1-2 + 3-5 + gol 0 + gol 6+ = 1
        m = self.m
        i, j = np.indices(m.shape)
        tot = i + j
        s = self.t["Multigol 1-2"] + self.t["Multigol 3-5"] + m[tot == 0].sum() + m[tot >= 6].sum()
        self.assertAlmostEqual(s, 1.0, places=9)
        self.assertAlmostEqual(self.t["Multigol 1-3"], self.t["Multigol 1-2"] + m[tot == 3].sum())

    def test_gg_ng_con_matrice_nota(self):
        m = np.zeros((11, 11))
        m[0, 0], m[1, 1], m[2, 0] = 0.2, 0.5, 0.3   # NG, GG, NG
        t = mk.tutti_i_mercati(m)
        self.assertAlmostEqual(t["GG"], 0.5)
        self.assertAlmostEqual(t["1"], 0.3)
        self.assertAlmostEqual(t["Over 1.5"], 0.8)   # 1-1 (2 gol) e 2-0 (2 gol)
        self.assertAlmostEqual(t["Multigol 2-3"], 0.8)

    def test_esiti_reali_stessi_nomi(self):
        e = mk.esiti_reali(2, 1)
        self.assertEqual(set(e), set(self.t))
        self.assertEqual((e["1"], e["X"], e["2"], e["1X"], e["X2"], e["12"]), (1, 0, 0, 1, 0, 1))
        self.assertEqual((e["GG"], e["NG"], e["Over 2.5"], e["Under 2.5"], e["Multigol 1-3"], e["Multigol 4-5" if "Multigol 4-5" in e else "Multigol 3-5"]), (1, 0, 1, 0, 1, 1))
        z = mk.esiti_reali(0, 0)
        self.assertEqual((z["NG"], z["Under 0.5"], z["Multigol 1-2"]), (1, 1, 0))

    def test_margine_e_quote(self):
        np.testing.assert_allclose(mk.toglie_margine(np.array([2.0, 2.0])), [0.5, 0.5])
        self.assertAlmostEqual(mk.quota_equa(0.5), 2.0)
        self.assertAlmostEqual(mk.quota_minima_valore(0.5, 0.02), 2.04)


if __name__ == "__main__":
    unittest.main()

"""Test di walk_forward.py con dati simulati.  python3 -m unittest backtest.test_walk_forward -v"""
import unittest

import numpy as np
import pandas as pd

from backtest import walk_forward as wf
from engine.test_dixon_coles import simula


def partite_finte(seed=0, stagioni=6):
    df, _, _ = simula(seed=seed, n_squadre=8, stagioni=stagioni, inizio="2019-08-20")
    df["stagione"] = "x"
    df["esito"] = np.where(df.gol_casa > df.gol_ospite, "H", np.where(df.gol_casa < df.gol_ospite, "A", "D"))
    for c, v in (("q1", 2.4), ("qx", 3.4), ("q2", 3.2)):
        df[f"{c}_ch"] = v
        df[f"{c}_ap"] = v
    df["over25_ch"] = df["over25_ap"] = 1.95
    df["under25_ch"] = df["under25_ap"] = 1.95
    for c in ("fonte_1x2_ch", "fonte_ou_ch", "fonte_1x2_ap", "fonte_ou_ap"):
        df[c] = "pinnacle"
    return df


class TestNoLookAhead(unittest.TestCase):
    def test_cambiare_il_futuro_non_cambia_le_previsioni_passate(self):
        df = partite_finte()
        da, fino = df["data"].iloc[len(df) // 2], df["data"].iloc[-1]
        limite = da + pd.Timedelta(days=180)
        base = wf.previsioni(df, da, fino, blocco_giorni=30)

        manomesso = df.copy()
        futuro = manomesso["data"] >= limite
        manomesso.loc[futuro, ["gol_casa", "gol_ospite"]] = [9, 0]  # risultati futuri stravolti
        manomesso.loc[futuro, "esito"] = "H"
        nuovo = wf.previsioni(manomesso, da, fino, blocco_giorni=30)

        # previsioni delle partite iniziate prima di (limite - blocco) devono essere identiche
        sicuro = base["data"] < limite
        a = base[sicuro].reset_index(drop=True)
        b = nuovo[nuovo["data"] < limite].reset_index(drop=True)
        self.assertGreater(len(a), 50)
        np.testing.assert_allclose(a[["p1", "px", "p2", "over25"]], b[["p1", "px", "p2", "over25"]], atol=1e-12)

    def test_ogni_partita_prevista_una_volta_sola(self):
        df = partite_finte()
        da, fino = df["data"].iloc[100], df["data"].iloc[-1]
        pred = wf.previsioni(df, da, fino, blocco_giorni=17)
        attese = df[(df["data"] >= da) & (df["data"] <= fino)]
        self.assertEqual(len(pred), len(attese))
        self.assertFalse(pred.duplicated(["data", "casa", "ospite"]).any())

    def test_solo_partite_pinnacle(self):
        df = partite_finte()
        df.loc[df.index[::2], "fonte_1x2_ch"] = "media"
        da, fino = df["data"].iloc[100], df["data"].iloc[-1]
        pred = wf.previsioni(df, da, fino)
        self.assertTrue((pred["fonte_1x2_ch"] == "pinnacle").all())
        self.assertLess(len(pred), len(df[df["data"] >= da]))


class TestMetriche(unittest.TestCase):
    def test_logloss_e_brier_1x2(self):
        k = np.array([0, 1, 2])
        perfetto = np.eye(3)
        uniforme = np.full((3, 3), 1 / 3)
        self.assertAlmostEqual(wf.logloss_1x2(perfetto, k).mean(), 0.0, places=6)
        self.assertAlmostEqual(wf.logloss_1x2(uniforme, k).mean(), np.log(3), places=9)
        self.assertAlmostEqual(wf.brier_1x2(perfetto, k).mean(), 0.0)
        self.assertAlmostEqual(wf.brier_1x2(uniforme, k).mean(), 2 / 3, places=9)

    def test_binarie(self):
        self.assertAlmostEqual(wf.logloss_bin(np.array([0.5]), np.array([1.0]))[0], np.log(2), places=9)
        self.assertAlmostEqual(wf.brier_bin(np.array([0.8]), np.array([1.0]))[0], 0.04, places=9)

    def test_toglie_margine(self):
        p = wf.toglie_margine(np.array([[1.9, 3.5, 4.0], [2.0, 2.0, 2.0]]))
        np.testing.assert_allclose(p.sum(axis=1), [1, 1])
        np.testing.assert_allclose(p[1], [1 / 3] * 3)

    def test_metriche_complete_su_previsioni_simulate(self):
        df = partite_finte()
        pred = wf.previsioni(df, df["data"].iloc[200], df["data"].iloc[-1])
        m = wf.metriche(pred)
        # il modello deve fare meglio delle sole frequenze storiche su dati generati dal modello stesso
        self.assertLess(m["1x2_logloss"]["modello"], m["1x2_logloss"]["base"])
        cal = wf.calibrazione(pred, intervalli=5)
        self.assertEqual(int(cal["n"].sum()), 3 * m["1x2_logloss"]["n"])


class TestRoi(unittest.TestCase):
    def test_scommesse_e_tabella(self):
        P = np.array([[0.6, 0.2, 0.2], [0.2, 0.3, 0.5], [0.5, 0.3, 0.2]])
        Q = np.array([[2.0, 4.0, 4.0], [3.0, 3.5, 1.8], [1.5, 3.0, 5.0]])
        esito = np.array([0, 2, 1])
        edge, prof = wf.scommesse(P, Q, esito)
        self.assertAlmostEqual(edge[0], 0.6 * 2.0 - 1)           # scelta 1: 0.2
        self.assertAlmostEqual(edge[1], max(0.2 * 3 - 1, 0.3 * 3.5 - 1, 0.5 * 1.8 - 1))  # = 0.05 (pareggio)
        np.testing.assert_allclose(prof, [1.0, -1.0, -1.0])      # vince 1; 2a scelta X ma esce 2; 3a: 1 ma esce X
        t = wf.tabella_roi(edge, prof, soglie=[-1.0, 0.1])
        self.assertEqual(t.loc[0, "scommesse"], 3)
        self.assertAlmostEqual(t.loc[0, "ROI_%"], 100 * (-1 / 3), places=6)
        self.assertEqual(t.loc[1, "scommesse"], 1)


if __name__ == "__main__":
    unittest.main()

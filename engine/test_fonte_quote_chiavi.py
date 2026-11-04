import unittest

from engine.fonte_quote import CHIAVI_SPORT, chiavi_da_elenco


class TestChiavi(unittest.TestCase):
    def test_tutte_presenti(self):
        r = chiavi_da_elenco([{"key": k} for k in CHIAVI_SPORT.values()])
        self.assertTrue(all(r.values()))

    def test_una_mancante(self):
        elenco = [{"key": k} for c, k in CHIAVI_SPORT.items() if c != "F1"]
        r = chiavi_da_elenco(elenco)
        self.assertFalse(r["F1"])
        self.assertTrue(r["I1"])


if __name__ == "__main__":
    unittest.main()

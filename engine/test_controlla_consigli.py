import json
import unittest

from engine.controlla_consigli import controlla


def partita(p1=0.5, px=0.25, p2=0.25):
    return {"id": "x", "modello": {"lam": 1.4, "mu": 1.1}, "riferimento": {"probabilita": {"1": p1, "X": px, "2": p2}}}


def file(partite, avvisi=None):
    return json.dumps({"versione": 1, "partite": partite, "avvisi": avvisi or []})


class TestControlla(unittest.TestCase):
    def test_valido(self):
        self.assertEqual(controlla(file([partita()]))[0], "pubblica")

    def test_nessuna_partita_senza_errori_salta(self):
        self.assertEqual(controlla(file([]))[0], "salta")

    def test_nessuna_partita_con_quote_non_scaricate_e_errore(self):
        esito, err, _ = controlla(file([], ["Serie A: quote non scaricate (HTTPError)"]))
        self.assertEqual(esito, "errore")
        self.assertTrue(err)

    def test_una_lega_fallita_ma_altre_ok_pubblica_con_avviso(self):
        esito, err, av = controlla(file([partita()], ["Liga: quote non scaricate (HTTPError)"]))
        self.assertEqual((esito, err), ("pubblica", []))
        self.assertEqual(len(av), 1)

    def test_chiave_nel_testo_blocca(self):
        testo = file([partita()], ["errore apiKey=ABCDEF1234567890"])
        self.assertEqual(controlla(testo, "ABCDEF1234567890")[0], "errore")

    def test_chiave_corta_o_assente_ignorata(self):
        self.assertEqual(controlla(file([partita()]), "")[0], "pubblica")
        self.assertEqual(controlla(file([partita()]), "ab")[0], "pubblica")

    def test_json_rotto_e_struttura_errata(self):
        self.assertEqual(controlla("{non json")[0], "errore")
        self.assertEqual(controlla('{"a": 1}')[0], "errore")

    def test_probabilita_incoerenti(self):
        self.assertEqual(controlla(file([partita(0.9, 0.3, 0.3)]))[0], "errore")

    def test_campo_mancante(self):
        self.assertEqual(controlla(file([{"id": "x"}]))[0], "errore")


if __name__ == "__main__":
    unittest.main()

const test = require('node:test');
const assert = require('node:assert/strict');
const A = require('./archivio.js');

const ev = (partita, quota, prob, mercato) => ({ partita, etichetta: partita + ' ' + (mercato || '1'), mercato: mercato || '1', quota, prob });
const giorno = (iso) => new Date(iso + 'T12:00:00');

test('saldo: versamenti, puntate aperte, vincite, annullate', () => {
  const s = A.statoIniziale();
  A.versa(s, 30, '2026-11-01');
  assert.equal(A.saldo(s), 30);
  const g1 = A.registraGiocata(s, [ev('a', 2.0, 0.55)], 1, 1, giorno('2026-11-04'));
  const g2 = A.registraGiocata(s, [ev('b', 3.0, 0.4)], 2, 1, giorno('2026-11-04'));
  assert.equal(A.saldo(s), 27);
  A.impostaEsito(s, g1.id, 'vinta');
  assert.equal(A.saldo(s), 29);            // 30 - 1 - 2 + 2
  A.impostaEsito(s, g2.id, 'persa');
  assert.equal(A.saldo(s), 29);
  A.impostaEsito(s, g2.id, 'annullata');
  assert.equal(A.saldo(s), 31);            // la puntata torna indietro
  A.impostaEsito(s, g1.id, 'aperta');
  assert.equal(A.saldo(s), 29 + 0);        // 30 - 1 (aperta) = 29
});

test('profitto in unita\' e statistiche con valore atteso', () => {
  const s = A.statoIniziale();
  const a = A.registraGiocata(s, [ev('a', 2.0, 0.55)], 1, 1, giorno('2026-11-04'));
  const b = A.registraGiocata(s, [ev('b', 3.0, 0.40)], 2, 1, giorno('2026-11-04'));
  A.impostaEsito(s, a.id, 'vinta'); A.impostaEsito(s, b.id, 'persa');
  assert.equal(A.profittoUnita(a), 1);
  assert.equal(A.profittoUnita(b), -2);
  const st = A.statistiche(s);
  assert.equal(st.n_chiuse, 2);
  assert.equal(st.unita_giocate, 3);
  assert.equal(st.profitto_unita, -1);
  assert.ok(Math.abs(st.roi - (-1 / 3)) < 1e-12);
  assert.ok(Math.abs(st.atteso_unita - ((0.55 * 2 - 1) * 1 + (0.4 * 3 - 1) * 2)) < 1e-12);
  assert.ok(Math.abs(st.vinte_attese - 0.95) < 1e-12);
});

test('multipla: quota e probabilita\' sono il prodotto; giaGiocata vede tutte le partite', () => {
  const s = A.statoIniziale();
  const m = A.registraGiocata(s, [ev('a', 1.8, 0.6), ev('b', 2.0, 0.55)], 1, 1, giorno('2026-11-04'));
  assert.equal(m.tipo, 'multipla');
  assert.ok(Math.abs(m.quota - 3.6) < 1e-12);
  assert.ok(Math.abs(m.prob - 0.33) < 1e-12);
  assert.ok(A.giaGiocata(s, 'a') && A.giaGiocata(s, 'b') && !A.giaGiocata(s, 'c'));
  A.impostaEsito(s, m.id, 'annullata');
  assert.ok(!A.giaGiocata(s, 'a'));
});

test('unita\' di oggi e storico per la pausa', () => {
  const s = A.statoIniziale();
  A.registraGiocata(s, [ev('a', 2, 0.5)], 2, 1, giorno('2026-11-04'));
  const x = A.registraGiocata(s, [ev('b', 2, 0.5)], 1, 1, giorno('2026-11-04'));
  A.registraGiocata(s, [ev('c', 2, 0.5)], 1, 1, giorno('2026-11-03'));
  assert.equal(A.unitaOggi(s, '2026-11-04'), 3);
  A.impostaEsito(s, x.id, 'annullata');
  assert.equal(A.unitaOggi(s, '2026-11-04'), 2);
  const y = A.registraGiocata(s, [ev('d', 2, 0.5)], 1, 1, giorno('2026-11-04'));
  A.impostaEsito(s, y.id, 'persa');
  assert.deepEqual(A.storicoProfitti(s), [{ data: '2026-11-04', profitto_unita: -1 }]);
});

test('quote inserite: imposta, toglie se vuote, pulisce le partite vecchie', () => {
  const s = A.statoIniziale();
  A.impostaQuota(s, 'p1', '1', 2.1); A.impostaQuota(s, 'p1', 'X', 3.3); A.impostaQuota(s, 'p2', '1', 1.9);
  assert.deepEqual(s.quote.p1, { '1': 2.1, X: 3.3 });
  A.impostaQuota(s, 'p1', 'X', NaN);
  assert.deepEqual(s.quote.p1, { '1': 2.1 });
  A.impostaQuota(s, 'p1', '1', 0);
  assert.equal(s.quote.p1, undefined);
  A.pulisciQuote(s, ['p9']);
  assert.deepEqual(s.quote, {});
});

test('versamento del mese', () => {
  const s = A.statoIniziale();
  assert.equal(A.versatoNelMese(s, '2026-11'), false);
  A.versa(s, 30, '2026-11-02');
  assert.equal(A.versatoNelMese(s, '2026-11'), true);
  assert.equal(A.versatoNelMese(s, '2026-12'), false);
});

test('copia di sicurezza: esporta, importa, rifiuta file errati, ripara campi mancanti', () => {
  const s = A.statoIniziale();
  A.versa(s, 30, '2026-11-01');
  A.registraGiocata(s, [ev('a', 2, 0.5)], 1, 1, giorno('2026-11-04'));
  const r = A.importa(A.esporta(s));
  assert.equal(r.giocate.length, 1);
  assert.equal(A.saldo(r), A.saldo(s));
  assert.throws(() => A.importa('non json'));
  assert.throws(() => A.importa('{"x":1}'));
  const rotto = A.normalizza({ giocate: [{ stato: 'boh', eventi: [] }, null], impostazioni: { peso_modello: 0.3 } });
  assert.equal(rotto.giocate.length, 0);
  assert.equal(rotto.impostazioni.peso_modello, 0.3);
  assert.equal(rotto.impostazioni.valore_unita, 1);
  assert.deepEqual(A.normalizza(null), A.statoIniziale());
});

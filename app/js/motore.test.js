// Parita' col Python: i numeri di motore.js devono coincidere con quelli generati da engine/genera_fixture_js.py.
const test = require('node:test');
const assert = require('node:assert/strict');
const M = require('./motore.js');
const F = require('./fixture_parita.json');

const vicino = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg || ''} atteso ${b}, ottenuto ${a}`);
const confrontaMercati = (js, py, tol, etichetta) => {
  assert.deepEqual(Object.keys(js).sort(), Object.keys(py).sort(), 'stessi nomi di mercato');
  for (const k of Object.keys(py)) vicino(js[k], py[k], tol, `${etichetta} ${k}:`);
};

test('matrice e tutti i mercati coincidono col Python (1e-9)', () => {
  for (const c of F.matrici) {
    const m = M.matricePunteggi(c.lam, c.mu, c.rho);
    vicino(m.flat().reduce((s, v) => s + v, 0), 1, 1e-12, 'somma matrice');
    confrontaMercati(M.tuttiIMercati(m), c.mercati, 1e-9, `lam=${c.lam}`);
  }
});

test('gol attesi dal mercato: stesse probabilita\' e gol attesi vicini a scipy', () => {
  for (const a of F.ancoraggi) {
    const k = M.lamMuDaMercato(a.p, a.rho);
    vicino(k.lam, a.lam, 2e-3, 'lam');
    vicino(k.mu, a.mu, 2e-3, 'mu');
    vicino(k.residuo, a.residuo, 2e-3, 'residuo');
    const b = M.mercatiBase(M.matricePunteggi(k.lam, k.mu, a.rho));
    vicino(b.p1, a.p['1'], 0.02); vicino(b.p2, a.p['2'], 0.02);
  }
});

test('riferimento (mercato + modello) coincide col Python', () => {
  for (const r of F.riferimenti) {
    const rif = M.riferimento(r.lam_mod, r.mu_mod, r.rho, r.mercato, r.peso);
    vicino(rif.lam, r.lam, 3e-3, 'lam'); vicino(rif.mu, r.mu, 3e-3, 'mu');
    if (r.disaccordo === null) assert.equal(rif.disaccordo, null);
    else vicino(rif.disaccordo, r.disaccordo, 1e-9, 'disaccordo');
    confrontaMercati(rif.probabilita, r.probabilita, 3e-3, `peso=${r.peso}`);
  }
});

test('ancoraggio precalcolato dà lo stesso risultato', () => {
  const r = F.riferimenti[1];
  const k = M.lamMuDaMercato(r.mercato, r.rho);
  const a = M.riferimento(r.lam_mod, r.mu_mod, r.rho, r.mercato, 0.3);
  const b = M.riferimento(r.lam_mod, r.mu_mod, r.rho, r.mercato, 0.3, { ancoraggio: k });
  vicino(a.probabilita['1'], b.probabilita['1'], 1e-12);
});

test('scheda: valore, quota minima, semaforo e "diretto" coincidono col Python', () => {
  for (const s of F.schede) {
    const rif = M.riferimento(s.lam_mod, s.mu_mod, s.rho, s.mercato, s.peso);
    const righe = M.scheda(rif, s.quote);
    assert.equal(righe.length, s.righe.length);
    righe.forEach((r) => {
      const py = s.righe.find((x) => x.mercato === r.mercato);
      assert.ok(py, `mercato ${r.mercato} presente nel Python`);
      assert.equal(r.diretto, py.diretto, `diretto ${r.mercato}`);
      vicino(r.valore, py.valore, 5e-3, `valore ${r.mercato}`);
      vicino(r.quota_minima, py.quota_minima, 0.02, `quota minima ${r.mercato}`);
      // il colore puo' differire solo se il valore e' a cavallo di una soglia: ammesso entro la tolleranza
      if (r.semaforo !== py.semaforo) {
        const soglia = py.diretto ? 0.02 : 0.08;
        assert.ok(Math.abs(py.valore - soglia) < 6e-3 || Math.abs((rif.disaccordo || 0) - 0.10) < 1e-3, `semaforo ${r.mercato}: ${r.semaforo} vs ${py.semaforo}`);
      }
    });
  }
});

test('selezione delle giocate coincide col Python', () => {
  for (const c of F.selezione) {
    const o = c.opzioni;
    const s = M.selezionaGiocate(c.candidati, { valore_unita: o.valore_unita, bankroll: o.bankroll, perdita_settimana: o.perdita_settimana, tetto: o.tetto });
    assert.equal(s.stato, c.stato);
    assert.deepEqual(s.singole.map((x) => [x.etichetta, x.unita, x.importo]), c.singole.map((x) => [x.etichetta, x.unita, x.importo]));
    assert.equal(s.unita_totali, c.unita_totali);
    if (c.multipla) {
      assert.deepEqual(s.multipla.eventi, c.multipla.eventi);
      vicino(s.multipla.quota_totale, c.multipla.quota_totale, 1e-9);
      vicino(s.multipla.prob_totale, c.multipla.prob_totale, 1e-9);
    } else assert.equal(s.multipla, null);
  }
});

test('perdita degli ultimi giorni', () => {
  const p = F.perdita;
  vicino(M.perditaUltimiGiorni(p.storico, p.oggi), p.valore, 1e-12);
  vicino(M.perditaUltimiGiorni(p.storico, p.oggi, 3), p.valore_3gg, 1e-12);
});

test('toglie margine, quote equa e minima, kelly, unita\'', () => {
  const p = M.togliMargine([2, 3.5, 4]);
  vicino(p.reduce((s, v) => s + v, 0), 1, 1e-12);
  vicino(M.quotaEqua(0.5), 2, 1e-12);
  vicino(M.quotaMinimaValore(0.5, 0.02), 2.04, 1e-12);
  vicino(M.kelly(0.5, 2.2), 0.1 / 1.2, 1e-12);
  assert.equal(M.kelly(0.4, 2.0), 0);
  assert.equal(M.unitaSingola(0.07, 2.0, true), 2);
  assert.equal(M.unitaSingola(0.07, 4.0, true), 1);
  assert.equal(M.unitaSingola(0.07, 2.0, false), 1);
});

test('formattazione percentuali all\'italiana', () => {
  assert.equal(M.pc(0.0412, 1, true), '+4,1%');
  assert.equal(M.pc(-0.02, 1, true), '-2,0%');
  assert.equal(M.pc(0.1, 0), '10%');
});

// Test: node --test app/js/parser_quote.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const P = require('./parser_quote.js');

test('una riga per partita, virgola o punto decimale', () => {
  const r = P.estrai('Juventus - Torino 1.45 4,20 7.00');
  assert.deepEqual(r, [{ casa: 'Juventus', ospite: 'Torino', quote: [1.45, 4.2, 7.0] }]);
});

test('quote su righe separate e rumore (campionato, orario, +mercati)', () => {
  const t = 'Serie A\nOggi 20:45\nInter - Napoli  +245\n1,80\n3,40\n4,50\n\nMilan – Roma  04/11\n2,10 3,30 3,50';
  const r = P.estrai(t);
  assert.equal(r.length, 2);
  assert.deepEqual(r[0], { casa: 'Inter', ospite: 'Napoli', quote: [1.8, 3.4, 4.5] });
  assert.deepEqual(r[1], { casa: 'Milan', ospite: 'Roma', quote: [2.1, 3.3, 3.5] });
});

test('formato con nomi in mezzo alle quote', () => {
  const r = P.estrai('Inter 1,80 X 3,40 Napoli 4,50');
  assert.deepEqual(r, [{ casa: 'Inter', ospite: 'Napoli', quote: [1.8, 3.4, 4.5] }]);
});

test('solo numeri: partita singola senza nomi', () => {
  assert.deepEqual(P.estrai('1,85 3,50 4,20'), [{ casa: null, ospite: null, quote: [1.85, 3.5, 4.2] }]);
});

test('la linea Under/Over 2,5 non e\' una quota', () => {
  const r = P.estrai('Inter - Napoli\nUnder 2,5 1,95  Over 2,5 1,85');
  assert.deepEqual(r[0].quote, [1.95, 1.85]);
  const a = P.assegna(r[0].quote, 'UO');
  assert.deepEqual(a.quote, { 'Under 2.5': 1.95, 'Over 2.5': 1.85 });
});

test('percentuali e orari con punto dopo "ore" ignorati', () => {
  const r = P.estrai('Lazio - Genoa ore 20.45 45,5% 2,20 3,10 3,40');
  assert.deepEqual(r[0].quote, [2.2, 3.1, 3.4]);
});

test('assegna 1X2 con margine plausibile e avviso su ordine/mercato sbagliato', () => {
  const ok = P.assegna([1.8, 3.4, 4.5], '1X2');
  assert.equal(ok.ok, true);
  assert.deepEqual(ok.quote, { '1': 1.8, 'X': 3.4, '2': 4.5 });
  assert.equal(ok.avvisi.length, 0);
  const strano = P.assegna([2.0, 2.0, 2.0], '1X2');
  assert.ok(strano.avvisi.some((a) => a.includes('margine anomalo')));
  const troppe = P.assegna([1.8, 3.4, 4.5, 1.9, 1.9], '1X2');
  assert.ok(troppe.avvisi.some((a) => a.includes('prime 3')));
});

test('troppo poche quote', () => {
  const r = P.assegna([1.8, 3.4], '1X2');
  assert.equal(r.ok, false);
});

test('doppia chance: ordine 1X, 12, X2 (modificabile)', () => {
  const d = P.assegna([1.25, 1.30, 1.90], 'DC');
  assert.deepEqual(d.quote, { '1X': 1.25, '12': 1.3, 'X2': 1.9 });
  const d2 = P.assegna([1.25, 1.90, 1.30], 'DC', { ordine: ['1X', 'X2', '12'] });
  assert.deepEqual(d2.quote, { '1X': 1.25, 'X2': 1.9, '12': 1.3 });
});

test('GG/NG', () => {
  assert.deepEqual(P.assegna([1.75, 1.95], 'GGNG').quote, { GG: 1.75, NG: 1.95 });
});

test('multigol: etichetta e quota', () => {
  const m = P.leggiMultigol('1-3 1,70\n2-4 1,95 | 2-5 1,60\nMultigol 3-6   2.40');
  assert.deepEqual(m, { 'Multigol 1-3': 1.7, 'Multigol 2-4': 1.95, 'Multigol 2-5': 1.6, 'Multigol 3-6': 2.4 });
});

test('abbinamento nomi squadre', () => {
  const nostri = ['Inter', 'Milan', 'Man City', 'Man United', 'Ath Madrid', 'Ein Frankfurt', 'Leverkusen', 'Paris SG', 'Napoli', 'Roma', 'Lazio'];
  assert.equal(P.abbina('Internazionale', nostri).nome, 'Inter');
  assert.equal(P.abbina('Manchester City', nostri).nome, 'Man City');
  assert.equal(P.abbina('Manchester United FC', nostri).nome, 'Man United');
  assert.equal(P.abbina('Atletico Madrid', nostri).nome, 'Ath Madrid');
  assert.equal(P.abbina('Eintracht Francoforte', nostri).nome, 'Ein Frankfurt');
  assert.equal(P.abbina('Bayer 04 Leverkusen', nostri).nome, 'Leverkusen');
  assert.equal(P.abbina('Paris Saint-Germain', nostri).nome, 'Paris SG');
  assert.equal(P.abbina('SSC Napoli', nostri).nome, 'Napoli');
  assert.equal(P.abbina('AS Roma', nostri).nome, 'Roma');
});

test('nome sconosciuto: nessun abbinamento automatico, candidati proposti', () => {
  const r = P.abbina('Pippo Calcio', ['Inter', 'Milan', 'Roma']);
  assert.equal(r.nome, null);
  assert.equal(r.candidati.length, 3);
});

test('Man City e Man United non si confondono con "Man"', () => {
  const r = P.abbina('Manchester', ['Man City', 'Man United']);
  assert.equal(r.nome, null);   // ambiguo: va chiesto all'utente
});

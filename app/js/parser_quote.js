/* Passo 4 / opzione 2 - "Incolla e leggi": legge le quote copiate dalla pagina del bookmaker.
 * Nessun collegamento ai siti: lavora solo sul testo incollato dall'utente.
 * Funziona nel browser (window.ParserQuote) e in Node (require) per i test.
 *
 *   estrai(testo)                     -> [{casa, ospite, quote:[numeri]}]  (nomi null se il testo ha solo numeri)
 *   assegna(quote, mercato, opzioni)  -> {ok, quote:{"1":..}, avvisi:[]}
 *   leggiMultigol(testo)              -> {"Multigol 1-3": 1.7, ...}
 *   abbina(nome, elenco)              -> {nome, punteggio, candidati}   (nome squadra del bookmaker -> nostro nome)
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.ParserQuote = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const QUOTA_MIN = 1.01, QUOTA_MAX = 1000;
  const RE_QUOTA = /(?<![\d.,:/])(\d{1,3}[.,]\d{1,3})(?![\d]|[.,]\d)/g;
  const RE_SEP = /^(.+?)\s*(?:\s[-–—]\s|[-–—]|\bvs\.?\b|\bv\b)\s*(.+)$/i;
  const RE_INTERCALATO = /^(.+?)\s+(\d{1,3}[.,]\d{1,3})\s+(?:x|pareggio|pari|draw)\s+(\d{1,3}[.,]\d{1,3})\s+(.+?)\s+(\d{1,3}[.,]\d{1,3})$/i;

  const num = (s) => parseFloat(String(s).replace(',', '.'));

  /** Toglie dal testo ciò che sembra una quota ma non lo è (linee Under/Over, percentuali, orari). */
  function pulisciRiga(riga) {
    return riga
      .replace(/ /g, ' ')
      .replace(/\b(?:under|over|u|o)(?:\s*\/\s*(?:under|over|u|o))?\s*\d[.,][05]\b/gi, ' ')   // Over 2,5
      .replace(/\b\d+(?:[.,]\d+)?\s*%/g, ' ')                                                 // 45,5%
      .replace(/\bore\s*\d{1,2}[.:]\d{2}\b/gi, ' ')                                           // ore 20.45
      .replace(/\b\d{1,2}:\d{2}\b/g, ' ')                                                     // 20:45
      .replace(/\b\d{1,2}\/\d{1,2}(?:\/\d{2,4})?\b/g, ' ');                                   // 04/11
  }

  function quoteDi(riga) {
    const trovate = [];
    for (const m of pulisciRiga(riga).matchAll(RE_QUOTA)) {
      const v = num(m[1]);
      if (v >= QUOTA_MIN && v <= QUOTA_MAX) trovate.push(v);
    }
    return trovate;
  }

  function soloTesto(riga) {
    return pulisciRiga(riga).replace(RE_QUOTA, ' ').replace(/[+]\s*\d+/g, ' ').replace(/\s+/g, ' ').trim();
  }

  const haLettere = (s) => (s.match(/[A-Za-zÀ-ÿ]/g) || []).length >= 2;

  function estrai(testo) {
    const righe = String(testo || '').split(/\r?\n/).map((r) => r.trim()).filter(Boolean);
    const partite = [];
    let corrente = null;
    for (const riga of righe) {
      const inter = riga.match(RE_INTERCALATO);
      if (inter) {                                   // "Inter 1,80 X 3,40 Napoli 4,50"
        partite.push({ casa: inter[1].trim(), ospite: inter[4].trim(), quote: [num(inter[2]), num(inter[3]), num(inter[5])] });
        corrente = null;
        continue;
      }
      const q = quoteDi(riga);
      const t = soloTesto(riga);
      const sep = t.match(RE_SEP);
      if (sep && haLettere(sep[1]) && haLettere(sep[2])) {      // nuova partita: "Inter - Napoli"
        corrente = { casa: sep[1].trim(), ospite: sep[2].trim(), quote: q.slice() };
        partite.push(corrente);
      } else if (q.length) {
        if (!corrente) { corrente = { casa: null, ospite: null, quote: [] }; partite.push(corrente); }
        corrente.quote.push(...q);
      }
    }
    return partite.filter((p) => p.quote.length);
  }

  const MODELLI = {
    '1X2': { n: 3, nomi: ['1', 'X', '2'] },
    'DC': { n: 3, nomi: ['1X', '12', 'X2'] },                // ordine tipico dei siti italiani
    'UO': { n: 2, nomi: ['Under', 'Over'] },
    'GGNG': { n: 2, nomi: ['GG', 'NG'] },
  };

  /** Assegna i numeri trovati ai nomi dei mercati. opzioni: {ordine:[...], linea:2.5} */
  function assegna(quote, mercato, opzioni) {
    const opt = opzioni || {};
    const m = MODELLI[mercato];
    if (!m) return { ok: false, quote: {}, avvisi: ['mercato non supportato: ' + mercato] };
    const nomi = opt.ordine || m.nomi;
    const avvisi = [];
    if (quote.length < m.n) return { ok: false, quote: {}, avvisi: [`servono ${m.n} quote, trovate ${quote.length}`] };
    if (quote.length > m.n) avvisi.push(`trovate ${quote.length} quote: uso le prime ${m.n}`);
    const out = {};
    nomi.forEach((nome, i) => {
      const chiave = mercato === 'UO' ? `${nome} ${opt.linea || 2.5}` : nome;
      out[chiave] = quote[i];
    });
    const usate = quote.slice(0, m.n);
    if (mercato === '1X2' || mercato === 'UO' || mercato === 'GGNG') {
      const somma = usate.reduce((s, x) => s + 1 / x, 0);
      if (somma < 1.0 || somma > 1.3) avvisi.push(`margine anomalo (${((somma - 1) * 100).toFixed(1)}%): ordine o mercato sbagliato?`);
    }
    return { ok: true, quote: out, avvisi };
  }

  /** "1-3 1,70 | 2-4 1,95 ..." -> {"Multigol 1-3": 1.7, ...} */
  function leggiMultigol(testo) {
    const out = {};
    const re = /(?<!\d)(\d)\s*[-–]\s*(\d)(?!\d)\D{0,6}?(\d{1,3}[.,]\d{1,3})/g;
    for (const m of String(testo || '').matchAll(re)) {
      const v = num(m[3]);
      if (v >= QUOTA_MIN && v <= QUOTA_MAX && Number(m[1]) < Number(m[2])) out[`Multigol ${m[1]}-${m[2]}`] = v;
    }
    return out;
  }

  // ---- abbinamento dei nomi delle squadre -------------------------------------------------
  const ALIAS = {
    'paris sg': 'paris saint germain', 'psg': 'paris saint germain', 'internazionale': 'inter',
    'atletico madrid': 'ath madrid', 'athletic bilbao': 'ath bilbao', 'athletic club': 'ath bilbao',
    'borussia monchengladbach': 'mgladbach', 'gladbach': 'mgladbach', 'eintracht francoforte': 'ein frankfurt',
    'eintracht frankfurt': 'ein frankfurt', 'bayern monaco': 'bayern munich', 'bayern munchen': 'bayern munich',
    'manchester united': 'man united', 'manchester city': 'man city', 'newcastle united': 'newcastle',
    'tottenham hotspur': 'tottenham', 'real sociedad': 'sociedad', 'celta vigo': 'celta',
  };
  const VUOTE = new Set(['fc', 'ac', 'as', 'ssc', 'us', 'cf', 'sc', 'cfc', 'calcio', 'afc', 'rc', 'ud', 'sd', 'ca', 'cd', 'sv', 'vfb', 'vfl', 'tsg', 'fsv', 'fk', 'of', '1909', '1913', '1899', '1900', '1907', '1927']);

  function normalizza(nome) {
    let s = String(nome || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/['’`.]/g, '').replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
    if (ALIAS[s]) s = ALIAS[s];
    const tok = s.split(' ').filter((t) => t && !VUOTE.has(t));
    return (tok.length ? tok : s.split(' ')).join(' ');
  }

  function bigrammi(s) {
    const t = s.replace(/ /g, '');
    const b = new Map();
    for (let i = 0; i < t.length - 1; i++) { const g = t.slice(i, i + 2); b.set(g, (b.get(g) || 0) + 1); }
    return b;
  }

  function dice(a, b) {
    const A = bigrammi(a), B = bigrammi(b);
    let inter = 0, na = 0, nb = 0;
    A.forEach((v) => { na += v; });
    B.forEach((v) => { nb += v; });
    A.forEach((v, g) => { if (B.has(g)) inter += Math.min(v, B.get(g)); });
    return na + nb ? (2 * inter) / (na + nb) : 0;
  }

  function punteggio(a, b) {
    const x = normalizza(a), y = normalizza(b);
    if (!x || !y) return 0;
    if (x === y) return 1;
    const tx = x.split(' '), ty = y.split(' ');
    const [corti, lunghi] = tx.length <= ty.length ? [tx, ty] : [ty, tx];
    // ogni parola della versione corta e' l'inizio di una parola di quella lunga ("man" / "manchester")
    const prefissi = corti.every((c) => c.length >= 3 && lunghi.some((l) => l.startsWith(c)));
    return Math.max(dice(x, y), prefissi ? 0.9 : 0);
  }

  /** Cerca nell'elenco dei nostri nomi il piu' simile. Sotto soglia -> nome null (chiedere all'utente). */
  function abbina(nome, elenco, soglia) {
    const min = soglia === undefined ? 0.6 : soglia;
    const classifica = elenco.map((e) => ({ nome: e, punteggio: punteggio(nome, e) }))
      .sort((p, q) => q.punteggio - p.punteggio);
    const migliore = classifica[0];
    const pari = classifica.length > 1 && classifica[1].punteggio >= migliore.punteggio - 0.02;
    return {
      nome: migliore && migliore.punteggio >= min && !pari ? migliore.nome : null,
      punteggio: migliore ? migliore.punteggio : 0,
      candidati: classifica.slice(0, 3),
    };
  }

  return { estrai, assegna, leggiMultigol, abbina, normalizza, punteggio };
});

/* Passo 8 - Dati dell'utente: impostazioni, quote inserite, giocate, versamenti.
 * Restano SOLO nel browser del telefono (localStorage): nessun invio a server, nessun dato nel repository.
 * Qui c'e' solo la logica (funzioni pure sullo stato); il salvataggio e' in app.js.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Archivio = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const VERSIONE = 1;
  const STATI = ['aperta', 'vinta', 'persa', 'annullata'];

  function statoIniziale() {
    return {
      v: VERSIONE,
      impostazioni: { valore_unita: 1, budget_mensile: 30, peso_modello: 0.10 },
      quote: {},
      giocate: [],
      versamenti: [],
    };
  }

  const nuovoId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  const arrotonda = (x) => Math.round(x * 100) / 100;

  /** Ripara uno stato letto dal disco (campi mancanti, versioni vecchie): non lancia mai. */
  function normalizza(s) {
    const base = statoIniziale();
    const o = s && typeof s === 'object' ? s : {};
    return {
      v: VERSIONE,
      impostazioni: Object.assign(base.impostazioni, o.impostazioni && typeof o.impostazioni === 'object' ? o.impostazioni : {}),
      quote: o.quote && typeof o.quote === 'object' ? o.quote : {},
      giocate: Array.isArray(o.giocate) ? o.giocate.filter((g) => g && STATI.includes(g.stato) && Array.isArray(g.eventi)) : [],
      versamenti: Array.isArray(o.versamenti) ? o.versamenti.filter((v) => v && typeof v.importo === 'number') : [],
    };
  }

  // ---------------------------------------------------------------- quote inserite
  function impostaQuota(stato, partita, mercato, quota) {
    if (!(quota > 1)) {                       // vuoto o non valido: si toglie
      if (stato.quote[partita]) {
        delete stato.quote[partita][mercato];
        if (!Object.keys(stato.quote[partita]).length) delete stato.quote[partita];
      }
      return stato;
    }
    (stato.quote[partita] = stato.quote[partita] || {})[mercato] = quota;
    return stato;
  }

  /** Toglie le quote di partite che non sono piu' nei consigli (il browser non si riempie di dati vecchi). */
  function pulisciQuote(stato, idAttivi) {
    const attivi = new Set(idAttivi);
    for (const id of Object.keys(stato.quote)) if (!attivi.has(id)) delete stato.quote[id];
    return stato;
  }

  // ---------------------------------------------------------------- giocate
  /** eventi: [{partita, etichetta, mercato, quota, prob}]. Una sola riga = singola, piu' righe = multipla. */
  function registraGiocata(stato, eventi, unita, valoreUnita, quando) {
    const t = quando || new Date();
    const data = [t.getFullYear(), String(t.getMonth() + 1).padStart(2, '0'), String(t.getDate()).padStart(2, '0')].join('-');
    const g = {
      id: nuovoId(), creata: t.toISOString(), data, tipo: eventi.length > 1 ? 'multipla' : 'singola',
      unita, valore_unita: valoreUnita, importo: arrotonda(unita * valoreUnita),
      quota: eventi.reduce((p, e) => p * e.quota, 1), prob: eventi.reduce((p, e) => p * e.prob, 1),
      stato: 'aperta', chiusa: null, eventi: eventi.map((e) => ({ partita: e.partita, etichetta: e.etichetta, mercato: e.mercato, quota: e.quota, prob: e.prob })),
    };
    stato.giocate.push(g);
    return g;
  }

  function impostaEsito(stato, id, nuovoStato, quando) {
    const g = stato.giocate.find((x) => x.id === id);
    if (!g || !STATI.includes(nuovoStato)) return null;
    g.stato = nuovoStato;
    g.chiusa = nuovoStato === 'aperta' ? null : (quando || new Date()).toISOString();
    return g;
  }

  const eliminaGiocata = (stato, id) => { stato.giocate = stato.giocate.filter((g) => g.id !== id); return stato; };

  /** Profitto in unita': vinta (quota-1)*unita, persa -unita, aperta/annullata 0. */
  function profittoUnita(g) {
    if (g.stato === 'vinta') return (g.quota - 1) * g.unita;
    if (g.stato === 'persa') return -g.unita;
    return 0;
  }

  const giaGiocata = (stato, partita) =>
    stato.giocate.some((g) => g.stato !== 'annullata' && g.eventi.some((e) => e.partita === partita));

  const unitaOggi = (stato, oggi) =>
    stato.giocate.filter((g) => g.data === oggi && g.stato !== 'annullata').reduce((s, g) => s + g.unita, 0);

  /** Righe {data, profitto_unita} delle giocate chiuse: serve a Motore.perditaUltimiGiorni. */
  const storicoProfitti = (stato) =>
    stato.giocate.filter((g) => g.stato === 'vinta' || g.stato === 'persa').map((g) => ({ data: g.data, profitto_unita: profittoUnita(g) }));

  // ---------------------------------------------------------------- bankroll
  function versa(stato, importo, data, nota) {
    stato.versamenti.push({ id: nuovoId(), data, importo: arrotonda(importo), nota: nota || '' });
    return stato;
  }

  const versatoNelMese = (stato, mese) => stato.versamenti.some((v) => v.data.slice(0, 7) === mese && v.importo > 0);

  /** Saldo disponibile: versamenti - puntate (non annullate) + vincite incassate. */
  function saldo(stato) {
    let s = stato.versamenti.reduce((t, v) => t + v.importo, 0);
    for (const g of stato.giocate) {
      if (g.stato === 'annullata') continue;
      s -= g.importo;
      if (g.stato === 'vinta') s += g.importo * g.quota;
    }
    return arrotonda(s);
  }

  /** Risultati reali e confronto con le previsioni (valore atteso al momento della giocata). */
  function statistiche(stato) {
    const chiuse = stato.giocate.filter((g) => g.stato === 'vinta' || g.stato === 'persa');
    const unita = chiuse.reduce((s, g) => s + g.unita, 0);
    const profitto = chiuse.reduce((s, g) => s + profittoUnita(g), 0);
    const atteso = chiuse.reduce((s, g) => s + (g.prob * g.quota - 1) * g.unita, 0);
    const vinte = chiuse.filter((g) => g.stato === 'vinta').length;
    return {
      n_chiuse: chiuse.length, n_aperte: stato.giocate.filter((g) => g.stato === 'aperta').length, vinte,
      unita_giocate: unita, profitto_unita: profitto, roi: unita ? profitto / unita : null,
      atteso_unita: atteso, roi_atteso: unita ? atteso / unita : null,
      vinte_attese: chiuse.reduce((s, g) => s + g.prob, 0),
    };
  }

  // ---------------------------------------------------------------- copia di sicurezza
  const esporta = (stato) => JSON.stringify(stato, null, 1);
  function importa(testo) {
    let o;
    try { o = JSON.parse(testo); } catch (e) { throw new Error('File non valido: non e\' un JSON'); }
    if (!o || typeof o !== 'object' || !Array.isArray(o.giocate) || !Array.isArray(o.versamenti)) {
      throw new Error('File non valido: non sembra una copia di questa app');
    }
    return normalizza(o);
  }

  return {
    STATI, statoIniziale, normalizza, impostaQuota, pulisciQuote, registraGiocata, impostaEsito, eliminaGiocata,
    profittoUnita, giaGiocata, unitaOggi, storicoProfitti, versa, versatoNelMese, saldo, statistiche, esporta, importa,
  };
});

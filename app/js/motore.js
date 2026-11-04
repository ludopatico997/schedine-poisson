/* Passo 8 - Motore di calcolo nel browser: porting di engine/mercati.py, riferimento.py e puntate.py.
 * Serve perche' il cursore del peso del modello ricalcoli le probabilita' anche offline.
 * I numeri devono coincidere con quelli del Python: lo verifica app/js/motore.test.js con valori generati dal Python
 * (engine/genera_fixture_js.py -> app/js/fixture_parita.json).
 * Funziona nel browser (window.Motore) e in Node (require).
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Motore = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const LINEE_UO = [0.5, 1.5, 2.5, 3.5, 4.5];
  const MULTIGOL = [[1, 2], [1, 3], [1, 4], [1, 5], [2, 3], [2, 4], [2, 5], [2, 6], [3, 5], [3, 6]];
  const MERCATI_DIRETTI = ['1', 'X', '2', '1X', 'X2', '12', 'Over 2.5', 'Under 2.5'];
  const COSTANTI = {   // valori di riserva: l'app usa quelli scritti in consigli.json (parametri)
    peso_modello: 0.10, soglia_valore: 0.02, soglia_senza_mercato: 0.08, soglia_disaccordo: 0.10,
    kelly_frazione: 0.25, tetto: 3, pausa: 10, max_multipla: 3, valore_alto: 0.06, quota_max_due: 3.5,
  };

  // ---------------------------------------------------------------- matrice dei punteggi
  function pmfPoisson(media, max) {
    const p = [Math.exp(-media)];
    for (let k = 1; k <= max; k++) p.push(p[k - 1] * media / k);
    return p;
  }

  /** matrice[i][j] = P(casa i gol, ospite j gol), correzione Dixon-Coles sui punteggi bassi, somma 1. */
  function matricePunteggi(lam, mu, rho, maxGol) {
    const n = maxGol === undefined ? 10 : maxGol;
    const a = pmfPoisson(lam, n), b = pmfPoisson(mu, n);
    const m = a.map((x) => b.map((y) => x * y));
    m[0][0] *= Math.max(1 - lam * mu * rho, 1e-10);
    m[0][1] *= Math.max(1 + lam * rho, 1e-10);
    m[1][0] *= Math.max(1 + mu * rho, 1e-10);
    m[1][1] *= Math.max(1 - rho, 1e-10);
    let s = 0;
    for (const r of m) for (const v of r) s += v;
    return m.map((r) => r.map((v) => v / s));
  }

  function sommaDove(m, cond) {
    let s = 0;
    for (let i = 0; i < m.length; i++) for (let j = 0; j < m[i].length; j++) if (cond(i, j)) s += m[i][j];
    return s;
  }

  function mercatiBase(m) {
    return {
      p1: sommaDove(m, (i, j) => i > j), px: sommaDove(m, (i, j) => i === j), p2: sommaDove(m, (i, j) => i < j),
      over25: sommaDove(m, (i, j) => i + j >= 3), under25: sommaDove(m, (i, j) => i + j <= 2),
    };
  }

  /** Probabilita' di ogni esito: 1X2, Doppia Chance, Under/Over 0.5-4.5, GG/NG, Multigol (stessi nomi del Python). */
  function tuttiIMercati(m) {
    const p1 = sommaDove(m, (i, j) => i > j), px = sommaDove(m, (i, j) => i === j), p2 = sommaDove(m, (i, j) => i < j);
    const gg = sommaDove(m, (i, j) => i >= 1 && j >= 1);
    const out = { '1': p1, 'X': px, '2': p2, '1X': p1 + px, 'X2': px + p2, '12': p1 + p2, 'GG': gg, 'NG': 1 - gg };
    for (const l of LINEE_UO) {
      const over = sommaDove(m, (i, j) => i + j > l);
      out['Over ' + l] = over;
      out['Under ' + l] = 1 - over;
    }
    for (const [a, b] of MULTIGOL) out[`Multigol ${a}-${b}`] = sommaDove(m, (i, j) => i + j >= a && i + j <= b);
    return out;
  }

  const quotaEqua = (p) => 1 / p;
  const quotaMinimaValore = (p, soglia) => (1 + (soglia === undefined ? 0.02 : soglia)) / p;

  /** Probabilita' del mercato senza margine (metodo proporzionale). */
  function togliMargine(quote) {
    const inv = quote.map((q) => 1 / q), s = inv.reduce((x, y) => x + y, 0);
    return inv.map((v) => v / s);
  }

  // ---------------------------------------------------------------- gol attesi dal mercato
  /** Minimi quadrati (Levenberg-Marquardt, 2 parametri, limiti come in scipy) per trovare lam, mu del mercato. */
  function lamMuDaMercato(p, rho, maxGol) {
    const r0 = rho === undefined ? -0.07 : rho;
    const LO = -3, HI = 2.5;
    const residui = (x) => {
      const b = mercatiBase(matricePunteggi(Math.exp(x[0]), Math.exp(x[1]), r0, maxGol));
      const r = [b.p1 - p['1'], b.px - p['X'], b.p2 - p['2']];
      if (p['Over 2.5'] !== undefined) r.push(b.over25 - p['Over 2.5']);
      return r;
    };
    const costo = (r) => r.reduce((s, v) => s + v * v, 0);
    const limita = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
    let x = [Math.log(1.4), Math.log(1.1)], r = residui(x), c = costo(r), smorz = 1e-3;
    for (let it = 0; it < 200; it++) {
      const h = 1e-6, J = [];                                   // jacobiana numerica (differenze centrali)
      for (let k = 0; k < 2; k++) {
        const xp = x.slice(), xm = x.slice();
        xp[k] += h; xm[k] -= h;
        const rp = residui(xp), rm = residui(xm);
        J.push(rp.map((v, i) => (v - rm[i]) / (2 * h)));
      }
      const g = J.map((col) => col.reduce((s, v, i) => s + v * r[i], 0));                      // J^T r
      const A = [[0, 0], [0, 0]];
      for (let a = 0; a < 2; a++) for (let b = 0; b < 2; b++) A[a][b] = J[a].reduce((s, v, i) => s + v * J[b][i], 0);
      let migliorato = false;
      for (let tent = 0; tent < 20 && !migliorato; tent++) {
        const a11 = A[0][0] * (1 + smorz) + 1e-12, a22 = A[1][1] * (1 + smorz) + 1e-12, a12 = A[0][1];
        const det = a11 * a22 - a12 * a12;
        const dx = [-(a22 * g[0] - a12 * g[1]) / det, -(-a12 * g[0] + a11 * g[1]) / det];
        const xn = [limita(x[0] + dx[0], LO, HI), limita(x[1] + dx[1], LO, HI)];
        const rn = residui(xn), cn = costo(rn);
        if (cn < c) {
          const passo = Math.hypot(xn[0] - x[0], xn[1] - x[1]);
          x = xn; r = rn; smorz = Math.max(smorz / 5, 1e-12);
          migliorato = true;
          if (c - cn < 1e-16 || passo < 1e-10) { c = cn; it = 1e9; }
          c = cn;
        } else smorz *= 5;
      }
      if (!migliorato) break;
    }
    return { lam: Math.exp(x[0]), mu: Math.exp(x[1]), residuo: Math.max(...r.map(Math.abs)) };
  }

  // ---------------------------------------------------------------- riferimento, valore, semaforo
  /** Mescola mercato e modello (media geometrica dei gol attesi) e ricava tutti i mercati.
   *  opzioni.ancoraggio: {lam, mu, residuo} gia' calcolato (evita di rifare i minimi quadrati quando si muove il cursore). */
  function riferimento(lamMod, muMod, rho, mercato, pesoModello, opzioni) {
    const opt = opzioni || {}, maxGol = opt.maxGol === undefined ? 10 : opt.maxGol;
    const probMod = tuttiIMercati(matricePunteggi(lamMod, muMod, rho, maxGol));
    const haMercato = !!mercato && Object.keys(mercato).length > 0;
    let lam = lamMod, mu = muMod, fonte = 'modello', disaccordo = null, residuo = null, peso = 1;
    if (haMercato) {
      const k = opt.ancoraggio || lamMuDaMercato(mercato, rho, maxGol);
      const w = Math.min(1, Math.max(0, pesoModello === undefined ? COSTANTI.peso_modello : pesoModello));
      lam = Math.pow(k.lam, 1 - w) * Math.pow(lamMod, w);
      mu = Math.pow(k.mu, 1 - w) * Math.pow(muMod, w);
      fonte = w > 0 ? 'mercato+modello' : 'mercato';
      residuo = k.residuo; peso = w;
      disaccordo = Math.max(...Object.keys(mercato).map((n) => Math.abs(probMod[n] - mercato[n])));
    }
    return {
      lam, mu, rho, fonte, disaccordo, residuo_ancoraggio: residuo, peso_modello: peso,
      probabilita: tuttiIMercati(matricePunteggi(lam, mu, rho, maxGol)), prob_modello: probMod,
      prob_mercato: haMercato ? mercato : null,
    };
  }

  const valore = (prob, quota) => prob * quota - 1;

  const pc = (x, dec, segno) => {
    const v = (x * 100).toFixed(dec);
    return (segno && x >= 0 ? '+' : '') + v.replace('.', ',') + '%';
  };

  function semaforo(val, disaccordo, diretto, soglie) {
    const s = Object.assign({}, COSTANTI, soglie || {});
    const soglia = diretto ? s.soglia_valore : s.soglia_senza_mercato;
    if (val < soglia) return ['rosso', `valore ${pc(val, 1, true)} sotto la soglia richiesta (${pc(soglia, 0, true)})`];
    if (disaccordo !== null && disaccordo !== undefined && disaccordo > s.soglia_disaccordo) {
      return ['giallo', `valore ${pc(val, 1, true)}, ma modello e mercato differiscono di ${pc(disaccordo, 0)}: controlla infortuni e formazioni`];
    }
    const nota = diretto ? '' : ' (stima non verificabile con quote di mercato)';
    return ['verde', `valore ${pc(val, 1, true)} sopra la soglia (${pc(soglia, 0, true)})${nota}`];
  }

  /** Per ogni quota del bookmaker: probabilita', quota equa, valore, quota minima, semaforo. */
  function scheda(rif, quoteBookmaker, soglie) {
    const s = Object.assign({}, COSTANTI, soglie || {});
    const pm = rif.prob_mercato || {};
    const haMercato = Object.keys(pm).length > 0;
    return Object.keys(quoteBookmaker).map((nome) => {
      const q = quoteBookmaker[nome], p = rif.probabilita[nome];
      const diretto = MERCATI_DIRETTI.includes(nome) && (!(nome === 'Over 2.5' || nome === 'Under 2.5') || pm[nome] !== undefined) && haMercato;
      const v = valore(p, q), [colore, motivo] = semaforo(v, rif.disaccordo, diretto, s);
      return {
        mercato: nome, prob_riferimento: p, quota_equa: 1 / p, quota_bookmaker: q, diretto, valore: v,
        quota_minima: quotaMinimaValore(p, diretto ? s.soglia_valore : s.soglia_senza_mercato), semaforo: colore, motivo,
      };
    });
  }

  // ---------------------------------------------------------------- puntate
  const kelly = (p, q) => (q <= 1 ? 0 : Math.max((p * q - 1) / (q - 1), 0));
  const kellyFrazionato = (p, q, f) => (f === undefined ? COSTANTI.kelly_frazione : f) * kelly(p, q);
  const unitaSingola = (val, quota, diretto, s) => {
    const c = Object.assign({}, COSTANTI, s || {});
    return diretto && val >= c.valore_alto && quota <= c.quota_max_due ? 2 : 1;
  };

  const giorniPrima = (iso, n) => {
    const d = new Date(iso + 'T12:00:00Z');
    d.setUTCDate(d.getUTCDate() - n);
    return d.toISOString().slice(0, 10);
  };

  /** storico: [{data:'YYYY-MM-DD', profitto_unita}] -> perdita netta (>= 0) negli ultimi `giorni` giorni, oggi compreso. */
  function perditaUltimiGiorni(storico, oggi, giorni) {
    const da = giorniPrima(oggi, (giorni === undefined ? 7 : giorni) - 1);
    const netto = storico.filter((s) => s.data >= da && s.data <= oggi).reduce((t, s) => t + s.profitto_unita, 0);
    return Math.max(-netto, 0);
  }

  /** Sceglie singole e (eventualmente) una multipla. candidati: righe di scheda() con in piu' 'partita' e 'etichetta'. */
  function selezionaGiocate(candidati, opzioni) {
    const o = Object.assign({ valore_unita: 1, bankroll: null, perdita_settimana: 0 }, COSTANTI, opzioni || {});
    const msg = [];
    const vuoto = { stato: 'nessuna', singole: [], multipla: null, unita_totali: 0, importo_totale: 0, messaggi: msg };
    if (o.perdita_settimana >= o.pausa) {
      msg.push(`PAUSA: in una settimana hai perso ${o.perdita_settimana.toFixed(0)} unità. Nessuna giocata finché non fai una revisione.`);
      return Object.assign({}, vuoto, { stato: 'pausa' });
    }
    const gialli = candidati.filter((c) => c.semaforo === 'giallo');
    if (gialli.length) msg.push(`${gialli.length} giocate in giallo: modello e mercato sono in disaccordo, controlla infortuni e formazioni prima di decidere.`);
    const verdi = candidati.filter((c) => c.semaforo === 'verde').map((c) => Object.assign({}, c, {
      kelly: kellyFrazionato(c.prob_riferimento, c.quota_bookmaker, o.kelly_frazione) }));
    if (!verdi.length) {
      msg.push("Nessuna giocata con valore sufficiente: oggi non giocare è la scelta migliore.");
      return vuoto;
    }
    verdi.sort((a, b) => (b.kelly - a.kelly) || (b.valore - a.valore));
    const scelte = [], viste = new Set();
    for (const c of verdi) {
      if (viste.has(c.partita)) { msg.push(`${c.etichetta}: scartata, hai già una giocata su questa partita (esiti correlati).`); continue; }
      viste.add(c.partita); scelte.push(c);
    }
    let limite = o.tetto;
    if (o.bankroll !== null && o.bankroll !== undefined) {
      limite = Math.min(limite, Math.floor(o.bankroll / o.valore_unita + 1e-9));
      if (limite < o.tetto) msg.push(`Bankroll o tetto: massimo ${Math.max(limite, 0)} unità disponibili.`);
    }
    const singole = []; let usate = 0;
    for (const c of scelte) {
      let u = unitaSingola(c.valore, c.quota_bookmaker, c.diretto, o);
      if (usate + u > limite) u = limite - usate;
      if (u <= 0) { msg.push(`${c.etichetta}: oltre il tetto di ${o.tetto} unità al giorno, non giocata.`); continue; }
      usate += u;
      singole.push(Object.assign({}, c, { unita: u, importo: u * o.valore_unita }));
    }
    let multipla = null;
    const legs = scelte.slice(0, o.max_multipla);
    if (legs.length >= 2 && usate + 1 <= limite) {
      const quota = legs.reduce((t, c) => t * c.quota_bookmaker, 1), prob = legs.reduce((t, c) => t * c.prob_riferimento, 1);
      multipla = {
        eventi: legs.map((c) => c.etichetta), partite: legs.map((c) => c.partita), legs,
        quota_totale: quota, prob_totale: prob, valore: prob * quota - 1, unita: 1, importo: o.valore_unita,
        nota: 'Ogni evento in più aggiunge il margine del bookmaker e fa salire la varianza: una sola unità.',
      };
      usate += 1;
    } else if (legs.length >= 2) msg.push('Multipla non proposta: tetto giornaliero raggiunto con le singole.');
    return {
      stato: singole.length || multipla ? 'ok' : 'nessuna', singole, multipla, unita_totali: usate,
      importo_totale: usate * o.valore_unita, messaggi: msg,
    };
  }

  return {
    LINEE_UO, MULTIGOL, MERCATI_DIRETTI, COSTANTI, matricePunteggi, mercatiBase, tuttiIMercati, quotaEqua, quotaMinimaValore,
    togliMargine, lamMuDaMercato, riferimento, valore, semaforo, scheda, kelly, kellyFrazionato, unitaSingola,
    perditaUltimiGiorni, selezionaGiocate, pc, giorniPrima,
  };
});

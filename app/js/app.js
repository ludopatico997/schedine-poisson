/* Schedine Poisson - interfaccia. I calcoli stanno in motore.js, i dati dell'utente in archivio.js (solo nel browser).
 * Nessun dato personale lascia il telefono: il sito pubblico serve solo consigli.json (probabilita' e quote minime). */
(function () {
  'use strict';
  const M = window.Motore, A = window.Archivio, P = window.ParserQuote;
  const CHIAVE = 'schedine-poisson/v1';
  const vista = document.getElementById('vista');
  let dati = null, erroreDati = null, stato = A.statoIniziale(), soloMemoria = false, filtro = 'tutti';

  // ------------------------------------------------------------------ utilita'
  function el(tag, attrs, ...figli) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k === 'value') e.value = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const f of figli.flat(3)) {
      if (f === null || f === undefined || f === false) continue;
      e.append(f.nodeType ? f : document.createTextNode(String(f)));
    }
    return e;
  }
  const q2 = (x) => (x === null || x === undefined || !isFinite(x) ? '–' : (x >= 100 ? x.toFixed(0) : x.toFixed(2)).replace('.', ','));
  const pct = (x, d) => (x * 100).toFixed(d || 0).replace('.', ',') + '%';
  const eur = (x) => x.toLocaleString('it-IT', { style: 'currency', currency: 'EUR' });
  const segno = (x, dec) => (x >= 0 ? '+' : '−') + Math.abs(x).toFixed(dec === undefined ? 1 : dec).replace('.', ',');
  const numero = (s) => { const v = parseFloat(String(s).trim().replace(',', '.')); return isFinite(v) ? v : NaN; };
  const pad = (n) => String(n).padStart(2, '0');
  const oggiISO = () => { const t = new Date(); return `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())}`; };
  const chiaveGiorno = (iso) => { const t = new Date(iso); return `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())}`; };
  const giornoLungo = (iso) => new Date(iso).toLocaleDateString('it-IT', { weekday: 'long', day: 'numeric', month: 'long' });
  const oraDi = (iso) => new Date(iso).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  const NOME_SEMAFORO = { verde: 'Verde', giallo: 'Giallo', rosso: 'Rosso' };
  const etichetta = (m) => m.replace(/(Under|Over) (\d)\.(\d)/, '$1 $2,$3');
  const etichettaRiga = (m) => (m.startsWith('Multigol ') ? m.slice(9).replace('-', '–') : etichetta(m));
  const maiuscola = (s) => s.charAt(0).toUpperCase() + s.slice(1);

  let timerAvviso = null;
  function avviso(testo) {
    const t = document.getElementById('avviso');
    t.textContent = testo; t.hidden = false;
    clearTimeout(timerAvviso); timerAvviso = setTimeout(() => { t.hidden = true; }, 2600);
  }

  function conferma(titolo, testo, ok, pericolo) {
    const d = document.getElementById('dialogo');
    if (typeof d.showModal !== 'function') return Promise.resolve(window.confirm(titolo + '\n' + testo));
    document.getElementById('dialogo-titolo').textContent = titolo;
    document.getElementById('dialogo-testo').textContent = testo;
    const b = document.getElementById('dialogo-ok');
    b.textContent = ok || 'Conferma'; b.className = pericolo ? 'pericolo' : '';
    d.returnValue = '';
    return new Promise((ris) => { d.addEventListener('close', () => ris(d.returnValue === 'si'), { once: true }); d.showModal(); });
  }

  // ------------------------------------------------------------------ salvataggio (solo nel browser)
  function carica() {
    try { const t = localStorage.getItem(CHIAVE); if (t) return A.normalizza(JSON.parse(t)); } catch (e) { soloMemoria = true; }
    return A.statoIniziale();
  }
  function salva() { try { localStorage.setItem(CHIAVE, JSON.stringify(stato)); } catch (e) { soloMemoria = true; } }

  // ------------------------------------------------------------------ parametri e calcoli
  function parametri() {
    const p = (dati && dati.parametri) || {}, s = p.soglie || {}, u = p.puntate || {}, C = M.COSTANTI;
    const pick = (a, b) => (a === undefined || a === null ? b : a);
    return {
      soglie: {
        soglia_valore: pick(s.valore_mercato_diretto, C.soglia_valore),
        soglia_senza_mercato: pick(s.valore_senza_mercato, C.soglia_senza_mercato),
        soglia_disaccordo: pick(s.disaccordo, C.soglia_disaccordo),
      },
      puntate: {
        tetto: pick(u.tetto_giornaliero_unita, C.tetto), pausa: pick(u.pausa_dopo_perdita_unita, C.pausa),
        max_multipla: pick(u.max_eventi_multipla, C.max_multipla), kelly_frazione: pick(u.kelly_frazione, C.kelly_frazione),
        valore_alto: pick(u.valore_alto_due_unita, C.valore_alto), quota_max_due: pick(u.quota_max_due_unita, C.quota_max_due),
      },
    };
  }
  const memo = { anc: new Map(), rif: new Map() };
  function ancoraggio(p) {
    if (!p.mercato) return null;
    if (!memo.anc.has(p.id)) memo.anc.set(p.id, M.lamMuDaMercato(p.mercato.prob, p.modello.rho));
    return memo.anc.get(p.id);
  }
  function rifDi(p, peso) {
    const w = peso === undefined ? stato.impostazioni.peso_modello : peso, k = p.id + '|' + w;
    if (!memo.rif.has(k)) {
      if (memo.rif.size > 3000) memo.rif.clear();
      memo.rif.set(k, M.riferimento(p.modello.lam, p.modello.mu, p.modello.rho, p.mercato ? p.mercato.prob : null, w, { ancoraggio: ancoraggio(p) }));
    }
    return memo.rif.get(k);
  }
  function quotaMercato(p, nome) {
    if (!p.mercato) return { q: null };
    const pm = p.mercato.prob, dc = { '1X': ['1', 'X'], 'X2': ['X', '2'], '12': ['1', '2'] };
    if (pm[nome] !== undefined) return { q: 1 / pm[nome] };
    if (dc[nome]) return { q: 1 / (pm[dc[nome][0]] + pm[dc[nome][1]]) };
    return { q: 1 / rifDi(p, 0).probabilita[nome], derivata: true };
  }
  const eDiretto = (p, nome) => !!p.mercato && M.MERCATI_DIRETTI.includes(nome) &&
    (!(nome === 'Over 2.5' || nome === 'Under 2.5') || p.mercato.prob[nome] !== undefined);
  const iniziata = (p) => !dati.demo && new Date(p.inizio) <= new Date();
  const descrizioneMercato = (p) => (p.mercato
    ? `mercato: ${p.mercato.fonte}${p.mercato.n_bookmaker ? ` (${p.mercato.n_bookmaker} bookmaker)` : ''}` : 'solo modello');
  const saldoUnita = () => Math.floor(A.saldo(stato) / stato.impostazioni.valore_unita + 1e-9);
  const perditaSettimana = () => M.perditaUltimiGiorni(A.storicoProfitti(stato), oggiISO());
  const inPausa = () => perditaSettimana() >= parametri().puntate.pausa;

  function vuoto(titolo, testo, azione) {
    return el('div', { class: 'vuoto' }, el('h2', {}, titolo), el('p', {}, testo), azione || null);
  }
  function bannerComuni() {
    const out = [];
    if (dati && dati.demo) out.push(el('div', { class: 'banner rosso' }, el('strong', {}, 'Dati di prova. '), 'Sono partite già giocate, usate solo per provare l\'app: non servono per giocare.'));
    if (dati && !dati.demo) {
      const ore = (Date.now() - new Date(dati.generato).getTime()) / 3.6e6;
      if (ore > 36) out.push(el('div', { class: 'banner' }, el('strong', {}, 'Consigli non aggiornati. '), `Sono stati calcolati ${Math.round(ore)} ore fa: controlla che il calcolo giornaliero su GitHub funzioni.`));
    }
    if (inPausa()) out.push(el('div', { class: 'banner rosso' }, el('strong', {}, 'Pausa di revisione. '), `Negli ultimi 7 giorni hai perso ${perditaSettimana().toFixed(0)} unità: nessuna giocata finché non fai una revisione.`));
    return out;
  }

  // ------------------------------------------------------------------ elenco partite
  function vistaPartite() {
    const radice = el('div');
    if (erroreDati || !dati) {
      return vuoto('Consigli non disponibili', `Non riesco a leggere i consigli${erroreDati ? ' (' + erroreDati + ')' : ''}. Se sei offline, riapri l'app quando c'è rete: i dati scaricati l'ultima volta restano disponibili.`,
        el('button', { onclick: () => start() }, 'Riprova'));
    }
    bannerComuni().forEach((b) => radice.append(b));
    const campionati = [...new Map(dati.partite.map((p) => [p.campionato, p.nome_campionato])).entries()];
    if (campionati.length > 1) {
      const f = el('div', { class: 'filtri', role: 'group', 'aria-label': 'Campionato' });
      [['tutti', 'Tutti'], ...campionati].forEach(([cod, nome]) => f.append(
        el('button', { 'aria-pressed': filtro === cod ? 'true' : 'false', onclick: () => { filtro = cod; route(); } }, nome)));
      radice.append(f);
    }
    const lista = dati.partite.filter((p) => filtro === 'tutti' || p.campionato === filtro);
    if (!lista.length) {
      radice.append(vuoto('Nessuna partita', 'Non ci sono partite con quote disponibili in questo momento. Il calcolo gira ogni mattina.'));
      return radice;
    }
    let giorno = '';
    for (const p of lista) {
      const g = chiaveGiorno(p.inizio);
      if (g !== giorno) { giorno = g; radice.append(el('h2', { class: 'giorno' }, maiuscola(giornoLungo(p.inizio)))); }
      radice.append(rigaPartita(p));
    }
    return radice;
  }

  function rigaPartita(p) {
    const r = rifDi(p).probabilita, qs = stato.quote[p.id];
    let semaforo = null;
    if (qs) {
      const colori = M.scheda(rifDi(p), qs, parametri().soglie).map((x) => x.semaforo);
      semaforo = colori.includes('verde') ? 'verde' : colori.includes('giallo') ? 'giallo' : colori.length ? 'rosso' : null;
    }
    const seg = (cls, v) => { const s = el('span', { class: cls }, v >= 0.13 ? String(Math.round(v * 100)) : ''); s.style.flex = `${v} 1 0`; return s; };
    return el('a', { class: 'partita', href: '#/partita/' + encodeURIComponent(p.id), 'aria-label': `${p.casa} – ${p.ospite}, apri la scheda` },
      el('div', { class: 'ora num' }, oraDi(p.inizio)),
      el('div', {}, el('div', { class: 'squadre' }, `${p.casa} – ${p.ospite}`),
        el('div', { class: 'sotto' }, `${p.nome_campionato} · ${descrizioneMercato(p)}`, iniziata(p) ? ' · iniziata' : '',
          semaforo ? [' · ', el('span', { class: 'punto ' + semaforo }), 'tua quota: ' + semaforo] : '')),
      el('div', { class: 'barra3', role: 'img', 'aria-label': `Probabilità: 1 ${pct(r['1'])}, X ${pct(r['X'])}, 2 ${pct(r['2'])}` },
        seg('s1', r['1']), seg('sx', r['X']), seg('s2', r['2'])));
  }

  // ------------------------------------------------------------------ scheda partita
  const GRUPPI = [
    { id: '1x2', titolo: 'Esito finale (1X2)', righe: ['1', 'X', '2'] },
    { id: 'dc', titolo: 'Doppia chance', righe: ['1X', '12', 'X2'] },
    { id: 'uo', titolo: 'Under / Over 2,5', righe: ['Under 2.5', 'Over 2.5'] },
    { id: 'gg', titolo: 'Gol / NoGol', righe: ['GG', 'NG'] },
    { id: 'uoaltre', titolo: 'Altre linee Under / Over', chiuso: true, righe: [0.5, 1.5, 3.5, 4.5].flatMap((l) => ['Under ' + l, 'Over ' + l]) },
    { id: 'mg', titolo: 'Multigol', chiuso: true, righe: M.MULTIGOL.map(([a, b]) => `Multigol ${a}-${b}`) },
  ];

  /** Righello: dove cade la tua quota rispetto a modello, mercato e quota minima di valore (scala logaritmica). */
  function righello(modQ, merQ, minQ, tuaQ, colore) {
    const valori = [modQ, merQ, minQ, tuaQ].filter((v) => v && isFinite(v));
    const lo = Math.min(...valori) * 0.9, hi = Math.max(...valori) * 1.1;
    const L = (v) => ((Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo))) * 100;
    const sx = (cls, v, titolo) => { const m = el('span', { class: 'm ' + cls, title: titolo }); m.style.left = L(v) + '%'; return m; };
    const zona = el('span', { class: 'zona' }); zona.style.left = L(minQ) + '%'; zona.style.right = '0';
    return el('div', { class: 'righello', role: 'img',
      'aria-label': `Quota del modello ${q2(modQ)}, del mercato ${merQ ? q2(merQ) : 'non disponibile'}, minima di valore ${q2(minQ)}, la tua ${q2(tuaQ)}` },
    el('span', { class: 'asse' }), zona, sx('mod', modQ, 'modello'), merQ ? sx('mer', merQ, 'mercato') : null,
    sx('min', minQ, 'quota minima di valore'), sx('tua ' + colore, tuaQ, 'la tua quota'));
  }

  function creaRiga(p, rif, nome, qs, soglie) {
    const pMod = rif.prob_modello[nome], pRif = rif.probabilita[nome], mer = quotaMercato(p, nome);
    const qMin = M.quotaMinimaValore(pRif, eDiretto(p, nome) ? soglie.soglia_valore : soglie.soglia_senza_mercato);
    const input = el('input', { type: 'text', inputmode: 'decimal', autocomplete: 'off', placeholder: '–',
      'aria-label': `La tua quota per ${etichetta(nome)}`, value: qs[nome] ? q2(qs[nome]) : '' });
    const esito = el('div', { class: 'esito' });
    const aggiorna = () => {
      esito.replaceChildren();
      const v = numero(input.value);
      if (!(v > 1)) { esito.hidden = true; return; }
      esito.hidden = false;
      const r = M.scheda(rif, { [nome]: v }, soglie)[0];
      esito.append(el('span', { class: 'chip ' + r.semaforo }, NOME_SEMAFORO[r.semaforo]), el('span', { class: 'motivo' }, r.motivo),
        righello(1 / pMod, mer.q, qMin, v, r.semaforo));
    };
    input.addEventListener('input', () => { A.impostaQuota(stato, p.id, nome, numero(input.value)); salva(); aggiorna(); });
    aggiorna();
    return el('div', { class: 'riga' }, el('div', { class: 'nome' }, etichettaRiga(nome)),
      el('div', { class: 'q mod' }, q2(1 / pMod)),
      el('div', { class: 'q mer' }, mer.q ? q2(mer.q) + (mer.derivata ? '*' : '') : '–'),
      el('div', { class: 'q rif' }, q2(1 / pRif), el('small', {}, 'min ' + q2(qMin))), input, esito);
  }

  function disegnaTabella(p, cont) {
    const rif = rifDi(p), qs = stato.quote[p.id] || {}, soglie = parametri().soglie;
    const apertiPrima = new Set([...cont.querySelectorAll('details.gruppo[open]')].map((d) => d.dataset.g));
    cont.replaceChildren(el('div', { class: 'legenda', 'aria-hidden': 'true' },
      el('span', {}, el('i', { class: 'l l-mod' }), 'modello'), el('span', {}, el('i', { class: 'l l-mer' }), 'mercato'),
      el('span', {}, el('i', { class: 'l l-min' }), 'quota minima di valore'), el('span', {}, el('i', { class: 'l l-tua' }), 'la tua quota')));
    for (const g of GRUPPI) {
      const intest = el('div', { class: 'riga intest', 'aria-hidden': 'true' }, el('div'), el('div', { class: 'q' }, 'Modello'),
        el('div', { class: 'q' }, 'Mercato'), el('div', { class: 'q' }, 'Riferim.'), el('div', { class: 'q' }, 'La tua'));
      const righe = g.righe.map((n) => creaRiga(p, rif, n, qs, soglie));
      if (g.chiuso) {
        const aperto = apertiPrima.has(g.id) || g.righe.some((n) => qs[n]);
        cont.append(el('details', { class: 'gruppo', 'data-g': g.id, open: aperto }, el('summary', {}, g.titolo), intest, righe));
      } else cont.append(el('section', { class: 'gruppo' }, el('h3', {}, g.titolo), intest, righe));
    }
    cont.append(el('p', { class: 'piccolo tenue', style: 'margin-top:14px' },
      '* quota ricavata dalle quote 1X2 e Under/Over 2,5 del mercato (non esiste una quota di mercato diretta). "Riferim." è la quota che l\'app usa per calcolare il valore: mercato e modello mescolati col peso scelto sopra.'));
  }

  function leggiQuote(p, tipo, linea, testo) {
    if (tipo === 'MG') {
      const o = P.leggiMultigol(testo), nomi = Object.keys(o);
      if (!nomi.length) return { ok: false, msgs: ['Nessuna quota Multigol riconosciuta. Formato atteso: "1-3 1,70".'] };
      nomi.forEach((n) => A.impostaQuota(stato, p.id, n, o[n]));
      return { ok: true, msgs: [`${nomi.length} quote Multigol lette.`] };
    }
    const voci = P.estrai(testo);
    if (!voci.length) return { ok: false, msgs: ['Nessuna quota trovata nel testo incollato.'] };
    const nostri = [p.casa, p.ospite];
    const coincidono = voci.filter((v) => v.casa && v.ospite && P.abbina(v.casa, nostri).nome === p.casa && P.abbina(v.ospite, nostri).nome === p.ospite);
    const msgs = [];
    let voce;
    if (coincidono.length) voce = coincidono[0];
    else if (voci.length === 1) {
      voce = voci[0];
      if (voce.casa && /[A-Za-zÀ-ÿ]{2,}/.test(voce.casa)) msgs.push(`Il testo parla di "${voce.casa} – ${voce.ospite}": controlla che sia la partita giusta.`);
    } else return { ok: false, msgs: [`Nel testo ci sono ${voci.length} partite e nessuna coincide con ${p.casa} – ${p.ospite}. Incolla solo il blocco di questa partita.`] };
    const r = P.assegna(voce.quote, tipo, { linea: Number(linea) });
    msgs.push(...r.avvisi);
    if (!r.ok) return { ok: false, msgs };
    Object.keys(r.quote).forEach((n) => A.impostaQuota(stato, p.id, n, r.quote[n]));
    msgs.unshift('Lette: ' + Object.keys(r.quote).map((n) => `${etichetta(n)} ${q2(r.quote[n])}`).join(' · '));
    return { ok: true, msgs };
  }

  function vistaPartita(id) {
    const p = dati && dati.partite.find((x) => x.id === id);
    if (!p) return vuoto('Partita non trovata', 'Questa partita non è più nei consigli di oggi.', el('a', { class: 'pulsante', href: '#/' }, 'Torna alle partite'));
    const radice = el('div'), soglie = parametri().soglie;
    const contAvviso = el('div'), contTabella = el('div'), etPeso = el('span', { class: 'num' });
    const slider = el('input', { type: 'range', min: 0, max: 100, step: 5, value: Math.round(stato.impostazioni.peso_modello * 100), 'aria-label': 'Peso del modello' });
    const disegnaAvviso = () => {
      const rif = rifDi(p);
      contAvviso.replaceChildren();
      if (dati.demo) contAvviso.append(el('div', { class: 'banner rosso' }, 'Partita di prova, già giocata.'));
      else if (iniziata(p)) contAvviso.append(el('div', { class: 'banner rosso' }, 'Questa partita è già iniziata.'));
      if (!p.mercato) contAvviso.append(el('div', { class: 'banner' }, el('strong', {}, 'Nessuna quota di mercato per questa partita. '),
        `Le probabilità vengono solo dal modello, che da solo non batte il mercato: la soglia di valore sale al ${pct(soglie.soglia_senza_mercato)}.`));
      else if (rif.disaccordo > soglie.soglia_disaccordo) contAvviso.append(el('div', { class: 'banner' },
        el('strong', {}, `Modello e mercato differiscono di ${Math.round(rif.disaccordo * 100)} punti. `),
        'Il mercato può sapere di infortuni, squalifiche e formazioni che il modello ignora: controlla prima di giocare. Qui nessuna giocata può essere verde.'));
    };
    const ridisegna = () => { etPeso.textContent = pct(stato.impostazioni.peso_modello); disegnaAvviso(); disegnaTabella(p, contTabella); };
    slider.addEventListener('input', () => { stato.impostazioni.peso_modello = Number(slider.value) / 100; salva(); ridisegna(); });

    // "incolla e leggi": legge il testo incollato, senza collegarsi a nessun sito
    const tipo = el('select', { 'aria-label': 'Mercato incollato' }, ...[['1X2', 'Esito finale 1X2'], ['DC', 'Doppia chance (1X, 12, X2)'],
      ['UO', 'Under / Over'], ['GGNG', 'Gol / NoGol'], ['MG', 'Multigol']].map(([v, t]) => el('option', { value: v }, t)));
    const linea = el('select', { 'aria-label': 'Linea Under/Over' }, ...[0.5, 1.5, 2.5, 3.5, 4.5].map((l) => el('option', { value: l, selected: l === 2.5 }, String(l).replace('.', ','))));
    const lineaCampo = el('label', { hidden: true }, 'Linea', linea);
    tipo.addEventListener('change', () => { lineaCampo.hidden = tipo.value !== 'UO'; });
    const testo = el('textarea', { rows: 4, placeholder: 'Incolla qui il testo copiato dal sito o dall\'app del bookmaker', 'aria-label': 'Testo con le quote' });
    const esitoLettura = el('ul');
    const leggi = el('button', { onclick: () => {
      const r = leggiQuote(p, tipo.value, linea.value, testo.value);
      esitoLettura.replaceChildren(...r.msgs.map((m) => el('li', {}, m)));
      if (r.ok) { salva(); disegnaTabella(p, contTabella); avviso('Quote inserite'); }
    } }, 'Leggi quote');
    const incolla = el('details', { class: 'incolla' }, el('summary', {}, 'Incolla le quote del tuo bookmaker'),
      el('div', { class: 'dentro' },
        el('p', { class: 'piccolo tenue' }, 'Copia il blocco delle quote dal sito o dall\'app del bookmaker e incollalo qui. L\'app legge solo il testo che incolli: non si collega a nessun sito. In alternativa scrivi le quote a mano nella tabella.'),
        el('div', { class: 'due' }, el('label', {}, 'Mercato', tipo), lineaCampo), testo, leggi, esitoLettura));

    radice.append(el('a', { class: 'indietro', href: '#/' }, '‹ Partite'),
      el('div', { class: 'intesta' }, el('h2', {}, `${p.casa} – ${p.ospite}`),
        el('div', { class: 'meta' }, `${p.nome_campionato} · ${giornoLungo(p.inizio)}, ${oraDi(p.inizio)} · ${descrizioneMercato(p)}`)),
      contAvviso,
      el('div', { class: 'regolo' }, el('label', {}, el('span', {}, 'Peso del modello'), etPeso), slider,
        el('div', { class: 'piccolo tenue' }, '0% = solo mercato · 100% = solo modello. Nei test storici il mercato da solo è la scelta più precisa: il valore consigliato è 10%.')),
      incolla, contTabella);
    ridisegna();
    return radice;
  }

  // ------------------------------------------------------------------ consigli
  function candidati() {
    const out = [], saltate = [];
    if (!dati) return { out, saltate };
    const soglie = parametri().soglie;
    for (const p of dati.partite) {
      const qs = stato.quote[p.id];
      if (!qs || iniziata(p)) continue;
      if (A.giaGiocata(stato, p.id)) { saltate.push(p); continue; }
      for (const r of M.scheda(rifDi(p), qs, soglie)) {
        out.push(Object.assign(r, { partita: p.id, casa: p.casa, ospite: p.ospite, etichetta: `${p.casa} – ${p.ospite}: ${etichetta(r.mercato)}` }));
      }
    }
    return { out, saltate };
  }

  function registra(eventi, unita) {
    if (A.saldo(stato) + 1e-9 < unita * stato.impostazioni.valore_unita) { avviso('Saldo insufficiente'); return; }
    A.registraGiocata(stato, eventi, unita, stato.impostazioni.valore_unita);
    salva(); avviso('Giocata registrata'); route();
  }
  const evento = (c) => ({ partita: c.partita, etichetta: c.etichetta, mercato: c.mercato, quota: c.quota_bookmaker, prob: c.prob_riferimento });

  function voceSingola(c, conBottone) {
    const dettagli = el('div', { class: 'dati' },
      el('span', {}, 'quota ', el('b', { class: 'num' }, q2(c.quota_bookmaker))),
      el('span', {}, 'probabilità ', el('b', { class: 'num' }, pct(c.prob_riferimento, 1))),
      el('span', {}, 'valore ', el('b', { class: 'num' }, segno(c.valore * 100) + '%')),
      el('span', {}, 'quota minima ', el('b', { class: 'num' }, q2(c.quota_minima))));
    return el('div', { class: 'voce' }, el('div', { class: 'titolo' }, el('span', { class: 'chip ' + c.semaforo }, NOME_SEMAFORO[c.semaforo]), c.etichetta), dettagli,
      conBottone
        ? el('div', { class: 'azioni' }, el('span', { class: 'puntata' }, `Puntata: ${c.unita} ${c.unita === 1 ? 'unità' : 'unità'} (${eur(c.importo)})`),
          el('button', { onclick: () => registra([evento(c)], c.unita) }, 'Registra giocata'))
        : el('div', { class: 'piccolo tenue', style: 'margin-top:3px' }, c.motivo));
  }

  function vistaConsigli() {
    const radice = el('div');
    if (!dati) return vuoto('Consigli non disponibili', 'Non riesco a leggere i consigli: riprova quando c\'è rete.', el('button', { onclick: () => start() }, 'Riprova'));
    radice.append(el('h2', {}, 'Cosa giocare oggi'));
    bannerComuni().forEach((b) => radice.append(b));
    const { out, saltate } = candidati(), par = parametri();
    if (!out.length) {
      radice.append(vuoto('Nessuna quota inserita',
        saltate.length ? 'Hai già una giocata sulle partite per cui avevi inserito le quote.'
          : 'Apri una partita e inserisci le quote del tuo bookmaker, a mano o incollando il testo. Qui compaiono le giocate che hanno valore.',
        el('a', { class: 'pulsante', href: '#/' }, 'Vai alle partite')));
      return radice;
    }
    const usate = A.unitaOggi(stato, oggiISO()), tettoResiduo = Math.max(0, par.puntate.tetto - usate);
    let sel = null;
    if (saldoUnita() < 1) radice.append(el('div', { class: 'banner' }, el('strong', {}, 'Bankroll esaurito. '), `Hai ${eur(A.saldo(stato))}: aspetta il versamento del mese.`,
      el('div', { class: 'azioni' }, el('a', { class: 'pulsante secondario', href: '#/conto' }, 'Vai al conto'))));
    else if (inPausa()) { /* il banner di pausa e' gia' in cima */ }
    else if (tettoResiduo <= 0) radice.append(el('div', { class: 'banner' }, el('strong', {}, 'Tetto giornaliero raggiunto. '), `Oggi hai già giocato ${usate} unità su ${par.puntate.tetto}: per oggi basta.`));
    else sel = M.selezionaGiocate(out, Object.assign({ valore_unita: stato.impostazioni.valore_unita, bankroll: A.saldo(stato), perdita_settimana: perditaSettimana(), tetto: tettoResiduo }, par.puntate));
    if (sel) {
      sel.messaggi.forEach((m) => radice.append(el('div', { class: m.startsWith('PAUSA') ? 'banner rosso' : 'banner info' }, m)));
      if (sel.singole.length) radice.append(el('div', { class: 'sezione' }, el('h2', {}, sel.singole.length > 1 ? 'Singole' : 'Singola'), ...sel.singole.map((c) => voceSingola(c, true))));
      if (sel.multipla) {
        const m = sel.multipla;
        radice.append(el('div', { class: 'sezione' }, el('h2', {}, `Multipla (${m.eventi.length} eventi)`),
          el('div', { class: 'voce' }, el('ul', { class: 'lista-piana' }, ...m.legs.map((c) => el('li', {}, `${c.etichetta} @ ${q2(c.quota_bookmaker)}`))),
            el('div', { class: 'dati' }, el('span', {}, 'quota totale ', el('b', { class: 'num' }, q2(m.quota_totale))),
              el('span', {}, 'probabilità ', el('b', { class: 'num' }, pct(m.prob_totale, 1))), el('span', {}, 'valore ', el('b', { class: 'num' }, segno(m.valore * 100) + '%'))),
            el('p', { class: 'piccolo tenue' }, m.nota),
            el('div', { class: 'azioni' }, el('span', { class: 'puntata' }, `Puntata: 1 unità (${eur(m.importo)})`),
              el('button', { onclick: () => registra(m.legs.map(evento), 1) }, 'Registra multipla')))));
      }
    }
    const gialli = out.filter((c) => c.semaforo === 'giallo');
    if (gialli.length) radice.append(el('div', { class: 'sezione' }, el('h2', {}, 'Da controllare a mano'),
      el('p', { class: 'piccolo tenue' }, 'Valore sufficiente, ma modello e mercato non sono d\'accordo: l\'app non propone la puntata.'), ...gialli.map((c) => voceSingola(c, false))));
    radice.append(el('details', { class: 'sezione' }, el('summary', {}, `Tutte le quote valutate (${out.length})`), ...out.map((c) => voceSingola(c, false))));
    if (saltate.length) radice.append(el('p', { class: 'piccolo tenue' }, `Escluse perché hai già una giocata: ${saltate.map((p) => `${p.casa} – ${p.ospite}`).join(', ')}.`));
    radice.append(el('p', { class: 'piccolo tenue', style: 'margin-top:18px' }, 'Il valore è una stima: il margine del bookmaker è sempre un costo e nessuna giocata è garantita.'));
    return radice;
  }

  // ------------------------------------------------------------------ giocate e risultati
  function vistaGiocate() {
    const radice = el('div', {}, el('h2', {}, 'Giocate'));
    const s = A.statistiche(stato);
    const profittoEuro = stato.giocate.reduce((t, g) => t + A.profittoUnita(g) * g.valore_unita, 0);
    if (!stato.giocate.length) {
      radice.append(vuoto('Nessuna giocata registrata', 'Quando registri una giocata dalla scheda Consigli, compare qui. Segna poi l\'esito per vedere come va rispetto alle previsioni.',
        el('a', { class: 'pulsante', href: '#/consigli' }, 'Vai ai consigli')));
      return radice;
    }
    radice.append(el('div', { class: 'riepilogo' },
      el('div', {}, el('div', { class: 'v num ' + (s.profitto_unita >= 0 ? 'pos' : 'neg') }, `${segno(s.profitto_unita)} u`),
        el('div', { class: 'e' }, `profitto reale (${segno(profittoEuro, 2)} €) su ${s.unita_giocate} unità giocate`)),
      el('div', {}, el('div', { class: 'v num' }, s.roi === null ? '–' : segno(s.roi * 100, 1) + '%'), el('div', { class: 'e' }, 'rendimento reale (ROI)')),
      el('div', {}, el('div', { class: 'v num' }, s.roi_atteso === null ? '–' : segno(s.roi_atteso * 100, 1) + '%'), el('div', { class: 'e' }, 'rendimento stimato dalle previsioni')),
      el('div', {}, el('div', { class: 'v num' }, `${s.vinte} su ${s.n_chiuse}`),
        el('div', { class: 'e' }, `vinte (attese circa ${s.vinte_attese.toFixed(1).replace('.', ',')}); ancora aperte: ${s.n_aperte}`))));
    if (s.n_chiuse < 100) radice.append(el('p', { class: 'piccolo tenue' }, `Con ${s.n_chiuse} giocate chiuse la differenza tra reale e previsto è soprattutto casualità: servono almeno un centinaio di giocate per dire se le previsioni funzionano.`));
    const ordine = stato.giocate.slice().sort((a, b) => (a.stato === 'aperta' ? 0 : 1) - (b.stato === 'aperta' ? 0 : 1) || b.creata.localeCompare(a.creata));
    const imposta = (g, nuovo) => { A.impostaEsito(stato, g.id, nuovo); salva(); route(); };
    radice.append(el('div', { class: 'sezione' }, ...ordine.map((g) => {
      const prof = A.profittoUnita(g), multipla = g.tipo === 'multipla';
      return el('div', { class: 'voce' },
        el('div', { class: 'titolo' }, el('span', { class: 'chip ' + g.stato }, maiuscola(g.stato)), multipla ? 'Multipla' : g.eventi[0].etichetta),
        multipla ? el('ul', { class: 'lista-piana' }, ...g.eventi.map((e) => el('li', {}, `${e.etichetta} @ ${q2(e.quota)}`))) : null,
        el('div', { class: 'dati' }, el('span', {}, 'quota ', el('b', { class: 'num' }, q2(g.quota))),
          el('span', {}, 'puntata ', el('b', { class: 'num' }, `${g.unita} u (${eur(g.importo)})`)),
          el('span', {}, 'prob. stimata ', el('b', { class: 'num' }, pct(g.prob, 1))),
          g.stato === 'vinta' || g.stato === 'persa' ? el('span', {}, 'esito ', el('b', { class: 'num ' + (prof >= 0 ? 'pos' : 'neg') }, `${segno(prof)} u`)) : null,
          el('span', {}, new Date(g.creata).toLocaleDateString('it-IT'))),
        el('div', { class: 'azioni' },
          g.stato === 'aperta' ? [
            el('button', { onclick: () => imposta(g, 'vinta') }, 'Vinta'),
            el('button', { class: 'secondario', onclick: () => imposta(g, 'persa') }, 'Persa'),
            el('button', { class: 'leggero', onclick: async () => {
              if (await conferma('Annullare la giocata?', 'La puntata torna nel bankroll (per esempio se la partita è stata rinviata).', 'Annulla giocata')) imposta(g, 'annullata');
            } }, 'Annulla')]
            : el('button', { class: 'leggero', onclick: () => imposta(g, 'aperta') }, 'Riapri'),
          el('button', { class: 'leggero', onclick: async () => {
            if (await conferma('Eliminare la giocata?', 'Sparisce dallo storico e dai conti. Non si può annullare.', 'Elimina', true)) { A.eliminaGiocata(stato, g.id); salva(); route(); }
          } }, 'Elimina')));
    })));
    return radice;
  }

  // ------------------------------------------------------------------ conto e impostazioni
  function vistaConto() {
    const radice = el('div', {}, el('h2', {}, 'Conto'));
    const u = stato.impostazioni.valore_unita, budget = stato.impostazioni.budget_mensile, mese = oggiISO().slice(0, 7);
    if (soloMemoria) radice.append(el('div', { class: 'banner' }, el('strong', {}, 'Salvataggio non disponibile. '),
      'Il browser blocca la memoria del sito (navigazione privata?): i dati si perdono alla chiusura. Fai una copia di sicurezza qui sotto.'));
    radice.append(el('div', { class: 'riepilogo' },
      el('div', {}, el('div', { class: 'v num' }, eur(A.saldo(stato))), el('div', { class: 'e' }, 'bankroll disponibile')),
      el('div', {}, el('div', { class: 'v num' }, String(saldoUnita())), el('div', { class: 'e' }, `unità disponibili (1 unità = ${eur(u)})`))));
    const gia = A.versatoNelMese(stato, mese);
    radice.append(el('div', { class: 'azioni' }, el('button', { class: gia ? 'secondario' : '', onclick: async () => {
      if (gia && !(await conferma('Hai già versato questo mese', 'Il piano è un solo versamento al mese. Vuoi aggiungerne un altro?', 'Versa comunque'))) return;
      A.versa(stato, budget, oggiISO(), 'Budget mensile'); salva(); avviso('Versamento registrato'); route();
    } }, `Versa ${eur(budget)} del mese`)));
    if (!gia) radice.append(el('p', { class: 'piccolo tenue' }, 'Non hai ancora versato il budget di questo mese. Il bankroll è denaro dedicato solo alle giocate: se finisce, si aspetta il mese dopo.'));
    if (stato.versamenti.length) radice.append(el('details', { class: 'sezione' }, el('summary', {}, `Versamenti (${stato.versamenti.length})`),
      ...stato.versamenti.slice().reverse().slice(0, 12).map((v) => el('div', { class: 'voce' },
        `${new Date(v.data + 'T12:00:00').toLocaleDateString('it-IT')} · `, el('b', { class: 'num' }, eur(v.importo)), v.nota ? ' · ' + v.nota : ''))));

    const campoNum = (nomeCampo, chiave, min, step, nota) => {
      const i = el('input', { type: 'number', min, step, inputmode: 'decimal', value: stato.impostazioni[chiave] });
      i.addEventListener('change', () => {
        const v = numero(i.value);
        if (v >= min) { stato.impostazioni[chiave] = v; salva(); avviso('Salvato'); } else i.value = stato.impostazioni[chiave];
      });
      return el('div', { class: 'campo' }, el('label', {}, el('b', {}, nomeCampo)), i, nota ? el('div', { class: 'piccolo tenue' }, nota) : null);
    };
    radice.append(el('div', { class: 'sezione' }, el('h2', {}, 'Impostazioni'),
      campoNum('Valore di una unità (€)', 'valore_unita', 0.5, 0.5, 'Controlla la puntata minima del tuo bookmaker prima di cambiarlo. Con 30 € al mese, 1 unità = 1 € è circa il 3% del bankroll iniziale.'),
      campoNum('Budget mensile (€)', 'budget_mensile', 1, 1, null),
      el('p', { class: 'piccolo tenue' }, 'Il peso del modello si regola nella scheda di ogni partita (consigliato 10%).')));
    if (dati) {
      const par = parametri();
      radice.append(el('details', { class: 'sezione' }, el('summary', {}, 'Regole in uso'), el('ul', { class: 'lista-piana' },
        el('li', {}, `Verde se il valore atteso supera +${pct(par.soglie.soglia_valore)} (1X2, doppia chance, Under/Over 2,5) o +${pct(par.soglie.soglia_senza_mercato)} (Multigol, GG/NG, altre linee) e modello e mercato non differiscono di più di ${Math.round(par.soglie.soglia_disaccordo * 100)} punti.`),
        el('li', {}, `Una giocata per partita, massimo ${par.puntate.tetto} unità al giorno; multipla di al massimo ${par.puntate.max_multipla} eventi, sempre 1 unità.`),
        el('li', {}, `2 unità solo con valore sopra +${pct(par.puntate.valore_alto)}, quota di mercato diretta e quota fino a ${q2(par.puntate.quota_max_due)}.`),
        el('li', {}, `Pausa di revisione se in 7 giorni perdi ${par.puntate.pausa} unità.`))));
    }
    const fileInput = el('input', { type: 'file', accept: 'application/json,.json', hidden: true });
    fileInput.addEventListener('change', async () => {
      const f = fileInput.files[0];
      if (!f) return;
      try {
        const nuovo = A.importa(await f.text());
        if (await conferma('Ripristinare la copia?', `Sostituisce tutti i dati di questo telefono con quelli del file (${nuovo.giocate.length} giocate).`, 'Ripristina', true)) {
          stato = nuovo; salva(); avviso('Copia ripristinata'); route();
        }
      } catch (e) { avviso(e.message); }
      fileInput.value = '';
    });
    radice.append(el('div', { class: 'sezione' }, el('h2', {}, 'I tuoi dati'),
      el('p', { class: 'tenue' }, 'Bankroll, quote inserite e giocate restano solo su questo telefono, nel browser: non vengono inviati a nessun server e non sono nel repository pubblico. Se cancelli i dati del sito o cambi telefono si perdono: fai ogni tanto una copia.'),
      el('div', { class: 'azioni' },
        el('button', { class: 'secondario', onclick: () => {
          const url = URL.createObjectURL(new Blob([A.esporta(stato)], { type: 'application/json' }));
          const a = el('a', { href: url, download: `schedine-copia-${oggiISO()}.json` });
          document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 3000);
        } }, 'Salva copia'),
        el('button', { class: 'secondario', onclick: () => fileInput.click() }, 'Ripristina copia'),
        el('button', { class: 'leggero', onclick: async () => {
          if (await conferma('Cancellare tutti i dati?', 'Bankroll, quote e giocate di questo telefono vengono eliminati. Non si può annullare.', 'Cancella tutto', true)) {
            stato = A.statoIniziale(); salva(); avviso('Dati cancellati'); route();
          }
        } }, 'Cancella tutto')), fileInput));
    radice.append(el('div', { class: 'sezione' }, el('h2', {}, 'Gioco responsabile'),
      el('p', {}, 'Il bankroll è denaro dedicato solo alle giocate, separato da quello di tutti i giorni, che puoi permetterti di perdere interamente. I bookmaker tengono un margine su ogni quota: nel lungo periodo è un costo, e un modello statistico non lo elimina.'),
      el('p', {}, 'Se senti di non controllare il gioco chiama il Telefono Verde Nazionale per il gioco d\'azzardo: ', el('a', { href: 'tel:800558822' }, '800 55 88 22'), ', gratuito e anonimo.')));
    radice.append(el('p', { class: 'piccolo tenue' }, 'Per installare l\'app: dal menu del browser scegli «Installa app» o «Aggiungi a schermata Home».'));
    return radice;
  }

  // ------------------------------------------------------------------ navigazione
  function route() {
    const h = location.hash || '#/';
    let tab = 'partite', contenuto;
    try {
      const m = h.match(/^#\/partita\/(.+)$/);
      if (m) contenuto = vistaPartita(decodeURIComponent(m[1]));
      else if (h === '#/consigli') { tab = 'consigli'; contenuto = vistaConsigli(); }
      else if (h === '#/giocate') { tab = 'giocate'; contenuto = vistaGiocate(); }
      else if (h === '#/conto') { tab = 'conto'; contenuto = vistaConto(); }
      else contenuto = vistaPartite();
    } catch (e) {
      console.error(e);
      contenuto = vuoto('Qualcosa non ha funzionato', `Errore: ${e.message}. Ricarica la pagina; se si ripete, fai una copia dei dati dal Conto.`, el('button', { onclick: () => location.reload() }, 'Ricarica'));
    }
    document.querySelectorAll('.schede a').forEach((a) => { if (a.dataset.tab === tab) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    const y = window.scrollY, stessa = route.ultima === h;
    vista.replaceChildren(contenuto);
    window.scrollTo(0, stessa ? y : 0);
    route.ultima = h;
  }

  function aggiornaTestata() {
    const t = document.getElementById('aggiornato');
    if (erroreDati || !dati) { t.textContent = 'Consigli non disponibili'; return; }
    const quando = new Date(dati.generato).toLocaleString('it-IT', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    t.textContent = `${dati.partite.length} partite · aggiornato ${quando}${dati.demo ? ' · DATI DI PROVA' : ''}`;
  }

  async function start() {
    try {
      const r = await fetch('data/consigli.json', { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const d = await r.json();
      if (!d || !Array.isArray(d.partite)) throw new Error('formato inatteso');
      dati = d; erroreDati = null; memo.anc.clear(); memo.rif.clear();
      A.pulisciQuote(stato, d.partite.map((p) => p.id)); salva();
    } catch (e) { erroreDati = e.message; }
    aggiornaTestata(); route();
  }

  stato = carica();
  window.addEventListener('hashchange', route);
  const fondo = document.querySelector('.fondo');
  const misura = () => document.documentElement.style.setProperty('--fondo-h', fondo.offsetHeight + 'px');
  if (window.ResizeObserver) new ResizeObserver(misura).observe(fondo); else window.addEventListener('resize', misura);
  misura();
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost')) navigator.serviceWorker.register('sw.js').catch(() => {});
  start();
})();

/* Service worker: l'app funziona anche senza rete.
 * - file dell'app: dalla cache, aggiornati in background (alla visita successiva si vede la versione nuova);
 * - data/consigli.json: prima la rete, se manca si usa l'ultimo scaricato.
 * La versione viene scritta dal workflow (sostituisce __VERSIONE__ con l'identificativo del commit). */
const VERSIONE = '__VERSIONE__';
const CACHE = 'schedine-' + VERSIONE;
const FILE = ['./', 'index.html', 'css/stile.css', 'js/motore.js', 'js/parser_quote.js', 'js/archivio.js', 'js/app.js',
  'manifest.webmanifest', 'icone/icona-192.png', 'icone/icona-512.png', 'icone/favicon-32.png', 'icone/icona-apple-180.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(FILE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys().then((chiavi) => Promise.all(chiavi.filter((k) => k.startsWith('schedine-') && k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== self.location.origin) return;
  if (new URL(req.url).pathname.endsWith('/data/consigli.json')) {
    e.respondWith(fetch(req, { cache: 'no-store' }).then((r) => {
      if (r.ok) { const copia = r.clone(); caches.open(CACHE).then((c) => c.put(req, copia)); }
      return r;
    }).catch(() => caches.match(req)));
    return;
  }
  e.respondWith(caches.match(req, { ignoreSearch: true }).then((inCache) => {
    const rete = fetch(req).then((r) => {
      if (r.ok) { const copia = r.clone(); caches.open(CACHE).then((c) => c.put(req, copia)); }
      return r;
    }).catch(() => inCache);
    return inCache || rete;
  }));
});

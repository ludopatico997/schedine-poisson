# App Schedine Poisson

PWA per consigli sulle schedine calcistiche basata su modelli statistici (Dixon-Coles, Elo) e ricerca di value bet. Progetto personale, a costo zero. Non garantisce profitti: il gioco può causare dipendenza, gioca solo ciò che puoi permetterti di perdere.

## Struttura
- `engine/`   motore Python: download dati, modelli, value bet, puntate
- `backtest/` backtest walk-forward e metriche
- `app/`      PWA (HTML/CSS/JS + service worker)
- `data/`     output pubblicabile (`consigli.json`); `data/raw/` = CSV scaricati, NON versionati
- `docs/`     note tecniche
- `.github/workflows/` automazione giornaliera

## Automazione (passo 9)
`.github/workflows/consigli.yml` gira ogni giorno (e a mano da Actions): installa le dipendenze, esegue i test, scarica i CSV storici,
genera `data/consigli.json` con le quote di The Odds API, lo controlla (`engine/controlla_consigli.py`: niente chiavi nel file,
probabilita' coerenti) e pubblica `app/` + `consigli.json` su GitHub Pages. Nulla viene committato dal workflow.

Impostazione una tantum:
1. Settings > Secrets and variables > Actions > New repository secret: `ODDS_API_KEY` = la chiave (mai nel codice).
2. Settings > Pages > Build and deployment > Source: **GitHub Actions**.
3. Actions > Consigli giornalieri > Run workflow (prima con "solo_verifica_chiavi", poi con la sorgente `demo`, poi `odds-api`).

Nota: GitHub disattiva i workflow programmati dei repository pubblici dopo 60 giorni senza attivita'; basta riattivarlo da Actions.

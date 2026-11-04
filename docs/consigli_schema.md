# Formato di `consigli.json`

Generato da `engine/genera_consigli.py` (ogni giorno, via GitHub Actions) e letto dalla PWA. **Pubblico**: contiene solo
probabilita' e quote minime calcolate. Nessuna quota di bookmaker, nessun dato personale, nessuna chiave.

```
versione, demo (true = solo prova), generato (UTC), avviso_gioco, avvisi[]
modello:    nome ("ens"), parametri, stimato_fino_a
parametri:  peso_modello (default 0.10), soglie {valore_mercato_diretto 0.02, valore_senza_mercato 0.08, disaccordo 0.10},
            puntate {unita_euro, tetto_giornaliero_unita, pausa_dopo_perdita_unita, max_eventi_multipla, kelly_frazione,
                     valore_alto_due_unita, quota_max_due_unita}, mercati_diretti[]
partite[]:  id, campionato, nome_campionato, inizio (UTC), casa, ospite
            modello:    lam, mu, rho, squadre_note      -> gol attesi del modello (ricalcolo della matrice nell'app)
            mercato:    fonte, n_bookmaker, prob{1,X,2,Over 2.5,Under 2.5}   (probabilita' senza margine) | null
            riferimento: peso_modello, fonte, disaccordo, probabilita{tutti i mercati}, quota_equa{...}, quota_minima{...}
```

Nell'app: l'utente inserisce la quota del suo bookmaker (a mano o con "incolla e leggi");
valore = probabilita' x quota - 1; semaforo come in `engine/riferimento.py`; puntate come in `engine/puntate.py`.
Con il cursore del peso del modello l'app ricalcola le probabilita' partendo da `modello` e `mercato.prob`.

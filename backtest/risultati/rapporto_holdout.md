# Backtest walk-forward - holdout

Parametri: {'emivita': 270.0, 'ridge': 3.0, 'blocco_giorni': 30}
Periodo: 2024-08-15 -> 2026-01-14  |  partite 1X2: 3120  |  partite Under/Over: 3093
Partite con squadre sconosciute al modello (neopromosse senza storico): 0.9%

## Qualita' delle probabilita' (piu' basso = meglio)

```
    metrica      n  modello  mercato   base  modello-mercato   ic95
1x2_logloss 3120.0   1.0004   0.9752 1.0763           0.0252 0.0059
  1x2_brier 3120.0   0.5975   0.5810 0.6517           0.0164 0.0040
 ou_logloss 3093.0   0.6866   0.6749 0.6897           0.0117 0.0050
   ou_brier 3093.0   0.2466   0.2410 0.2483           0.0057 0.0024
```

'modello-mercato' < 0 significa modello migliore del mercato; 'ic95' e' la meta' larghezza dell'intervallo al 95%.
Se l'intervallo include lo zero, la differenza non e' distinguibile dal caso.

## Log-loss per campionato

```
campionato   n  1X2 modello  1X2 mercato  O/U modello  O/U mercato  O/U base
        D1 455       0.9998       0.9660       0.6627       0.6497    0.6723
        E0 590       0.9902       0.9739       0.6814       0.6795    0.6867
        F1 459       0.9794       0.9564       0.6900       0.6735    0.6907
        I1 578       0.9912       0.9648       0.6953       0.6832    0.6997
        I2 470       1.0799       1.0509       0.7158       0.6998    0.6923
       SP1 568       0.9721       0.9470       0.6746       0.6616    0.6930
```

## Log-loss per stagione

```
stagione    n  1X2 modello  1X2 mercato  O/U modello  O/U mercato  O/U base
 2024/25 2132       1.0026       0.9764       0.6849       0.6724    0.6896
 2025/26  988       0.9957       0.9725       0.6904       0.6804    0.6898
```

## Log-loss secondo la conoscenza delle squadre

```
               note    n  1X2 modello  1X2 mercato  O/U modello  O/U mercato  O/U base
squadra sconosciuta   27       0.9290       0.8606       0.7055       0.6874    0.7111
       squadre note 3093       1.0010       0.9762       0.6865       0.6748    0.6895
```

## Calibrazione 1X2 (probabilita' prevista vs frequenza osservata)

```
   n  prevista  mercato  osservata  errore_modello  errore_mercato
1170    0.1524   0.1433     0.1316          0.0208          0.0117
1170    0.2228   0.2230     0.2393         -0.0165         -0.0163
1170    0.2545   0.2562     0.2393          0.0152          0.0169
1170    0.2827   0.2817     0.2932         -0.0105         -0.0114
1170    0.3137   0.3069     0.3026          0.0112          0.0044
1170    0.3701   0.3655     0.3615          0.0086          0.0039
1170    0.4563   0.4612     0.4538          0.0024          0.0073
1170    0.6141   0.6288     0.6453         -0.0312         -0.0165
```

## ROI simulato (1 unita' per scommessa, sull'esito col maggior edge, a quote Pinnacle)

ATTENZIONE: quote Pinnacle = ideale. Un bookmaker italiano ha margini piu' alti e limiti di puntata.
Piu' soglie e piu' mercati provati = piu' probabilita' di trovare un risultato buono per puro caso.

### 1X2 - quote di chiusura

```
 soglia_edge  scommesse  vinte_%  profitto_unita  ROI_%  ic95_%
     -1.0000       3120     26.6          -357.0  -11.4  6.1787
      0.0000       2982     25.8          -345.1  -11.6  6.3929
      0.0200       2821     25.4          -309.7  -11.0  6.6638
      0.0500       2485     23.4          -343.6  -13.8  7.2586
      0.0800       2191     22.0          -344.3  -15.7  7.8531
      0.1000       1987     20.6          -360.3  -18.1  8.3629
```

### 1X2 - quote di apertura

```
 soglia_edge  scommesse  vinte_%  profitto_unita  ROI_%  ic95_%
     -1.0000       3120     26.4          -447.8  -14.4  5.7809
      0.0000       2895     25.6          -409.9  -14.2  6.1000
      0.0200       2660     24.2          -425.4  -16.0  6.4258
      0.0500       2288     22.6          -421.8  -18.4  7.0495
      0.0800       1932     22.0          -349.2  -18.1  7.8256
      0.1000       1740     20.7          -359.7  -20.7  8.3167
```

### Under/Over 2.5 - quote di chiusura

```
 soglia_edge  scommesse  vinte_%  profitto_unita   ROI_%  ic95_%
     -1.0000       3093     47.7          -140.9 -4.5545  3.6782
      0.0000       2519     47.5           -88.2 -3.4994  4.1298
      0.0200       2143     46.0          -113.2 -5.2804  4.5162
      0.0500       1690     44.9           -90.3 -5.3414  5.1879
      0.0800       1289     44.0           -65.6 -5.0908  6.0600
      0.1000       1067     44.5           -30.4 -2.8500  6.7416
```

### Under/Over 2.5 - quote di apertura

```
 soglia_edge  scommesse  vinte_%  profitto_unita   ROI_%  ic95_%
     -1.0000       3091     49.1          -123.6 -3.9971  3.5852
      0.0000       2409     48.7           -84.1 -3.4890  4.1073
      0.0200       2021     47.7           -76.6 -3.7892  4.5478
      0.0500       1519     46.1           -73.8 -4.8611  5.3480
      0.0800       1077     46.4           -28.0 -2.6026  6.4547
      0.1000        864     45.5           -37.0 -4.2836  7.2078
```

# Confronto modelli - holdout 2024-08-01 -> 2026-12-31

Modello scelto sul periodo di taratura: **ens** (2021-08-01 -> 2024-07-31)
Parametri candidati: dc={'emivita_giorni': 270.0, 'ridge': 3.0}, elo={'k': 20.0, 'vantaggio_casa': 40.0, 'regressione': 0.05}, ens={'k': 20.0, 'vantaggio_casa': 40.0, 'regressione': 0.05, 'peso_elo': 0.5, 'dc': {'emivita_giorni': 270.0, 'ridge': 3.0}}

Partite 1X2: 3120

## Log-loss (piu' basso = meglio)

```
modello    1X2    O/U  1X2 - dc  ic95 vs dc  1X2 - mercato  ic95 vs mercato
     dc 1.0004 0.6866    0.0000      0.0000         0.0252           0.0059
    elo 1.0006 0.6835    0.0001      0.0041         0.0254           0.0062
    ens 0.9987 0.6833   -0.0017      0.0020         0.0235           0.0057
mercato 0.9752 0.6749       NaN         NaN            NaN              NaN
   base 1.0763 0.6897       NaN         NaN            NaN              NaN
```

## Il modello aggiunge informazione al mercato? (peso scelto sull'holdout stesso: ottimistico)

```
modello          dc    elo    ens
peso_modello                     
0.00         0.9752 0.9752 0.9752
0.05         0.9758 0.9757 0.9757
0.10         0.9764 0.9763 0.9763
0.20         0.9779 0.9778 0.9778
0.30         0.9797 0.9795 0.9795
0.50         0.9842 0.9840 0.9836
```
(log-loss 1X2 della miscela mercato/modello)

```
modello          dc    elo    ens
peso_modello                     
0.00         0.6749 0.6749 0.6749
0.05         0.6750 0.6749 0.6749
0.10         0.6751 0.6750 0.6750
0.20         0.6756 0.6752 0.6753
0.30         0.6763 0.6756 0.6758
0.50         0.6782 0.6770 0.6772
```
(log-loss Under/Over 2.5 della miscela)

## dc: log-loss per campionato

```
campionato   n  1X2 modello  1X2 mercato  O/U modello  O/U mercato  O/U base
        D1 455       0.9998       0.9660       0.6627       0.6497    0.6723
        E0 590       0.9902       0.9739       0.6814       0.6795    0.6867
        F1 459       0.9794       0.9564       0.6900       0.6735    0.6907
        I1 578       0.9912       0.9648       0.6953       0.6832    0.6997
        I2 470       1.0799       1.0509       0.7158       0.6998    0.6923
       SP1 568       0.9721       0.9470       0.6746       0.6616    0.6930
```

## elo: log-loss per campionato

```
campionato   n  1X2 modello  1X2 mercato  O/U modello  O/U mercato  O/U base
        D1 455       1.0015       0.9660       0.6641       0.6497    0.6723
        E0 590       0.9896       0.9739       0.6827       0.6795    0.6867
        F1 459       0.9747       0.9564       0.6874       0.6735    0.6907
        I1 578       0.9900       0.9648       0.6892       0.6832    0.6997
        I2 470       1.0882       1.0509       0.6974       0.6998    0.6923
       SP1 568       0.9702       0.9470       0.6788       0.6616    0.6930
```

## ens: log-loss per campionato

```
campionato   n  1X2 modello  1X2 mercato  O/U modello  O/U mercato  O/U base
        D1 455       0.9990       0.9660       0.6612       0.6497    0.6723
        E0 590       0.9890       0.9739       0.6808       0.6795    0.6867
        F1 459       0.9765       0.9564       0.6871       0.6735    0.6907
        I1 578       0.9885       0.9648       0.6907       0.6832    0.6997
        I2 470       1.0790       1.0509       0.7051       0.6998    0.6923
       SP1 568       0.9706       0.9470       0.6742       0.6616    0.6930
```

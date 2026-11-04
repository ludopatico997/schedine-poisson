# Verifica mercati derivati - holdout

Partite: 3120  |  periodo 2024-08-15 -> 2026-01-14
Errore massimo dell'ancoraggio alle quote (probabilita'): medio 0.0109, massimo 0.0453

## Log-loss per mercato (piu' basso = meglio)

```
              freq_reale   base   puro  mercato  misto migliore
1                 0.4247 0.6816 0.6175   0.5989 0.5997  mercato
X                 0.2660 0.5770 0.5720   0.5689 0.5690  mercato
2                 0.3093 0.6176 0.5630   0.5461 0.5469  mercato
1X                0.6907 0.6176 0.5630   0.5461 0.5469  mercato
X2                0.5753 0.6816 0.6175   0.5989 0.5997  mercato
12                0.7340 0.5770 0.5720   0.5689 0.5690  mercato
GG                0.5446 0.6914 0.6920   0.6881 0.6879    misto
NG                0.4554 0.6914 0.6920   0.6881 0.6879    misto
Over 0.5          0.9333 0.2457 0.2428   0.2398 0.2398  mercato
Under 0.5         0.0667 0.2457 0.2428   0.2398 0.2398  mercato
Over 1.5          0.7654 0.5443 0.5394   0.5319 0.5320  mercato
Under 1.5         0.2346 0.5443 0.5394   0.5319 0.5320  mercato
Over 2.5          0.5186 0.6894 0.6844   0.6729 0.6732  mercato
Under 2.5         0.4814 0.6894 0.6844   0.6729 0.6732  mercato
Over 3.5          0.3016 0.6052 0.5985   0.5883 0.5884  mercato
Under 3.5         0.6984 0.6052 0.5985   0.5883 0.5884  mercato
Over 4.5          0.1385 0.3972 0.3899   0.3819 0.3819  mercato
Under 4.5         0.8615 0.3972 0.3899   0.3819 0.3819  mercato
Multigol 1-2      0.4147 0.6758 0.6729   0.6669 0.6670  mercato
Multigol 1-3      0.6317 0.6527 0.6496   0.6458 0.6457    misto
Multigol 1-4      0.7949 0.5053 0.5046   0.5030 0.5029    misto
Multigol 1-5      0.8728 0.3809 0.3817   0.3816 0.3815    misto
Multigol 2-3      0.4638 0.6899 0.6897   0.6898 0.6896    misto
Multigol 2-4      0.6269 0.6614 0.6623   0.6623 0.6622    misto
Multigol 2-5      0.7048 0.6073 0.6087   0.6064 0.6064  mercato
Multigol 2-6      0.7439 0.5690 0.5670   0.5631 0.5631  mercato
Multigol 3-5      0.4580 0.6888 0.6902   0.6839 0.6842  mercato
Multigol 3-6      0.4971 0.6910 0.6889   0.6806 0.6809  mercato
```

'base' = frequenze storiche; 'puro' = solo Dixon-Coles; 'mercato' = gol attesi dalle quote;
'misto' = mercato + 10% modello.

## Disaccordo modello-mercato (max differenza di probabilita' su 1, X, 2)

Log-loss 1X2 sulle sole partite con disaccordo oltre la soglia:

```
 disaccordo_>  partite  quota_%  logloss_modello  logloss_mercato  modello-mercato   ic95
       0.0000     3120 100.0000           1.0004           0.9752           0.0252 0.0059
       0.0500     2302  73.7821           1.0015           0.9661           0.0353 0.0078
       0.0800     1397  44.7756           1.0000           0.9527           0.0472 0.0117
       0.1000      913  29.2628           1.0176           0.9605           0.0570 0.0164
       0.1200      582  18.6538           1.0206           0.9426           0.0781 0.0222
       0.1500      254   8.1410           1.0627           0.9406           0.1221 0.0400
       0.2000       45   1.4423           1.0765           0.8089           0.2677 0.1131
```

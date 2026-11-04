#!/usr/bin/env python3
"""Genera le icone della PWA (disegno originale: istogramma di Poisson con l'ultima barra evidenziata).
    python3 app/icone/genera_icone.py        # richiede Pillow
"""
from math import exp, factorial
from pathlib import Path

from PIL import Image, ImageDraw

CARTELLA = Path(__file__).resolve().parent
INCHIOSTRO, CARTA, ACCENTO, EVIDENZA = (19, 33, 43), (232, 237, 240), (92, 192, 222), (111, 215, 159)


def disegna(lato: int, maschera: bool) -> Image.Image:
    s = 4                                                    # supercampionamento per bordi lisci
    L = lato * s
    img = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    raggio = 0 if maschera else int(L * 0.22)                # icona "maskable": sfondo pieno, il sistema ritaglia
    d.rounded_rectangle([0, 0, L - 1, L - 1], radius=raggio, fill=INCHIOSTRO)
    margine = L * (0.26 if maschera else 0.17)               # zona sicura piu' ampia per la maschera
    area = L - 2 * margine
    lam, n = 1.6, 7
    pmf = [exp(-lam) * lam ** k / factorial(k) for k in range(n)]
    alto = max(pmf)
    larg = area / n
    for k, p in enumerate(pmf):
        h = area * 0.82 * p / alto
        x0 = margine + k * larg + larg * 0.14
        x1 = margine + (k + 1) * larg - larg * 0.14
        y1 = margine + area
        colore = EVIDENZA if k == 3 else ACCENTO
        d.rounded_rectangle([x0, y1 - h, x1, y1], radius=larg * 0.12, fill=colore)
    d.line([margine, margine + area + L * 0.02, margine + area, margine + area + L * 0.02], fill=CARTA, width=max(2, int(L * 0.012)))
    return img.resize((lato, lato), Image.LANCZOS)


if __name__ == "__main__":
    for nome, lato, maschera in [("icona-192.png", 192, False), ("icona-512.png", 512, False), ("icona-maschera-512.png", 512, True),
                                 ("icona-apple-180.png", 180, False), ("favicon-32.png", 32, False)]:
        disegna(lato, maschera).save(CARTELLA / nome)
        print("scritto", nome)

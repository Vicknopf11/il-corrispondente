#!/usr/bin/env python3
"""
Il Corrispondente Artificiale — Generatore di immagini OG per i permalink
Per ogni articolo genera un'immagine 1200x630 (formato standard OG/Twitter
card) con categoria, titolo ed estratto — uno "screenshot ricostruito",
non un vero screenshot del browser: niente Chromium in CI, solo Pillow.
Se la generazione fallisce per qualsiasi motivo, il chiamante deve
ricadere sull'immagine di copertina generica (mai bloccare la pipeline
per un'immagine mancante).
"""

import os
import re
import textwrap

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "docs/assets/fonts"
OG_IMG_DIR = "docs/assets/og"

LARGHEZZA, ALTEZZA = 1200, 630

COLORI_CATEGORIA = {
    "internazionale": "#2c3e50",
    "nazionale": "#c0392b",
    "economia": "#27ae60",
    "sport": "#2980b9",
    "cronaca": "#8e44ad",
}
COLORE_DEFAULT = "#c0392b"

CREMA = "#f5f0e8"
NERO = "#1a1a1a"
BIANCO = "#ffffff"
GRIGIO_TESTO = "#222222"
GRIGIO_CHIARO = "#999999"


def _font(nome: str, dimensione: int) -> ImageFont.FreeTypeFont:
    path = os.path.join(FONT_DIR, nome)
    return ImageFont.truetype(path, dimensione)


def _wrap_su_larghezza(draw: ImageDraw.ImageDraw, testo: str, font: ImageFont.FreeTypeFont,
                        larghezza_max: int, righe_max: int) -> list[str]:
    """Word-wrap manuale basato sulla larghezza reale del testo renderizzato
    (non un conteggio di caratteri a stima), troncando con ellissi se il
    testo supera le righe massime disponibili."""
    parole = testo.split()
    righe = []
    riga_corrente = ""

    for parola in parole:
        prova = f"{riga_corrente} {parola}".strip()
        larghezza_prova = draw.textbbox((0, 0), prova, font=font)[2]
        if larghezza_prova <= larghezza_max:
            riga_corrente = prova
        else:
            if riga_corrente:
                righe.append(riga_corrente)
            riga_corrente = parola
            if len(righe) >= righe_max:
                break

    if riga_corrente and len(righe) < righe_max:
        righe.append(riga_corrente)

    # Se il testo non è finito ed eravamo già alla riga massima, aggiunge l'ellissi
    testo_racchiuso = " ".join(righe)
    if len(testo_racchiuso) < len(testo) and righe:
        ultima = righe[-1]
        while ultima and draw.textbbox((0, 0), ultima + "…", font=font)[2] > larghezza_max:
            ultima = ultima[:-1].rstrip()
        righe[-1] = ultima + "…"

    return righe[:righe_max]


def slug_categoria(cat: str) -> str:
    if not cat:
        return ""
    c = cat.lower()
    if "intern" in c:
        return "internazionale"
    if "naz" in c:
        return "nazionale"
    if "econ" in c:
        return "economia"
    if "sport" in c:
        return "sport"
    if "cron" in c:
        return "cronaca"
    return ""


def _pulisci_estratto(testo: str) -> str:
    return re.sub(r"\s+", " ", testo or "").strip()


def genera_immagine_og(post: dict, percorso_output: str) -> None:
    """Genera e salva l'immagine OG per un articolo. Solleva eccezione in
    caso di errore — il chiamante decide il fallback, questa funzione non
    lo nasconde per non mascherare problemi (es. font mancanti)."""
    categoria = post.get("categoria", "")
    cat_slug = slug_categoria(categoria)
    colore_cat = COLORI_CATEGORIA.get(cat_slug, COLORE_DEFAULT)

    titolo = post.get("titolo", "")
    estratto = _pulisci_estratto(post.get("post_sito") or post.get("post_x", ""))

    img = Image.new("RGB", (LARGHEZZA, ALTEZZA), CREMA)
    draw = ImageDraw.Draw(img)

    # ── Fascia superiore, mastate della testata ──────────────────
    ALTEZZA_HEADER = 84
    draw.rectangle([0, 0, LARGHEZZA, ALTEZZA_HEADER], fill=NERO)
    draw.rectangle([0, ALTEZZA_HEADER, LARGHEZZA, ALTEZZA_HEADER + 6], fill=COLORE_DEFAULT)

    font_masthead = _font("PTSans-Bold.ttf", 30)
    masthead = "IL CORRISPONDENTE ARTIFICIALE"
    bbox = draw.textbbox((0, 0), masthead, font=font_masthead)
    larghezza_testo = bbox[2] - bbox[0]
    draw.text(((LARGHEZZA - larghezza_testo) / 2, 24), masthead, font=font_masthead, fill=CREMA)

    # ── Card bianca centrale ──────────────────────────────────────
    MARGINE_X = 64
    CARD_TOP = ALTEZZA_HEADER + 6 + 40
    CARD_BOTTOM = ALTEZZA - 50
    BORDO_SINISTRO = 8

    draw.rectangle([MARGINE_X, CARD_TOP, LARGHEZZA - MARGINE_X, CARD_BOTTOM], fill=BIANCO)
    draw.rectangle([MARGINE_X, CARD_TOP, MARGINE_X + BORDO_SINISTRO, CARD_BOTTOM], fill=colore_cat)

    PADDING_INTERNO = 44
    x_testo = MARGINE_X + BORDO_SINISTRO + PADDING_INTERNO
    larghezza_testo_max = LARGHEZZA - MARGINE_X - x_testo - PADDING_INTERNO
    y = CARD_TOP + 36

    # Etichetta categoria
    font_label = _font("PTSans-Bold.ttf", 22)
    label_testo = categoria.upper()
    bbox_label = draw.textbbox((0, 0), label_testo, font=font_label)
    lw, lh = bbox_label[2] - bbox_label[0], bbox_label[3] - bbox_label[1]
    draw.rectangle([x_testo, y, x_testo + lw + 28, y + lh + 22], fill=colore_cat)
    draw.text((x_testo + 14, y + 8), label_testo, font=font_label, fill=BIANCO)
    y += lh + 22 + 28

    # Titolo
    font_titolo = _font("PTSerif-Bold.ttf", 46)
    righe_titolo = _wrap_su_larghezza(draw, titolo, font_titolo, larghezza_testo_max, righe_max=3)
    for riga in righe_titolo:
        draw.text((x_testo, y), riga, font=font_titolo, fill=GRIGIO_TESTO)
        y += 56
    y += 18

    # Estratto — le righe disponibili dipendono da quanto spazio ha
    # occupato il titolo sopra: non è un numero fisso, per evitare che
    # un titolo lungo (3 righe) faccia sovrapporre l'estratto alla firma.
    ALTEZZA_RIGA_ESTRATTO = 40
    Y_FIRMA = CARD_BOTTOM - 44
    SPAZIO_PRIMA_DELLA_FIRMA = 16
    spazio_disponibile = Y_FIRMA - SPAZIO_PRIMA_DELLA_FIRMA - y
    righe_max_estratto = max(1, min(4, spazio_disponibile // ALTEZZA_RIGA_ESTRATTO))

    font_estratto = _font("PTSerif-Regular.ttf", 28)
    righe_estratto = _wrap_su_larghezza(draw, estratto, font_estratto, larghezza_testo_max,
                                         righe_max=righe_max_estratto)
    for riga in righe_estratto:
        draw.text((x_testo, y), riga, font=font_estratto, fill="#444444")
        y += ALTEZZA_RIGA_ESTRATTO

    # Firma in basso nella card
    font_firma = _font("PTSerif-Italic.ttf", 22)
    firma = "Il Corrispondente Artificiale — corrispondente.filoclastos.it"
    draw.text((x_testo, Y_FIRMA), firma, font=font_firma, fill=GRIGIO_CHIARO)

    os.makedirs(os.path.dirname(percorso_output), exist_ok=True)
    img.save(percorso_output, "PNG")

#!/usr/bin/env python3
"""
Il Corrispondente Artificiale — Generatore automatico di prompt.html

Legge SYSTEM_PROMPT e PROMPT_UTENTE_TEMPLATE direttamente da genera.py e li
inietta in docs/prompt.html, sostituendo solo i due blocchi "prompt-box"
(System Prompt e Prompt utente). Il resto della pagina — header, CSS, note,
footer — resta intatto.

Questo garantisce che la pagina di trasparenza non possa disallinearsi dal
prompt reale usato in produzione: se SYSTEM_PROMPT cambia in genera.py,
prompt.html si aggiorna da solo alla prossima esecuzione della pipeline.
"""

import re

PROMPT_FILE = "docs/prompt.html"


def esc(s: str) -> str:
    return (str(s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def testo_a_html(testo: str) -> str:
    """Converte un blocco di testo (SYSTEM_PROMPT o prompt utente) nella
    stessa struttura semantica HTML usata finora in prompt.html:
    - righe '━━━ TITOLO ━━━'           -> <p class="separatore">
    - righe 'N. TITOLO'                -> <p class="num">
    - righe TUTTE MAIUSCOLE indentate  -> <p class="sub">
    - righe che iniziano con '- '      -> raggruppate in <ul><li>...
      (le righe di continuazione avvolte su più righe vengono riunite
      allo stesso <li>)
    - blocco che inizia con '{' a indentazione zero e termina con '}' alla
      stessa indentazione -> <pre> preformattato (es. lo schema JSON)
    - paragrafi indentati (nested)     -> <p class="indent">
    - paragrafi non indentati (flat)   -> <p> semplice
    """
    righe = testo.split("\n")
    html = []
    buffer = []
    buffer_indentato = False
    lista_corrente = []
    blocco_json = None

    def flush_lista():
        nonlocal lista_corrente
        if lista_corrente:
            items = "".join(f"<li>{esc(i)}</li>" for i in lista_corrente)
            html.append(f"<ul>{items}</ul>")
            lista_corrente = []

    def flush_paragrafo():
        nonlocal buffer, buffer_indentato
        if buffer:
            unito = " ".join(s.strip() for s in buffer)
            classe = ' class="indent"' if buffer_indentato else ""
            html.append(f"<p{classe}>{esc(unito)}</p>")
            buffer = []
            buffer_indentato = False

    for riga in righe:
        stripped = riga.strip()
        indentata = (len(riga) - len(riga.lstrip())) > 0

        if blocco_json is not None:
            blocco_json.append(riga)
            if stripped == "}" and not indentata:
                html.append(f"<pre>{esc(chr(10).join(blocco_json))}</pre>")
                blocco_json = None
            continue

        if stripped == "{" and not indentata:
            flush_lista()
            flush_paragrafo()
            blocco_json = [riga]
            continue

        if stripped == "":
            flush_lista()
            flush_paragrafo()
            continue

        if re.match(r"^━━━.*━━━$", stripped):
            flush_lista()
            flush_paragrafo()
            html.append(f'<p class="separatore">{esc(stripped)}</p>')
            continue

        if re.match(r"^\d+\.\s", stripped):
            flush_lista()
            flush_paragrafo()
            html.append(f'<p class="num">{esc(stripped)}</p>')
            continue

        if stripped.startswith("- "):
            flush_paragrafo()
            lista_corrente.append(stripped[2:].strip())
            continue

        if lista_corrente:
            # continuazione di un bullet avvolto su più righe nel testo sorgente
            lista_corrente[-1] = lista_corrente[-1] + " " + stripped
            continue

        if indentata and stripped.isupper() and len(stripped) > 1:
            flush_paragrafo()
            html.append(f'<p class="sub">{esc(stripped)}</p>')
            continue

        buffer.append(stripped)
        if indentata:
            buffer_indentato = True

    flush_lista()
    flush_paragrafo()
    if blocco_json is not None:
        html.append(f"<pre>{esc(chr(10).join(blocco_json))}</pre>")
    return "\n      ".join(html)


def sostituisci_prompt_box(pagina: str, label: str, contenuto_html: str) -> str:
    pattern = re.compile(
        r'(<div class="prompt-box">\s*<span class="label">'
        + re.escape(label) + r"</span>)(.*?)(</div>)",
        re.S,
    )

    def repl(m):
        return f"{m.group(1)}\n      {contenuto_html}\n    {m.group(3)}"

    nuova, n = pattern.subn(repl, pagina, count=1)
    if n == 0:
        raise ValueError(
            f"Blocco prompt-box con label '{label}' non trovato in {PROMPT_FILE} — "
            "controlla che la struttura HTML non sia cambiata."
        )
    return nuova


def main():
    import genera  # importa SYSTEM_PROMPT e PROMPT_UTENTE_TEMPLATE dal codice reale

    categorie_str = "\n".join(f"- {c}" for c in genera.CATEGORIE)
    prompt_utente = genera.PROMPT_UTENTE_TEMPLATE.format(categorie_str=categorie_str)

    html_sistema = testo_a_html(genera.SYSTEM_PROMPT.strip())
    html_utente = testo_a_html(prompt_utente.strip())

    with open(PROMPT_FILE, encoding="utf-8") as f:
        pagina = f.read()

    pagina_nuova = sostituisci_prompt_box(pagina, "System Prompt", html_sistema)
    pagina_nuova = sostituisci_prompt_box(pagina_nuova, "Prompt utente (template)", html_utente)

    if pagina_nuova != pagina:
        with open(PROMPT_FILE, "w", encoding="utf-8") as f:
            f.write(pagina_nuova)
        print("✓ prompt.html rigenerato dal codice sorgente (contenuto cambiato)")
    else:
        print("✓ prompt.html già sincronizzato con il codice sorgente — nessuna modifica")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
Builds the interactive HTML version of the Francés 2° de Secundaria Libro Abierto.
See LIBROS/INGLES/1ro Secundaria - Interactivo/tools/build.py for full documentation
of how this pipeline works (page rendering, language-classified text blocks,
pre-baked neural-voice audio). This is the same script, retargeted to this book.
"""
import asyncio
import fitz
import hashlib
import json
import os
import re
import sys

import edge_tts
from langdetect import DetectorFactory, detect
DetectorFactory.seed = 0

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC_PDF = os.path.join(r"C:\Trabajo - Salome Ureña\LIBROS\FRANCES", "Lenguas Extranjeras - Francés 2° Secundaria (Libro Abierto).pdf")
PAGES_DIR = os.path.join(ROOT, "pages")
DATA_DIR = os.path.join(ROOT, "data")
AUDIO_DIR = os.path.join(ROOT, "audio")
TARGET_LANG = "fr"
VOICE = "fr-FR-DeniseNeural"
ZOOM = 2.0
JPEG_QUALITY = 85
AUDIO_CONCURRENCY = 12

SKIP_ALWAYS = [
    "ministerio de educación",
    "república dominicana",
    "todos los derechos reservados",
    "prohibida su venta",
    "libroabierto.minerd.gob.do",
]


def clean_for_detect(text):
    text = re.sub(r"[■●►•\t\xad]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_speakable(text):
    cleaned = clean_for_detect(text)
    low = cleaned.lower()
    if any(marker in low for marker in SKIP_ALWAYS):
        return False
    letters = re.sub(r"[^A-Za-zÀ-ÿ]", "", cleaned)
    if len(letters) < 3:
        return False
    try:
        lang = detect(cleaned)
    except Exception:
        return False
    return lang == TARGET_LANG


LIST_MARKER_RE = re.compile(r"^(\d{1,3}|[a-zA-Z])[.)]\s")
END_PUNCT_RE = re.compile(r"[.!?:\u2026]\s*$")


def _clean_line_text(raw):
    t = re.sub(r"[■●►\t\xad]", " ", raw)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _get_raw_blocks(page):
    """List of PyMuPDF blocks, each a list of {bbox, text} *lines* (not yet merged),
    in PyMuPDF's own order (spatially clustered — same region stays consecutive)."""
    d = page.get_text("dict")
    blocks = []
    for block in d["blocks"]:
        if "lines" not in block:
            continue
        lines = []
        for line in block["lines"]:
            line_text = "".join(span["text"] for span in line["spans"])
            cleaned = _clean_line_text(line_text)
            if cleaned:
                lines.append({"bbox": list(line["bbox"]), "text": cleaned})
        if lines:
            blocks.append(lines)
    return blocks


def _intra_block_cluster(lines):
    """Merge/split the lines *within one PyMuPDF block* into logical units. Uses
    the block's own max line-width as the "did this line reach the margin"
    reference for deciding a continuation — safe to do here (unlike page-wide)
    because it's scoped to lines PyMuPDF already grouped as one block, so it can't
    be skewed by an unrelated wide paragraph elsewhere on the page. This is what
    splits a table (PyMuPDF sometimes fuses a whole sparse table + the paragraph
    after it into one block) into one unit per cell/row instead of one giant blob."""
    if not lines:
        return []
    block_max_x1 = max(ln["bbox"][2] for ln in lines)
    units = []
    for ln in lines:
        merged = False
        if units:
            prev = units[-1]
            last = prev["last_line"]
            gap = ln["bbox"][1] - last["bbox"][3]
            x0_diff = abs(ln["bbox"][0] - last["bbox"][0])
            prev_open = not END_PUNCT_RE.search(prev["text"])
            reached_margin = last["bbox"][2] >= block_max_x1 - 15
            starts_new_item = bool(LIST_MARKER_RE.match(ln["text"]))
            if (-20 <= gap <= 8 and x0_diff <= 35 and prev_open
                    and reached_margin and not starts_new_item):
                prev["text"] = (prev["text"] + " " + ln["text"]).strip()
                prev["bbox"][0] = min(prev["bbox"][0], ln["bbox"][0])
                prev["bbox"][1] = min(prev["bbox"][1], ln["bbox"][1])
                prev["bbox"][2] = max(prev["bbox"][2], ln["bbox"][2])
                prev["bbox"][3] = max(prev["bbox"][3], ln["bbox"][3])
                prev["last_line"] = ln
                merged = True
        if not merged:
            units.append({"bbox": list(ln["bbox"]), "text": ln["text"], "last_line": ln})
    return units


def extract_blocks(page):
    """Text units for a page: bbox + text, one per paragraph/dialogue-turn/cell.
    Two passes: (1) re-cluster lines *within* each PyMuPDF block (fixes tables/lists
    PyMuPDF fused with a trailing paragraph into one block); (2) a capped one-hop
    merge *across* a block boundary for the case PyMuPDF splits one paragraph into
    two blocks — recognizable by a hanging-indent wrapped line PyMuPDF treats as a
    new block (e.g. "...practice with a" / "partner" as two separate blocks). The
    cross-block merge is gated on the earlier unit being a substantial fragment
    (>=20 chars) so it can't fire on short standalone labels like "Name"/"Age" that
    also happen to lack trailing punctuation.
    """
    raw_blocks = _get_raw_blocks(page)
    block_units = [_intra_block_cluster(lines) for lines in raw_blocks]

    flat = []
    for units in block_units:
        for ui, u in enumerate(units):
            merged = False
            if flat and ui == 0 and not flat[-1].get("cross_merged"):
                prev = flat[-1]
                last = prev["last_line"]
                gap = u["bbox"][1] - last["bbox"][3]
                x0_diff = abs(u["bbox"][0] - last["bbox"][0])
                prev_open = not END_PUNCT_RE.search(prev["text"])
                starts_new_item = bool(LIST_MARKER_RE.match(u["text"]))
                is_short = len(u["text"]) <= 40
                prev_substantial = len(prev["text"]) >= 20
                if (-20 <= gap <= 10 and x0_diff <= 40 and prev_open
                        and not starts_new_item and is_short and prev_substantial):
                    prev["text"] = (prev["text"] + " " + u["text"]).strip()
                    prev["bbox"][0] = min(prev["bbox"][0], u["bbox"][0])
                    prev["bbox"][1] = min(prev["bbox"][1], u["bbox"][1])
                    prev["bbox"][2] = max(prev["bbox"][2], u["bbox"][2])
                    prev["bbox"][3] = max(prev["bbox"][3], u["bbox"][3])
                    prev["last_line"] = u["last_line"]
                    prev["cross_merged"] = True
                    merged = True
            if not merged:
                flat.append(u)

    return [{"bbox": [round(v, 1) for v in u["bbox"]], "text": u["text"]} for u in flat]


def clean_for_speech(text):
    text = re.sub(r"(^|\s)(\d{1,3}|[a-zA-Z])[.)]\s+", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def audio_filename(text):
    h = hashlib.sha1((VOICE + "|" + text).encode("utf-8")).hexdigest()[:16]
    return h + ".mp3"


async def generate_audio_files(texts):
    os.makedirs(AUDIO_DIR, exist_ok=True)
    todo = []
    for text in texts:
        fname = audio_filename(text)
        path = os.path.join(AUDIO_DIR, fname)
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            todo.append((text, path))

    print("audio: %d unique clips needed, %d already cached, %d to generate" % (
        len(texts), len(texts) - len(todo), len(todo)))

    sem = asyncio.Semaphore(AUDIO_CONCURRENCY)
    done_count = [0]

    async def gen_one(text, path):
        async with sem:
            for attempt in range(3):
                try:
                    communicate = edge_tts.Communicate(text, VOICE)
                    await communicate.save(path)
                    break
                except Exception as e:
                    if attempt == 2:
                        print("FAILED after 3 attempts:", text[:50], "->", e)
                    else:
                        await asyncio.sleep(1.5)
            done_count[0] += 1
            if done_count[0] % 100 == 0:
                print("  audio progress:", done_count[0], "/", len(todo))

    await asyncio.gather(*(gen_one(t, p) for t, p in todo))


# Every "Libro Abierto Serie 2" book inspected (all 4 English grades, all 3 French
# grades) opens its 6 units at exactly these page numbers -- confirmed by hand while
# mapping the book's units to our own temas before this interactive-viewer work
# started. Hardcoding beats text-sniffing "Unit Content"/"Contenu": the English pilot
# build hit a false positive from a miniature page-preview reproduced (text layer and
# all) on the book's own "how this book works" explainer page, and nothing rules out
# an equivalent explainer page tripping up a text-based heuristic in another book.
UNIT_OPENER_PAGES = [11, 25, 39, 53, 67, 81]


def main():
    if not os.path.exists(SRC_PDF):
        print("PDF not found:", SRC_PDF)
        sys.exit(1)

    os.makedirs(PAGES_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    doc = fitz.open(SRC_PDF)
    mat = fitz.Matrix(ZOOM, ZOOM)

    pages_out = []
    units = []
    speakable_count = 0
    total_blocks = 0

    for i, page in enumerate(doc):
        page_no = i + 1
        pix = page.get_pixmap(matrix=mat)
        img_name = "page-%03d.jpg" % page_no
        pix.save(os.path.join(PAGES_DIR, img_name), jpg_quality=JPEG_QUALITY)

        blocks = extract_blocks(page)
        if page_no in UNIT_OPENER_PAGES:
            units.append({"unit": len(units) + 1, "page": page_no})

        out_blocks = []
        for b in blocks:
            speak = is_speakable(b["text"])
            total_blocks += 1
            block_out = {
                "bbox": b["bbox"],
                "text": b["text"],
                "speak": speak,
            }
            if speak:
                spoken_text = clean_for_speech(b["text"]) or b["text"]
                block_out["audio"] = "audio/" + audio_filename(spoken_text)
                speakable_count += 1
            out_blocks.append(block_out)

        pages_out.append({
            "page": page_no,
            "image": "pages/" + img_name,
            "width": round(page.rect.width, 1),
            "height": round(page.rect.height, 1),
            "blocks": out_blocks,
        })

        if page_no % 10 == 0:
            print("processed page", page_no, "/", len(doc))

    unique_texts = set()
    for p in pages_out:
        for b in p["blocks"]:
            if b["speak"]:
                unique_texts.add(clean_for_speech(b["text"]) or b["text"])
    asyncio.run(generate_audio_files(unique_texts))

    payload = {"lang": TARGET_LANG, "totalPages": len(doc), "units": units, "pages": pages_out}

    with open(os.path.join(DATA_DIR, "pages.js"), "w", encoding="utf-8") as f:
        f.write("window.BOOK_DATA = ")
        json.dump(payload, f, ensure_ascii=False)
        f.write(";")

    print("done.", len(doc), "pages,", total_blocks, "text blocks,", speakable_count, "marked speakable (%s)" % TARGET_LANG)
    print("units found:", units)


if __name__ == "__main__":
    main()

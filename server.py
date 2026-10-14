"""PaperTalkthrough local server.

Runs on your own computer. It:
  - turns a PDF into numbered sentences (PyMuPDF + pysbd)
  - speaks text with the free, offline Kokoro voice
  - forwards your questions to the AI through your API key (OpenAI-compatible gateway)
  - saves your reading position, highlights, notes and call history in ./library

Start it with:  python server.py   then open http://localhost:8000
"""
import bisect
import hashlib
import heapq
import itertools
import io
import json
import os
import re
import shutil
import traceback
import threading
import wave
import webbrowser
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np
import pymupdf
import pysbd
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from openai import OpenAI
from pydantic import BaseModel

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
LIB = ROOT / "library"
LIB.mkdir(exist_ok=True)
MODEL_DIR = ROOT / "models"

BASE_URL = os.getenv("OPENAI_BASE_URL") or None
API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("MODEL", "gpt-4o-mini")
DEFAULT_VOICE = os.getenv("VOICE", "af_heart")
PORT = int(os.getenv("PORT", "8000"))
# Send the whole document to the AI when it's shorter than this many characters (about 4 characters per token).
# 400,000 characters is roughly 100,000 tokens, which fits Claude, GPT and Gemini models. Set to 0 to always send excerpts only.
FULL_DOC_MAX_CHARS = int(os.getenv("FULL_DOC_MAX_CHARS", "400000"))
WEB_SEARCH = os.getenv("WEB_SEARCH", "on").lower() not in ("off", "0", "no", "false")
# Optional: a model on your gateway that can use Google Search through a "google_search" tool
# (for example a Gemini model behind a Portkey gateway). Empty = use the free search fallbacks.
WEB_SEARCH_MODEL = os.getenv("WEB_SEARCH_MODEL", "")

# Portkey-based gateways read the key from an extra header; other providers just use the normal one
_extra_headers = {"x-portkey-api-key": API_KEY} if BASE_URL and "portkey" in BASE_URL else None
client = OpenAI(base_url=BASE_URL, api_key=API_KEY or "missing", default_headers=_extra_headers)
app = FastAPI()

# ---------------------------------------------------------------- voice (Kokoro)
_kokoro = None
_kokoro_lock = threading.Lock()
_tts_cache: "OrderedDict[tuple, bytes]" = OrderedDict()
# Speech always goes first: page drawing pauses while any speech is being generated
_tts_busy = 0
_tts_busy_lock = threading.Lock()


def kokoro():
    global _kokoro
    if _kokoro is None:
        onnx, voices = MODEL_DIR / "kokoro-v1.0.onnx", MODEL_DIR / "voices-v1.0.bin"
        if not (onnx.exists() and voices.exists()):
            raise HTTPException(503, "Voice model files are missing. Run: python download_models.py")
        from kokoro_onnx import Kokoro
        _kokoro = Kokoro(str(onnx), str(voices))
    return _kokoro


def to_wav(samples, sr) -> bytes:
    pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class TTSReq(BaseModel):
    text: str
    voice: str = DEFAULT_VOICE
    speed: float = 1.0
    session: str = ""  # one per open browser tab
    gen: int = 0       # goes up every time you jump, stop or interrupt; older requests are dropped
    prio: int = 0      # 0 = needed right now, 1 = getting the next sentences ready


# Speech queue: one voice generation at a time, most urgent first, and anything
# from before your latest jump is thrown away instead of making you wait.
_sched = threading.Condition()
_queue = []
_running = False
_seq = itertools.count()
_latest_gen = {}


def take_turn(session, gen, prio):
    global _running
    item = (prio, next(_seq))
    with _sched:
        if gen > _latest_gen.get(session, -1):
            _latest_gen[session] = gen
            _sched.notify_all()
        heapq.heappush(_queue, item)
        try:
            while True:
                if gen < _latest_gen.get(session, -1):
                    return False
                if not _running and _queue[0] == item:
                    _running = True
                    return True
                _sched.wait(0.2)
        finally:
            if item in _queue:
                _queue.remove(item)
                heapq.heapify(_queue)


def end_turn():
    global _running
    with _sched:
        _running = False
        _sched.notify_all()


@app.post("/api/tts")
def tts(req: TTSReq):
    text = req.text.strip()[:2000]
    if not text:
        raise HTTPException(400, "No text")
    key = (text, req.voice, round(req.speed, 2))
    if key in _tts_cache:
        _tts_cache.move_to_end(key)
        return Response(_tts_cache[key], media_type="audio/wav")
    global _tts_busy
    k = kokoro()
    with _tts_busy_lock:
        _tts_busy += 1
    try:
        if not take_turn(req.session, req.gen, req.prio):
            if key in _tts_cache:
                return Response(_tts_cache[key], media_type="audio/wav")
            raise HTTPException(409, "No longer needed")
        try:
            if key in _tts_cache:  # the same words were just made while this request waited
                return Response(_tts_cache[key], media_type="audio/wav")
            samples, sr = k.create(text, voice=req.voice, speed=max(0.5, min(2.0, req.speed)), lang="en-us")
        finally:
            end_turn()
    finally:
        with _tts_busy_lock:
            _tts_busy -= 1
    data = to_wav(samples, sr)
    _tts_cache[key] = data
    while len(_tts_cache) > 300:
        _tts_cache.popitem(last=False)
    return Response(data, media_type="audio/wav")


# ---------------------------------------------------------------- PDF -> sentences (+ where each word sits on the page)
_seg = pysbd.Segmenter(language="en", clean=False, char_span=True)


def norm(t: str) -> str:
    return re.sub(r"\d+", "#", t.lower()).strip()


def words_to_text(ws, pno):
    """Join a block's words into text, remembering each word's character span and box."""
    text, spans, prev = "", [], None
    for w in ws:
        t = w[4].replace("\u00ad", "")
        if not t:
            continue
        if prev is not None:
            new_line = (w[5], w[6]) != (prev[5], prev[6])
            if new_line and re.search(r"[A-Za-z]-$", prev[4]) and t[:1].islower():
                text = text[:-1]  # re-join a word hyphenated across a line break
                spans[-1][1] -= 1
            else:
                text += " "
        start = len(text)
        text += t
        spans.append([start, len(text), pno, w[0], w[1], w[2], w[3]])
        prev = w
    return text, spans


PARSER_VERSION = 2
MONO_FONT = re.compile(r"mono|courier|typewriter|cmtt|consol|menlo|inconsolata|lmmono|nimbusmono|sourcecode|firacode", re.I)
CAPTION = re.compile(r"^(figure|fig\.|table|tab\.|algorithm|listing|chart)\s*[A-Z]?\d+(\.\d+)?\s*[:.|]", re.I)
ENDS_SENTENCE = re.compile(r"[.!?:;\"”')\]]$")


def block_kind(text, size, mono, body):
    """None for normal body text; otherwise caption / code / table / small (footnotes, labels inside figures...)."""
    if CAPTION.match(text):
        return "caption"
    if mono > 0.5:
        return "code"
    symbols = sum(text.count(c) for c in "(){}[];=<>_\\") / max(1, len(text))
    if symbols > 0.07 and re.search(r"=>|\(\)|\);|\w\(\w*[,)']", text):
        return "code"
    toks = text.split()
    if len(toks) >= 4 and sum(1 for t in toks if re.fullmatch(r"[\d.,%±+\-–()/]+", t)) / len(toks) > 0.4:
        return "table"
    if size and body and size < body * 0.85:
        return "small"
    return None


def parse_pdf(data: bytes):
    pdf = pymupdf.open(stream=data, filetype="pdf")
    pages, sizes, size_hist = [], [], Counter()
    for pno, page in enumerate(pdf, 1):
        sizes.append([round(page.rect.width, 1), round(page.rect.height, 1)])
        # font size and monospace share for every block (block numbers match the word list)
        fonts = {}
        for b in page.get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            chars = size_sum = mono = 0
            for line in b["lines"]:
                for sp in line["spans"]:
                    c = len(sp["text"].strip())
                    if not c:
                        continue
                    chars += c
                    size_sum += sp["size"] * c
                    if MONO_FONT.search(sp["font"]) or sp["flags"] & 8:
                        mono += c
                    size_hist[round(sp["size"] * 2) / 2] += c
            fonts[b["number"]] = (size_sum / chars, mono / chars) if chars else (0, 0)
        groups, order = {}, []
        for w in page.get_text("words"):
            if w[5] not in groups:
                groups[w[5]] = []
                order.append(w[5])
            groups[w[5]].append(w)
        blocks = []
        for b in order:
            ws = groups[b]
            text, spans = words_to_text(ws, pno)
            if text.strip():
                blocks.append((min(w[1] for w in ws), max(w[3] for w in ws), text, spans, *fonts.get(b, (0, 0))))
        pages.append((page.rect.height, blocks))
    body = size_hist.most_common(1)[0][0] if size_hist else 0

    # Running headers/footers: same text near the top/bottom edge on several pages
    edge_count = Counter()
    for h, blocks in pages:
        for y0, y1, t, *_ in blocks:
            if y1 < h * 0.08 or y0 > h * 0.92:
                edge_count[norm(t)] += 1
    need = min(3, max(2, len(pages) // 2))

    # Build paragraphs. Captions, tables, code and small print that interrupt an unfinished sentence
    # are held back and placed after that sentence ends, so the sentence reads as one.
    paras, held = [], []  # [page, text, spans, kind]
    for pno, (h, blocks) in enumerate(pages, 1):
        for y0, y1, t, spans, size, mono in blocks:
            if (y1 < h * 0.08 or y0 > h * 0.92) and (edge_count[norm(t)] >= need or re.fullmatch(r"[\d\s\-–|]{1,8}", t)):
                continue
            kind = block_kind(t, size, mono, body)
            open_sentence = paras and paras[-1][3] is None and not ENDS_SENTENCE.search(paras[-1][1])
            if kind:
                (held if open_sentence else paras).append([pno, t, spans, kind])
                continue
            if open_sentence and re.match(r"[a-z(]", t):
                off = len(paras[-1][1]) + 1
                paras[-1][1] += " " + t
                paras[-1][2] += [[a + off, b + off, *rest] for a, b, *rest in spans]
                if held and ENDS_SENTENCE.search(paras[-1][1]):
                    paras += held
                    held = []
            else:
                paras += held
                held = []
                paras.append([pno, t, spans, None])
    paras += held

    sents, words = [], []
    for g, (pno, text, spans, kind) in enumerate(paras):
        pieces = []
        for ts in _seg.segment(text):
            a, b = ts.start, ts.end
            chunk = text[a:b]
            a += len(chunk) - len(chunk.lstrip())
            b -= len(chunk) - len(chunk.rstrip())
            if b <= a:
                continue
            if pieces and (b - a <= 3 or re.fullmatch(r"[\d\W]+", text[a:b])):
                pieces[-1][1] = b
            else:
                pieces.append([a, b])
        if kind in ("code", "table") and pieces:   # don't chop code or tables into "sentences"
            pieces = [[pieces[0][0], pieces[-1][1]]]
        for a, b in pieces:
            i = len(sents)
            ws = [sp for sp in spans if sp[0] >= a and sp[1] <= b]
            sent = {"t": text[a:b], "p": ws[0][2] if ws else pno, "g": g}
            if kind:
                sent["k"] = kind
            sents.append(sent)
            for sa, sb, wp, x0, y0, x1, y1 in ws:
                words.append([i, sa - a, sb - a, wp, round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)])
    return sents, {"pages": sizes, "words": words}


def doc_path(doc_id):
    if not re.fullmatch(r"[a-f0-9]{16}", doc_id):
        raise HTTPException(400, "Bad document id")
    return LIB / f"{doc_id}.json", LIB / f"{doc_id}.state.json"


def extra_paths(doc_id):
    doc_path(doc_id)
    return LIB / f"{doc_id}.pdf", LIB / f"{doc_id}.geo.json", LIB / doc_id


def load_doc(doc_id):
    p, _ = doc_path(doc_id)
    if not p.exists():
        raise HTTPException(404, "Document not found")
    doc = json.loads(p.read_text("utf-8"))
    if doc.get("v", 1) < PARSER_VERSION:
        doc = reparse(doc_id, doc)
    return doc


def reparse(doc_id, doc):
    """Re-read a stored PDF with the newer parser, moving position, highlights and notes onto the new text."""
    p, st = doc_path(doc_id)
    pdf_p, geo_p, _ = extra_paths(doc_id)
    if not pdf_p.exists():
        return doc
    try:
        sents, geo = parse_pdf(pdf_p.read_bytes())
    except Exception:
        traceback.print_exc()
        return doc
    old = doc["sents"]
    state = load_state(doc_id)
    if old:
        op = max(0, min(state.get("pos", 0), len(old) - 1))
        where = locate(sents, old[op]["t"][:150], op)
        state["pos"] = where[0] if where else 0
    kept = []
    for h in state.get("hls", []):
        where = locate(sents, h.get("text", ""), h.get("s1", 0))
        if where:
            h["s1"], h["o1"], h["s2"], h["o2"] = where
            kept.append(h)
    if len(kept) < len(state.get("hls", [])):
        print(f"[reparse] {len(state['hls']) - len(kept)} highlight(s) couldn't be matched to the new text", flush=True)
    state["hls"] = kept
    doc.update(sents=sents, v=PARSER_VERSION)
    p.write_text(json.dumps(doc, ensure_ascii=False), "utf-8")
    geo_p.write_text(json.dumps(geo, separators=(",", ":")), "utf-8")
    st.write_text(json.dumps(state, ensure_ascii=False), "utf-8")
    print(f"[reparse] '{doc['title']}' updated to the improved text layout", flush=True)
    return doc


def load_state(doc_id):
    _, s = doc_path(doc_id)
    if s.exists():
        return json.loads(s.read_text("utf-8"))
    return {"pos": 0, "hls": [], "chat": []}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    doc_id = hashlib.sha1(data).hexdigest()[:16]
    p, _ = doc_path(doc_id)
    pdf_p, geo_p, _ = extra_paths(doc_id)
    if p.exists() and geo_p.exists():
        load_doc(doc_id)  # brings older documents up to date
    else:
        try:
            sents, geo = parse_pdf(data)
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(400, f"This PDF couldn't be opened ({e}).")
        if not sents:
            raise HTTPException(400, "No text found. This looks like a scanned PDF; it needs OCR first.")
        title = re.sub(r"\.pdf$", "", file.filename or "Untitled", flags=re.I)
        p.write_text(json.dumps({"id": doc_id, "title": title, "sents": sents, "v": PARSER_VERSION}, ensure_ascii=False), "utf-8")
        geo_p.write_text(json.dumps(geo, separators=(",", ":")), "utf-8")
        pdf_p.write_bytes(data)
    return {"id": doc_id}


@app.delete("/api/doc/{doc_id}")
def delete_doc(doc_id: str):
    p, st = doc_path(doc_id)
    pdf_p, geo_p, cache = extra_paths(doc_id)
    for f in (p, st, pdf_p, geo_p):
        if f.exists():
            f.unlink()
    shutil.rmtree(cache, ignore_errors=True)
    return {"ok": True}


@app.get("/api/geo/{doc_id}")
def get_geo(doc_id: str):
    _, geo_p, _ = extra_paths(doc_id)
    if not geo_p.exists():
        raise HTTPException(404, "Open this PDF again to enable page view and export.")
    prerender(doc_id)
    return FileResponse(geo_p, media_type="application/json")


_render_lock = threading.Lock()  # draw one page at a time
_prerendering = set()


def wait_for_speech(limit=4.0):
    """Let speech generation finish first (up to `limit` seconds)."""
    import time
    waited = 0.0
    while _tts_busy and waited < limit:
        time.sleep(0.05)
        waited += 0.05


def render_page(pdf_p, cache, n):
    img = cache / f"p{n}.png"
    if img.exists():
        return img
    wait_for_speech()
    with _render_lock:
        if not img.exists():
            pdf = pymupdf.open(pdf_p)
            if not 1 <= n <= len(pdf):
                raise HTTPException(404, "No such page")
            tmp = cache / f"p{n}.tmp.png"
            pdf[n - 1].get_pixmap(dpi=150).save(tmp)
            os.replace(tmp, img)
    return img


def prerender(doc_id):
    """Quietly draw every page in the background so page view is instant later."""
    if doc_id in _prerendering:
        return
    _prerendering.add(doc_id)

    def work():
        import time
        try:
            pdf_p, _, cache = extra_paths(doc_id)
            if not pdf_p.exists():
                return
            cache.mkdir(exist_ok=True)
            count = len(pymupdf.open(pdf_p))
            for n in range(1, count + 1):
                render_page(pdf_p, cache, n)
                time.sleep(0.02)
        except Exception:
            traceback.print_exc()
        finally:
            _prerendering.discard(doc_id)

    threading.Thread(target=work, daemon=True).start()


@app.get("/api/page/{doc_id}/{n}")
def page_image(doc_id: str, n: int):
    pdf_p, _, cache = extra_paths(doc_id)
    if not pdf_p.exists():
        raise HTTPException(404, "Original PDF not stored")
    cache.mkdir(exist_ok=True)
    img = render_page(pdf_p, cache, n)
    return FileResponse(img, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


HL_COLORS = {1: (0.80, 0.72, 0.96), 2: (0.70, 0.89, 0.67), 3: (0.68, 0.80, 0.95), 4: (0.96, 0.70, 0.78)}


def line_rects(rects):
    """Merge word boxes on the same line into one rectangle per line."""
    out = []
    for r in rects:
        if out and abs(out[-1].y0 - r.y0) < 2 and 0 <= r.x0 - out[-1].x1 < 20:
            out[-1] |= r
        else:
            out.append(pymupdf.Rect(r))
    return out


@app.get("/api/export/{doc_id}")
def export(doc_id: str):
    from urllib.parse import quote

    pdf_p, geo_p, _ = extra_paths(doc_id)
    if not (pdf_p.exists() and geo_p.exists()):
        raise HTTPException(404, "Open this PDF again (Open a PDF) to enable export.")
    title = load_doc(doc_id)["title"]
    words = json.loads(geo_p.read_text("utf-8"))["words"]
    keys = [(w[0], w[1]) for w in words]
    pdf = pymupdf.open(pdf_p)
    for h in load_state(doc_id).get("hls", []):
        by_page = {}
        for w in words[bisect.bisect_left(keys, (h["s1"], -1)):]:
            s, cs, ce = w[0], w[1], w[2]
            if s > h["s2"] or (s == h["s2"] and cs >= h["o2"]):
                break
            if s == h["s1"] and ce <= h["o1"]:
                continue
            by_page.setdefault(w[3], []).append(pymupdf.Rect(w[4:8]))
        for k, (pg, rects) in enumerate(sorted(by_page.items())):
            page = pdf[pg - 1]  # keep the page object alive while its annotation is edited
            annot = page.add_highlight_annot(line_rects(rects))
            annot.set_colors(stroke=HL_COLORS.get(h.get("c", 1), HL_COLORS[1]))
            if h.get("note") and k == 0:
                annot.set_info(content=h["note"], title="PaperTalkthrough")
            annot.update()
    data = pdf.tobytes(garbage=3, deflate=True)
    name = quote(f"{title} - notes.pdf")
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"})


@app.get("/api/library")
def library():
    out = []
    for p in sorted(LIB.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.name.endswith((".state.json", ".geo.json")):
            continue
        d = json.loads(p.read_text("utf-8"))
        st = load_state(d["id"])
        out.append({"id": d["id"], "title": d["title"], "pos": st.get("pos", 0), "total": len(d["sents"])})
    return out


@app.get("/api/doc/{doc_id}")
def get_doc(doc_id: str):
    return {"doc": load_doc(doc_id), "state": load_state(doc_id)}


@app.post("/api/state/{doc_id}")
def save_state(doc_id: str, state: dict):
    _, s = doc_path(doc_id)
    state["chat"] = state.get("chat", [])[-200:]
    s.write_text(json.dumps(state, ensure_ascii=False), "utf-8")
    return {"ok": True}


# ---------------------------------------------------------------- AI conversation
STOP = set("""the and for that this with from have what does did they them their there were was are is
about into which when where who why how can could would should will your you our not but also more
than then just like its it's been being any some such these those mean means said says paper text
article author authors here sentence last part use used using""".split())


def retrieve(sents, question, exclude, k=8):
    words = {w for w in re.findall(r"[a-z][a-z\-]{2,}", question.lower()) if w not in STOP}
    if not words:
        return []
    scored = []
    for i, s in enumerate(sents):
        if i in exclude:
            continue
        tl = s["t"].lower()
        sc = sum(1 for w in words if w in tl)
        if sc:
            scored.append((sc, -i, i))
    return sorted(i for _, _, i in sorted(scored, reverse=True)[:k])


# ---------------------------------------------------------------- web search for the AI
WEB_TOOLS = [
    {"type": "function", "function": {
        "name": "web_search",
        "description": "Search the web for specialist background knowledge the document doesn't give: definitions, methods, statistics, people, organisations, news. Returns titles, links and short snippets.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "A short search query, in English for academic topics"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "search_papers",
        "description": "Search scholarly papers (OpenAlex): find a paper, its authors, venue, year, citation count and abstract, related or follow-up work, or other papers by the same authors.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "Title words, topic, or author name"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "read_web_page",
        "description": "Read the main text of a web page (for example one found with web_search) when the snippets aren't enough.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
]
UA = {"User-Agent": "PaperTalkthrough/1.0 (personal study tool; https://github.com/)"}


class _Resp:
    def __init__(self, body, charset):
        self.text = body.decode(charset or "utf-8", errors="replace")

    def json(self):
        return json.loads(self.text)


def _http_get(url, params=None):
    """Plain GET using only Python's built-in tools (no extra packages needed)."""
    import urllib.parse
    import urllib.request
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={**UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return _Resp(r.read(3_000_000), r.headers.get_content_charset())


def wikipedia_search(query, n=4):
    import html as _html
    data = _http_get("https://en.wikipedia.org/w/api.php", {
        "action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": n}).json()
    return [{"title": h["title"], "url": "https://en.wikipedia.org/wiki/" + h["title"].replace(" ", "_"),
             "snippet": _html.unescape(re.sub(r"<[^>]+>", "", h.get("snippet", "")))}
            for h in data.get("query", {}).get("search", [])]


def search_papers(query, n=5):
    try:
        data = _http_get("https://api.openalex.org/works", {"search": query, "per-page": n}).json()
    except Exception as e:
        print(f"[search_papers] OpenAlex failed: {e!r}", flush=True)
        return {"error": f"Paper search failed: {e}"}
    out = []
    for w in data.get("results", []):
        abstract = ""
        inv = w.get("abstract_inverted_index") or {}
        if inv:
            pos = sorted((i, word) for word, idx in inv.items() for i in idx)
            abstract = " ".join(word for _, word in pos)[:700]
        src = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
        out.append({
            "title": w.get("display_name"), "year": w.get("publication_year"), "venue": src,
            "authors": [a["author"]["display_name"] for a in (w.get("authorships") or [])[:6] if a.get("author")],
            "cited_by": w.get("cited_by_count"), "doi": w.get("doi"), "abstract": abstract})
    return out or {"note": "No papers found"}


def google_search(query):
    """Ask a Gemini model to search Google and summarise what it finds, with sources."""
    r = client.with_options(timeout=60).chat.completions.create(
        model=WEB_SEARCH_MODEL,
        messages=[{"role": "user", "content":
                   f"Search the web and answer this for a student who is reading an academic paper:\n\n{query}\n\n"
                   "Give the key facts in 3 to 6 sentences. Then list the websites you used, as 'Site name: URL'. "
                   "If the search finds nothing reliable, say so."}],
        tools=[{"type": "function", "function": {"name": "google_search"}}])
    text = (r.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("empty answer")
    return {"source": "Google Search (via " + WEB_SEARCH_MODEL.split("/")[-1] + ")", "answer": text}


def web_search(query):
    errors = []
    if WEB_SEARCH_MODEL:
        try:
            return google_search(query)
        except Exception as e:
            print(f"[web_search] Google search via {WEB_SEARCH_MODEL} failed: {e!r}", flush=True)
            errors.append("google search failed")
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        results = DDGS().text(query, max_results=6)
        if results:
            return [{"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")} for r in results]
        errors.append("web search: no results")
    except Exception as e:
        print(f"[web_search] DuckDuckGo failed: {e!r}", flush=True)
        errors.append(f"web search failed ({type(e).__name__})")
    # Fall back to sources that are free and dependable
    fallback = {}
    try:
        fallback["wikipedia"] = wikipedia_search(query)
    except Exception as e:
        print(f"[web_search] Wikipedia failed: {e!r}", flush=True)
        errors.append(f"wikipedia failed ({type(e).__name__})")
    papers = search_papers(query, 3)
    if isinstance(papers, list):
        fallback["papers"] = papers
    if fallback:
        fallback["note"] = "General web search was unavailable, so these come from Wikipedia and the OpenAlex paper database."
        return fallback
    return {"error": "; ".join(errors) + ". Your internet connection may be down."}


def read_web_page(url):
    import html as _html
    try:
        t = _http_get(url).text
        t = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav)[^>]*>.*?</\1>", " ", t)
        t = re.sub(r"(?s)<[^>]+>", " ", t)
        t = re.sub(r"\s+", " ", _html.unescape(t)).strip()
        return {"url": url, "text": t[:7000]}
    except Exception as e:
        print(f"[read_web_page] {url}: {e!r}", flush=True)
        return {"error": f"Couldn't read that page: {e}"}


# ---------------------------------------------------------------- highlights and notes the AI can add
NOTE_TOOLS = [
    {"type": "function", "function": {
        "name": "highlight",
        "description": "Highlight words or sentences in the listener's copy of the document, when they ask you to. "
                       "quote must be copied exactly from the document: a few words, a sentence, or several sentences.",
        "parameters": {"type": "object", "properties": {
            "quote": {"type": "string", "description": "Exact words from the document"},
            "color": {"type": "string", "enum": ["purple", "green", "blue", "pink"]}}, "required": ["quote"]}}},
    {"type": "function", "function": {
        "name": "add_note",
        "description": "Write a note in the margin of the listener's copy, attached to a passage, when they ask you to note something down. "
                       "quote: exact words from the document the note belongs to (for 'this sentence', copy that whole sentence). "
                       "note: the note text, written the way they asked, in the language they used.",
        "parameters": {"type": "object", "properties": {
            "quote": {"type": "string", "description": "Exact words from the document"},
            "note": {"type": "string"},
            "color": {"type": "string", "enum": ["purple", "green", "blue", "pink"]}}, "required": ["quote", "note"]}}},
]
COLOR_IDS = {"purple": 1, "green": 2, "blue": 3, "pink": 4}


def locate(sents, quote, near):
    """Find exact words in the document. Returns (s1, o1, s2, o2) of the occurrence closest to `near`, or None."""
    q = re.sub(r"\s+", " ", quote).strip().strip("\"“”'‘’").strip().lower()
    if len(q) < 2:
        return None
    starts, parts, pos = [], [], 0
    for x in sents:
        starts.append(pos)
        parts.append(x["t"].lower())
        pos += len(x["t"]) + 1
    full = " ".join(parts)
    for cand in (q, q.rstrip(".!?,;:")):
        hits, k = [], full.find(cand)
        while k >= 0:
            hits.append(k)
            k = full.find(cand, k + 1)
        if hits:
            best = min(hits, key=lambda h: abs(bisect.bisect_right(starts, h) - 1 - near))
            end = best + len(cand)
            s1 = bisect.bisect_right(starts, best) - 1
            s2 = bisect.bisect_right(starts, end - 1) - 1
            return s1, best - starts[s1], s2, end - starts[s2]
    return None


def note_tool(name, args, sents, near):
    """Returns (result for the AI, action for the page or None)."""
    where = locate(sents, str(args.get("quote", "")), near)
    if not where:
        return {"ok": False, "error": "Couldn't find those exact words in the document. Copy the words exactly as written in the document and try again."}, None
    s1, o1, s2, o2 = where
    text = " ".join(sents[i]["t"][(o1 if i == s1 else 0):(o2 if i == s2 else None)] for i in range(s1, s2 + 1))
    action = {"s1": s1, "o1": o1, "s2": s2, "o2": o2, "text": text[:300],
              "c": COLOR_IDS.get(str(args.get("color", "")).lower(), 1),
              "note": str(args.get("note", "")).strip() if name == "add_note" else None}
    return {"ok": True, "done": "note added" if name == "add_note" else "highlighted", "page": sents[s1]["p"], "text": text[:120]}, action


def run_tool(name, args):
    q = str(args.get("query", ""))[:300]
    if name == "web_search":
        return web_search(q)
    if name == "search_papers":
        return search_papers(q)
    if name == "read_web_page":
        return read_web_page(str(args.get("url", "")))
    return {"error": "Unknown tool"}


class ChatReq(BaseModel):
    doc_id: str
    pos: int
    message: str
    history: list = []
    focus: str = ""  # exact words the listener selected or highlighted, if they asked about a specific passage


# What the gateway/model turned out not to accept, so we stop sending it
_unsupported = set()


def open_stream(msgs, want_tools, system_plain, tool_list=None):
    """Start a streamed reply, dropping optional extras the model doesn't accept. Returns (stream, tools_used)."""
    extras = {"cache": True, "usage": True, "limit": True, "tools": want_tools}
    while True:
        m = msgs
        if not extras["cache"] or "cache" in _unsupported:
            m = [{"role": "system", "content": system_plain}] + msgs[1:]
        kwargs = {"model": MODEL, "messages": m, "stream": True}
        if extras["usage"] and "usage" not in _unsupported:
            kwargs["stream_options"] = {"include_usage": True}
        if extras["limit"] and "limit" not in _unsupported:
            kwargs["max_tokens"] = 600
        if extras["tools"]:
            kwargs["tools"] = tool_list or WEB_TOOLS
        try:
            return client.chat.completions.create(**kwargs), extras["tools"]
        except Exception as e:
            msg = str(e).lower()
            for name, words in (("cache", ("cache_control", "cache")), ("usage", ("stream_options", "include_usage")),
                                ("limit", ("max_tokens", "max_completion_tokens")), ("tools", ("tool",))):
                if extras[name] and name not in _unsupported and any(w in msg for w in words):
                    print(f"[chat] model doesn't accept '{name}', continuing without it", flush=True)
                    _unsupported.add(name) if name != "tools" else None
                    extras[name] = False
                    break
            else:
                if not getattr(e, "status_code", None) or e.status_code >= 500 or not any(extras.values()):
                    raise
                # Unknown 4xx: drop all extras once and try a plain request
                print(f"[chat] request rejected ({str(e)[:120]}), retrying without extras", flush=True)
                extras = dict.fromkeys(extras, False)


def log_usage(u):
    cached = 0
    details = getattr(u, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", 0) or 0
    cached = cached or getattr(u, "cache_read_input_tokens", 0) or 0
    print(f"[usage] input {u.prompt_tokens:,} tokens (from cache: {cached:,}), answer {u.completion_tokens:,} tokens", flush=True)


@app.post("/api/chat")
def chat(req: ChatReq):
    doc = load_doc(req.doc_id)
    sents, title = doc["sents"], doc["title"]
    pos = max(0, min(req.pos, len(sents) - 1))
    line = lambda i: f"[#{i}, p.{sents[i]['p']}] {sents[i]['t']}"
    lo, hi = max(0, pos - 12), min(len(sents), pos + 3)
    passage = "\n".join((">> " if i == pos else "") + line(i) for i in range(lo, hi))
    total_chars = sum(len(x["t"]) + 1 for x in sents)

    # The prompt has two parts. Part 1 (instructions + document) is identical every time you ask
    # about the same document, so the AI provider can cache it and charge much less for it.
    # Part 2 (where reading stopped, what you selected) changes, so it comes last.
    instructions = """You are a study partner on a live voice call. The listener is having an academic text read aloud to them sentence by sentence. They paused the reading to talk with you. Everything you write is spoken aloud by text-to-speech.

How to talk:
- Sound like a person on the phone: warm, natural, concise. Usually 2 to 4 sentences. Go longer only if they ask.
- Plain spoken English. No markdown, no bullet points, no headings, no asterisks, no URLs. Spell out symbols when needed.
- If they speak Chinese or mix languages, you may answer in English but keep it simple, and explain tricky terms plainly.

Be strictly faithful to the document:
- When you say what the text says, base it on the document. Quote exactly when they ask you to repeat or quote something, and mention the page when it helps.
- Never invent what the document contains. If it isn't in the document, say so plainly, then clearly label anything else as general knowledge.
- "The last sentence" or "that" usually means the sentence where reading stopped, or the one just before it.
- You can look things up: web_search for general and specialist knowledge, search_papers for scholarly papers (authors, venues, citations, related work), and read_web_page to read a page. Use them when the listener asks for outside knowledge, or when you aren't sure of a fact the document doesn't cover. Before searching, say one short sentence such as "Let me look that up." Afterwards, make clear what comes from the paper and what comes from the web, and name the source briefly (for example "according to the APA website"). Don't read out URLs.
- You can mark up the listener's copy when they ask: highlight (words or sentences) and add_note (a note in the margin next to a passage). Copy the quote exactly from the document; for "this sentence" use the sentence where reading stopped. Write notes in the language they used. Only say it's done after the tool result says ok; if it failed, say so. Afterwards confirm in a few words, for example "Done, I've noted that next to the sentence."
- Your earlier replies in this conversation may end with a bracketed list, "[What you actually did in this reply: ...]". That list is an accurate record of the highlights, notes and searches you really made, so trust it and never apologise for something it shows you did.
- Don't continue reading the document yourself. When they say to move on, the app resumes reading automatically."""

    if total_chars <= FULL_DOC_MAX_CHARS:
        paras, cur, cur_g, cur_p = [], [], None, None
        for x in sents:
            if x["g"] != cur_g and cur:
                paras.append(" ".join(cur)); cur = []
            if x["p"] != cur_p:
                paras.append(f"--- page {x['p']} ---"); cur_p = x["p"]
            if x["g"] != cur_g and x.get("k"):
                cur.append({"caption": "[Caption]", "code": "[Code]", "table": "[Table]", "small": "[Small print]"}[x["k"]])
            cur_g = x["g"]
            cur.append(x["t"])
        if cur:
            paras.append(" ".join(cur))
        part1 = f"""{instructions}

The full document:
<document title="{title}">
{chr(10).join(paras)}
</document>"""
        part2 = f"""Reading stopped at page {sents[pos]['p']}, on this sentence:
"{sents[pos]['t']}"

The passage around it (>> marks that sentence):
{passage}"""
    else:
        lo2, hi2 = max(0, pos - 30), min(len(sents), pos + 4)
        window = set(range(lo2, hi2))
        opening = "\n".join(line(i) for i in range(0, min(10, len(sents))))
        wide = "\n".join((">> " if i == pos else "") + line(i) for i in range(lo2, hi2))
        found = retrieve(sents, req.message, window | set(range(0, 10)))
        elsewhere = "\n".join(line(i) for i in found)
        part1 = f"""{instructions}

Document: "{title}" ({len(sents)} sentences). It is too long to show in full, so you see excerpts only. Say so if the answer might be in a part you can't see.

Opening of the document:
{opening}"""
        part2 = f"""Passage around where reading stopped (>> marks the interrupted sentence):
{wide}

Other sentences in the document that match words in their question:
{elsewhere or "(none found)"}"""

    focus = req.focus.strip()[:3000]
    if focus:
        part2 += f"""

The listener selected this exact passage in the document and is asking about it:
\"\"\"{focus}\"\"\"
When they say "this", "that", "it" or "these words", they mean exactly this passage. Answer about these words, using the document around them for context."""

    history = [m for m in req.history if m.get("role") in ("user", "assistant") and m.get("content")][-8:]
    system_cached = [{"type": "text", "text": part1, "cache_control": {"type": "ephemeral"}},
                     {"type": "text", "text": part2}]
    system_plain = part1 + "\n\n" + part2
    messages = [{"role": "system", "content": system_cached}] + history + [{"role": "user", "content": req.message}]

    def gen():
        if not API_KEY:
            yield "data: " + json.dumps({"error": "No API key set. Add OPENAI_API_KEY to the .env file and restart."}) + "\n\n"
            return
        import time as _time
        t_start, t_first, searches = _time.time(), None, 0
        msgs = list(messages)
        tool_list = (WEB_TOOLS if WEB_SEARCH else []) + NOTE_TOOLS
        use_tools = True
        try:
            for rnd in range(5):
                stream, use_tools = open_stream(msgs, use_tools and rnd < 4, system_plain, tool_list)
                text, calls = "", {}
                for chunk in stream:
                    if getattr(chunk, "usage", None):
                        log_usage(chunk.usage)
                    if not chunk.choices:
                        continue
                    d = chunk.choices[0].delta
                    if d is None:
                        continue
                    if d.content:
                        if t_first is None:
                            t_first = _time.time()
                        text += d.content
                        yield "data: " + json.dumps({"t": d.content}) + "\n\n"
                    for tc in (d.tool_calls or []):
                        c = calls.setdefault(tc.index if tc.index is not None else len(calls), {"id": "", "name": "", "args": ""})
                        if tc.id:
                            c["id"] = tc.id
                        if tc.function and tc.function.name and not c["name"]:
                            c["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            c["args"] += tc.function.arguments
                if not calls:
                    break
                if text and not text.endswith((" ", "\n")):
                    yield "data: " + json.dumps({"t": " "}) + "\n\n"
                msgs.append({"role": "assistant", "content": text or None, "tool_calls": [
                    {"id": c["id"] or f"call_{i}", "type": "function", "function": {"name": c["name"], "arguments": c["args"] or "{}"}}
                    for i, c in calls.items()]})
                for i, c in calls.items():
                    try:
                        args = json.loads(c["args"] or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    label = args.get("query") or args.get("url") or ""
                    if c["name"] in ("highlight", "add_note"):
                        result, action = note_tool(c["name"], args, sents, pos)
                        if action:
                            yield "data: " + json.dumps({"action": action}) + "\n\n"
                            label = ("📝 Note added: " + action["note"]) if action["note"] else ("🖍 Highlighted: “" + action["text"][:80] + "”")
                        else:
                            label = "⚠️ Couldn't find those words to " + ("add the note" if c["name"] == "add_note" else "highlight")
                        yield "data: " + json.dumps({"status": label}) + "\n\n"
                        msgs.append({"role": "tool", "tool_call_id": c["id"] or f"call_{i}", "content": json.dumps(result, ensure_ascii=False)})
                        continue
                    yield "data: " + json.dumps({"status": {"web_search": "🔎 Searching the web: ", "search_papers": "🔎 Searching papers: "}.get(c["name"], "🔎 Reading: ") + label}) + "\n\n"
                    searches += 1
                    result = run_tool(c["name"], args)
                    msgs.append({"role": "tool", "tool_call_id": c["id"] or f"call_{i}", "content": json.dumps(result, ensure_ascii=False)[:9000]})
            yield "data: [DONE]\n\n"
            first = f"{t_first - t_start:.1f}s" if t_first else "-"
            print(f"[timing] AI started answering after {first}, finished after {_time.time() - t_start:.1f}s"
                  f"{f', with {searches} lookup(s)' if searches else ''}", flush=True)
        except Exception as e:
            yield "data: " + json.dumps({"error": f"The AI request failed: {e}"}) + "\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------------------------------------------------------------- config + page
@app.get("/api/config")
def config():
    try:
        voices = sorted(v for v in kokoro().get_voices() if v[:2] in ("af", "am", "bf", "bm"))
        tts_ok = True
    except HTTPException:
        voices, tts_ok = [], False
    return {"voices": voices, "voice": DEFAULT_VOICE, "model": MODEL, "tts_ok": tts_ok, "ai_ok": bool(API_KEY)}


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/m")
def mobile():
    return FileResponse(ROOT / "static" / "mobile.html")


if __name__ == "__main__":
    import uvicorn

    print(f"\n  PaperTalkthrough is running. Open http://localhost:{PORT} in Chrome or Edge.\n  Press Ctrl+C to stop.\n")
    threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")

# PaperTalkthrough 🎧📞

**Your papers, read aloud. And you can talk back.**

- 🎧 **Just listen.** Lean back and let it read the whole paper to you in a natural voice.
- 👀 **Or read along.** Each sentence lights up as it's read, on clean text or on the original PDF pages. Click any sentence to jump there.
- 📞 **Call anytime.** Hit **Call** mid-sentence and talk about anything: *"wait, what does that mean?"*, *"how is this different from the last paper?"*, *"look that up for me."* The AI has read the whole paper and answers out loud. Say *"move on"*, and reading picks up right where you left off.
- 🖍️ **Let the AI mark it up.** *"Highlight that in green."* *"Add a note next to this sentence: ask my advisor."* Or highlight and write notes yourself.
- 📄 **Export your PDF** with every highlight and note, ready to open in any PDF reader.

No more rereading the same paragraph five times.

[中文使用指南 (Chinese guide)](GUIDE_zh-CN.md)

It runs on your own computer. The reading voice is free and works offline; only your questions go to an AI service of your choice.

## What it can do

- **Reads PDFs aloud** in a natural voice ([Kokoro](https://github.com/thewh1teagle/kokoro-onnx)), highlighting each sentence as it goes. Click any sentence to jump there.
- **Live voice calls with an AI** about the paper. The AI sees the whole document and knows exactly where you stopped. Talk over it to interrupt, as on a phone call.
- **Voice commands during a call**: "move on", "repeat that", "go back".
- **Highlights and margin notes**: drag across text to highlight it and add a note. You can also ask the AI to do it ("highlight that in green", "note next to this sentence: compare with chapter 2").
- **Page view**: see the original PDF pages, with the current sentence and your highlights drawn on them.
- **Export** a copy of the PDF with all your highlights and notes.
- **Web and paper search**: the AI can look up background knowledge (free sources: DuckDuckGo, Wikipedia, and the OpenAlex research-paper database).
- **Skips clutter** when reading: figure captions, tables, code, small print, and optionally citations like "(Smith et al., 2019)".
- **Phone version** (optional): a simplified page you can use on your phone while your computer stays at home.

## What you need

- A **Windows or Mac** computer with about 1 GB of free disk space
- **Python 3.10, 3.11 or 3.12** (3.12 recommended)
- **Google Chrome** or **Microsoft Edge** (needed for talking to the AI by voice)
- An **API key** for an AI service that speaks the "OpenAI-compatible" format. Almost all do: OpenAI, Anthropic (Claude), Google Gemini, OpenRouter, DeepSeek, and many university or company AI gateways. Reading aloud works without a key; only the AI calls need one.

## Setup (about 15 minutes, one time only)

### 1. Download PaperTalkthrough

On this GitHub page, click the green **Code** button, then **Download ZIP**. Unzip it somewhere easy to find, for example your Documents folder.

> **Windows:** right-click the ZIP and choose **Extract All**. Unzipping sometimes creates a folder inside a folder; use the inner one, the one that directly contains `server.py`.

### 2. Install Python

Download **Python 3.12** from [python.org/downloads](https://www.python.org/downloads/).

- **Windows:** on the first screen of the installer, tick **"Add python.exe to PATH"** at the bottom, then click **Install Now**. If the newest 3.12 release only offers source files, pick the most recent 3.12 version that has a **Windows installer (64-bit)**.
- **Mac:** run the installer normally.

### 3. Open a terminal in the PaperTalkthrough folder

- **Windows:** open the PaperTalkthrough folder in File Explorer, click the address bar, type `cmd`, and press Enter. A black window opens, already in the right folder.
- **Mac:** open **Terminal**, type `cd ` (with a space after it), drag the PaperTalkthrough folder into the Terminal window, and press Enter.

Check you're in the right place: type `dir` (Windows) or `ls` (Mac) and press Enter. You should see `server.py` in the list.

> In the commands below, Windows uses `py`. On a Mac, use `python3` instead.

### 4. Install the required packages

```
py -m pip install -r requirements.txt
```

This takes a few minutes. A notice about a newer pip version is fine to ignore.

### 5. Download the voice model (about 350 MB)

```
py download_models.py
```

Wait until it says `Voice model ready.`

### 6. Add your API key

Make a copy of the file `.env.example` named `.env`:

- **Windows:** `copy .env.example .env` then `notepad .env`
- **Mac:** `cp .env.example .env` then `open -e .env`

In the file that opens, fill in three lines and save:

```
OPENAI_BASE_URL=   the address of your AI provider (examples are listed in the file)
OPENAI_API_KEY=    your key
MODEL=             the model to use
```

No spaces around `=` and no quotes. Save the file and close it.

> **Keep `.env` private.** It contains your key. Never share it or upload it anywhere.

### 7. Check that your key works

```
py check_gateway.py
```

It lists the models your key can use and asks the AI for a short test reply. If it says `All good`, you're set. If it doesn't, check the base URL, the key, and that `MODEL` exactly matches one of the listed names.

**Which model?** Pick a small, fast one, such as a "mini", "flash" or "haiku" model. Calls feel more natural when answers start quickly, and these models cost much less. Avoid large "reasoning" models: they pause for a long time before answering.

### 8. Start PaperTalkthrough

```
py server.py
```

Your browser opens **http://localhost:8000**. If it doesn't, open that address yourself in Chrome or Edge.

**Keep the terminal window open** while you use PaperTalkthrough; closing it stops the program.

**Starting it from now on:** double-click `start-windows.bat` (Windows) or `start-mac.command` (Mac). If your Mac refuses to open the file, use the terminal instead: `cd` into the folder and run `python3 server.py`.

## How to use it

1. Click **Open a PDF** and choose a paper. It must be a PDF with selectable text; a scanned image of pages won't work.
2. Press **▶** (or the **Space** bar) to start reading.
3. Press **Call** and just talk. The first time, allow the microphone. Pause for about two seconds when you're done; the AI answers out loud.
4. Say **"move on"** or press **Hang up & keep reading** to continue from the sentence where you stopped.

**During a call you can say:**

- "move on" / "continue": hang up and keep reading
- "repeat that": reread the sentence where you stopped
- "go back": go back one sentence
- "highlight 'design-based research' in blue"
- "add a note to this sentence: ask the professor about this"
- "look up what Cohen's kappa means"
- "is this paper part of a bigger project?"

**With the mouse:**

- **Click a sentence:** read from there, highlight it, or ask about it.
- **Drag across text:** highlight it, add a note, or ask about exactly those words.
- **Click a highlight:** change its color, edit its note, or delete it.
- **Page view** (top right): switch between the clean text and the original PDF pages.
- **Export PDF** (top right): download a copy of the PDF with your highlights and notes.
- **Skip** (bottom bar): choose what not to read aloud: Citations, Captions, Tables, Code, Small print.
- **Interrupt by talking** (next to Call): when on, you can talk over the AI to interrupt it. Use headphones; otherwise the AI may hear itself through your speakers.

Your reading position, highlights, notes and conversations are saved automatically, separately for each document.

## Use it on your phone (optional)

Your computer does all the work; the phone shows a simplified page (reading, calls, and picking up where you left off). This uses **Tailscale**, a free tool that privately connects your own devices. Only devices signed in to your Tailscale account can open the page.

1. Install **Tailscale** on your computer ([tailscale.com/download](https://tailscale.com/download)) and on your phone (App Store / Google Play). Sign in to **both with the same personal account**.
   > If you sign in with a school or work email, other people from your organization may end up on the same network. A personal account (Google, Apple, GitHub) is safer.
2. Start PaperTalkthrough on your computer as usual.
3. Open a **new** terminal window and run:
   ```
   tailscale serve --bg 8000
   ```
   - If it prints a link saying Serve isn't enabled, open the link and enable **HTTPS certificates**. Leave **Tailscale Funnel unticked**: Funnel would open your computer to the whole internet. Then run the command again.
   - If the command isn't found on Windows, use `"C:\Program Files\Tailscale\tailscale.exe" serve --bg 8000`
4. It prints an address like `https://your-computer.your-tailnet.ts.net/`. Open it in your phone's browser (with Tailscale connected), and allow the microphone when asked. On iPhone, use Safari's **Share → Add to Home Screen** for an app-like icon.

You only need to do this once. After that:

- Your computer must be **on and not asleep**. Set sleep to "Never" while plugged in; the screen can still turn off.
- PaperTalkthrough must be **running** on the computer.
- Keep the phone screen on while listening. On the phone, tap the status line ("Speaking — tap here to interrupt") to interrupt the AI.

**Optional: start PaperTalkthrough automatically on Windows.** Press Win + R, type `shell:startup`, and press Enter. Then put a shortcut to `start-windows.bat` in the folder that opens.

## Costs and privacy

- **Reading aloud** happens entirely on your computer and is free.
- **AI calls** cost money through your provider. Each question sends the document text and the recent conversation. With a small model, a question about a typical paper usually costs a few cents or less. Many providers cache the document between questions, which makes follow-up questions cheaper. The terminal window shows how many tokens each answer used.
- **What leaves your computer:** the document text and your questions go to the AI provider you chose. Your spoken words are turned into text by your browser's speech recognition; in Chrome this uses Google's servers. Web searches go to the search services listed above.
- **What stays on your computer:** the PDFs, your notes, highlights and conversations, in the `library` folder.

## Troubleshooting

| Problem | What to do |
|---|---|
| `'pip' is not recognized` or `'python' is not recognized` (Windows) | Use `py -m pip ...` and `py ...`. If `py` isn't found either, reinstall Python with **"Add python.exe to PATH"** ticked, then open a new terminal window. |
| `Python was not found; run without arguments to install from the Microsoft Store` | Same as above: use `py` instead of `python`. |
| `Could not open requirements file` | The terminal isn't in the PaperTalkthrough folder. See step 3. |
| `Fill in OPENAI_BASE_URL and OPENAI_API_KEY` | The `.env` file is missing or wasn't saved. On Windows, check it isn't named `.env.txt` (run `dir /a`; if needed, `ren .env.txt .env`). |
| The voice says the model files are missing | Run `py download_models.py` again. |
| The AI never answers or shows an error | Run `py check_gateway.py` and fix whatever it reports. |
| The microphone doesn't hear you | Use Chrome or Edge, allow the microphone (icon in the address bar), and keep the PaperTalkthrough tab in front: browsers pause speech recognition in background tabs. |
| "Failed to fetch" when opening a PDF | The program stopped. Look at the terminal window for an error message. |
| No text appears for a PDF | It's probably a scanned PDF (pictures of pages). It needs OCR (text recognition) first. |
| Two-column papers read in the wrong order | Some PDFs store their text in an unusual order. Please open an issue with the paper. |
| Changes don't show up after an update | Restart the program, then press Ctrl+F5 (Cmd+Shift+R on Mac) in the browser. |

## Files

| File | What it is |
|---|---|
| `server.py` | The program: reads PDFs, makes the voice, talks to the AI |
| `static/index.html` | The computer page |
| `static/mobile.html` | The phone page |
| `.env.example` | Settings template; copy it to `.env` |
| `check_gateway.py` | Checks your API key and lists models |
| `download_models.py` | Downloads the voice model |
| `start-windows.bat`, `start-mac.command` | Double-click to start |

Your `.env`, the `library` folder (your documents and notes) and the `models` folder are never uploaded: they're listed in `.gitignore`.

## Built with

[Kokoro](https://github.com/thewh1teagle/kokoro-onnx) (voice), [PyMuPDF](https://pymupdf.readthedocs.io/) (PDF reading), [pysbd](https://github.com/nipunsadvilkar/pySBD) (sentence splitting), [FastAPI](https://fastapi.tiangolo.com/), and the [OpenAlex](https://openalex.org/) paper database.

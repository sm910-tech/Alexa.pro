# Alexa Pro — Personal AI Assistant

A dark, premium voice assistant with a browser-based frontend and a Python FastAPI backend.  
Talk to it, type to it, or tap the quick-action cards — it answers with voice.

---

## What it does

| Capability | How it works |
|---|---|
| **Voice input** | Web Speech API (Chrome / Edge) |
| **Voice output** | SpeechSynthesis API (all browsers) |
| **Current time & date** | `tools/clock.py` — no API needed |
| **Weather** | Open-Meteo (free, no API key) + IP geolocation |
| **Reminders** | Stored in `backend/reminders.json` |
| **Timers** | Countdown in the browser, fires TTS alarm |
| **Calculator** | AST-based safe evaluator — no `eval()` |
| **Open conversation** | Anthropic API (`claude-opus-4-5`) |
| **Smart home** | UI demo — add real integrations in `tools/` |

---

## Folder structure

```
alexa-pro/
├── frontend/
│   ├── index.html      ← UI structure
│   ├── styles.css      ← Dark premium design
│   ├── app.js          ← Navigation, API calls, UI rendering
│   ├── voice.js        ← Speech recognition + TTS
│   └── orb.js          ← Animated canvas orb
├── backend/
│   ├── main.py         ← FastAPI server
│   ├── assistant.py    ← AI logic + tool routing
│   ├── schemas.py      ← Pydantic request / response models
│   ├── requirements.txt
│   └── tools/
│       ├── clock.py       ← Time and date
│       ├── reminders.py   ← CRUD reminder store
│       ├── weather.py     ← Open-Meteo weather
│       └── calculator.py  ← Safe AST evaluator
├── tests/
│   ├── test_api.py     ← FastAPI endpoint tests
│   └── test_tools.py   ← Unit tests for each tool
├── .env.example
├── .gitignore
├── LICENSE
└── README.md
```

---

## Installation

### 1 — Clone / copy the project

```bash
# If you have it as a zip, unzip and enter the folder
cd alexa-pro
```

### 2 — Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy the environment file and add your API key:

```bash
cd ..
cp .env.example .env
# Open .env and set ANTHROPIC_API_KEY=sk-ant-...
```

Start the server:

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 3 — Frontend

No build step required. Open `frontend/index.html` directly in **Chrome** or **Edge**  
(required for Web Speech API voice recognition).

```bash
# macOS
open frontend/index.html

# Linux
xdg-open frontend/index.html

# Or drag index.html into your browser
```

> **Note:** If you open the file from disk (`file://`), the browser may block  
> microphone access. For the full experience, serve it locally:
>
> ```bash
> cd frontend
> python -m http.server 3000
> # Then open http://localhost:3000
> ```

---

## Using the assistant

### Voice
Click the **microphone button** or the animated orb. Speak your request.  
The orb changes colour and shape to show what the assistant is doing:

| Orb state | Meaning |
|---|---|
| Slow blue pulse | Idle — waiting |
| Fast bright cyan | Listening |
| Purple shimmer | Thinking |
| Flowing blue | Speaking |

### Keyboard
Click the **keyboard button** to type. Press Enter or click the send arrow.

### Quick actions
The dashboard has six quick-action buttons for common requests.

---

## Example commands

```
What time is it?
What's today's date?
What's the weather like?
Remind me to call the dentist
Set a 10-minute timer for pasta
What's 18% of 340?
What is quantum entanglement?
Tell me a fun fact about the moon
```

---

## Running tests

```bash
cd alexa-pro
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

---

## Architecture

```
Browser  →  app.js POST /chat  →  FastAPI (main.py)
                                      │
                                  assistant.py
                                  ┌───┴───────────────────┐
                                  │  Keyword intent match  │
                                  │  (fast, no API call)   │
                                  └───────────┬────────────┘
                                       ↓ no match
                                  Anthropic claude-opus-4-5
                                       ↓
                              { reply, tool_results }
                                       ↓
                              app.js renders + speaks
```

Tools are executed on the **backend**, not by the AI model. The model answers  
open-ended questions; the backend decides whether to call a tool first based  
on keyword intent patterns in `assistant.py`.

---

## Adding new tools

1. Create `backend/tools/my_tool.py` with a function that returns a string or dict.
2. Add an intent pattern in `assistant.py`'s `_INTENT_PATTERNS`.
3. Add a handler in `Assistant.respond()` that calls your tool and returns a reply.
4. Add a test in `tests/test_tools.py`.

---

## API reference

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/health` | — | `{"status":"ok"}` |
| `POST` | `/chat` | `{message, history?}` | `{reply, tool_results?}` |
| `GET` | `/weather` | — | weather dict |
| `GET` | `/reminders` | — | reminder list |
| `POST` | `/reminders` | `{text, due_at?}` | reminder |
| `PUT` | `/reminders/{id}` | `{done?, text?}` | reminder |
| `DELETE` | `/reminders/{id}` | — | 204 |

Interactive docs (when backend is running): http://localhost:8000/docs

---

## Customisation

- **Voice:** Change rate and pitch in Settings.
- **Name:** Enter your name in Settings for personalised greetings.
- **AI model:** Change `model=` in `assistant.py` to any Anthropic model.
- **Weather city:** Set `WEATHER_LAT`, `WEATHER_LON`, `WEATHER_CITY` in `.env`.
- **Smart home:** Replace the UI toggles in `dashboard` with real API calls to  
  your home automation platform (Home Assistant, SmartThings, etc.).

# S.P.I.K.E — System for Personalized Intelligence, Knowledge & Execution

An **open-source, agentic terminal AI** — your Python-powered assistant that runs
in the terminal, calls tools autonomously, remembers everything between chats,
and acts on your behalf.

Built with **zero third-party dependencies** — only the Python standard library.
Free to use, free to modify, free to build on.

---

## Quick Start

### 1. Get the code

```bash
git clone https://github.com/FaqihAbdulMaalik/spike.git
cd spike
```

> Don't have Git? Download the ZIP from
> https://github.com/FaqihAbdulMaalik/spike → Code → Download ZIP

### 2. Requirements

**Python 3.10+** is the only requirement. No `pip install` needed — the entire
project uses only the Python standard library.

Check your Python version:

```bash
python --version   # must be 3.10 or higher
```

### 3. Get a free API key (online mode)

1. Go to https://opencode.ai and sign in
2. Copy your Zen API key
3. Create a file called `.env` in the project folder:

```bash
echo 'OPENCODE_API_KEY="zen-...."' > .env
```

Replace `zen-....` with your actual key.

### 4. Run Veronica

```bash
python -m terminal_chatbot                    # online with web + tools
python -m terminal_chatbot --local            # offline mode (no key needed)
python -m terminal_chatbot --list             # list providers & models
```

---

## Features

- **25+ tools** — web search, file read/write/list, run & review Python code,
  GitHub API, email sending, file upload, HTTP requests, weather, URL fetching,
  currency & unit conversion, news headlines, and more
- **Conversation memory** — remembers your name, preferences, watchlists, and
  GitHub identity between sessions (JSON-based, stored locally)
- **Agentic** — the model autonomously decides which tools to call, capped at
  4 tool rounds
- **Online by default** via `opencode` (free Zen models: `hy3-free`,
  `deepseek-v4-flash-free`, …)
- **Web search** (DuckDuckGo → Bing → Google fallback, no API key)
- **Streaming output** — responses appear token-by-token in real time
- **Privacy** — conversations stay in memory only, never written to disk,
  no telemetry
- **OpenAI-compatible API server** — `server.py` exposes a REST API
- **Sensitive tool verification** — destructive operations prompt `(y/N)`
  before executing
- **Claude-Code-style terminal UI** — colored status bar, tool indicators,
  markdown rendering
- **Offline mode** — built-in rule-based replies with `--local`

---

## Tools

| Category | Tools |
|----------|-------|
| **Memory** | `remember`, `recall`, `forget`, `list_memories`, `clear_memory` |
| **Files** | `read_file`, `write_file`, `list_dir` |
| **Code** | `run_code`, `review_code` |
| **Web** | `web_search`, `fetch_page`, `read_url`, `get_news` |
| **Conversion** | `convert` (currency + units) |
| **Weather** | `get_weather` |
| **Time** | `get_current_time`, `calculate` |
| **GitHub** | `github_get_repo`, `github_list_issues`, `github_create_issue`, `github_search_code` |
| **Network** | `http_request`, `upload_file` |
| **Email** | `send_email` |

---

## Commands

```
  !help               show help
  !list               list providers and models
  !provider <id>      switch provider (local/opencode)
  !model <name>       set model
  !web <query>        search the web directly
  !clear              clear conversation memory
  !quit               exit
```

---

## Send Email via Gmail (send_email tool)

To let Veronica send emails on your behalf, you need a **Gmail App Password**:

1. Enable **2-Factor Authentication** on your Google account:
   https://myaccount.google.com/security

2. Generate an **App Password**:
   https://myaccount.google.com/apppasswords
   - Select "Mail" as the app and your device
   - Copy the **16-character password** (looks like `abcd efgh ijkl mnop`)

3. Add these lines to your `.env` file:

```bash
SMTP_SERVER="smtp.gmail.com"
SMTP_PORT="587"
SMTP_USER="your.email@gmail.com"
SMTP_PASS="your 16 char app password"
EMAIL_FROM="your.email@gmail.com"
```

4. Restart Veronica. Now when you ask her to send an email, she'll use these
   credentials. They stay in your `.env` (gitignored) — nobody else sees them.

> For other email providers, change `SMTP_SERVER` and `SMTP_PORT` accordingly.

---

## API Server

```bash
python server.py
```

Exposes an OpenAI-compatible API at `POST /v1/chat/completions`.
Useful for building a web UI or integrating with other apps.

---

## Project structure

```
terminal-chatbot/
├── run.py                          # entry point
├── server.py                       # REST API server
├── terminal_chatbot/
│   ├── __init__.py
│   ├── __main__.py                 # python -m terminal_chatbot
│   ├── agent.py                    # agentic loop (tool calling)
│   ├── bot.py                      # chatbot logic, commands
│   ├── cli.py                      # terminal UI, arg parser
│   ├── config.py                   # provider configuration
│   ├── memory.py                   # persistent JSON memory
│   ├── tools.py                    # all 25+ tools
│   ├── ui.py                       # terminal styling
│   └── providers/
│       ├── base.py                 # base provider class
│       ├── http.py                 # HTTP provider (OpenCode Zen)
│       └── local.py                # offline rule-based provider
```

---

## Contributing

**This is an open-source project** and everyone is welcome to contribute!

### How to contribute

1. **Fork** the repo: https://github.com/FaqihAbdulMaalik/spike
   → click "Fork" (top right)
2. **Clone your fork**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/spike.git
   ```
3. **Create a branch**:
   ```bash
   git checkout -b your-feature-name
   ```
4. **Make your changes** and commit:
   ```bash
   git add .
   git commit -m "Add your feature"
   ```
5. **Push to your fork**:
   ```bash
   git push origin your-feature-name
   ```
6. **Open a Pull Request** on GitHub:
   - Go to https://github.com/FaqihAbdulMaalik/spike
   - Click "Pull Requests" → "New Pull Request"
   - Select your fork and branch
   - Describe your changes and submit

All PRs are reviewed and welcome!

### What you can build

- **Python learners** — study the code, add new tools, improve existing ones.
  The entire project uses only the standard library — great for learning how
  things work under the hood.
- **ML practitioners** — plug in your own models via the provider system,
  experiment with agentic loops, or build custom toolchains.
- **Web developers** — build a web interface for Veronica (the API server
  already speaks OpenAI-compatible format).
- **Anyone** — fork it, feature it, ship it. Build a desktop app, a website,
  a Slack bot, whatever you want.

Ideas to get started:
- [ ] Web-based UI (React/Vue/Svelte frontend for the API server)
- [ ] Desktop app (Tkinter, Electron, or native)
- [ ] More providers (OpenAI, Anthropic, local LLMs via Ollama)
- [ ] SQLite-backed memory instead of JSON
- [ ] Plugin system for community-contributed tools
- [ ] Voice input/output

---

## License

MIT — do whatever you want.

## Author

Built by **faqihabdulmaalik** — data analyst & vibecoder.

**S.P.I.K.E = System for Personalized Intelligence, Knowledge & Execution** ⚡

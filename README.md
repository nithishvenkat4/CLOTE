# CLOTE — Self-Hosted File Management System

> Own your files. Run your cloud. No subscriptions, no third parties.

CLOTE is a privacy-first, self-hosted file management platform built with FastAPI and SQLite. Upload, organize, share, and interact with your files using a built-in local AI — all running on your own machine.

---

## Features

- 📁 File & Folder Management — upload, download, organize, rename, delete
- 🗂️ Projects — group files into workspaces
- 🔗 File Sharing — generate share links for files
- 🗑️ Trash & Restore — soft-delete with recovery
- 📦 Bulk Operations — select and act on multiple files at once
- 📜 Audit Logs — track every action (who, what, when)
- 🤖 AI Assistant — chat with your files using a local LLM via Ollama
- 🔐 JWT Authentication — secure login with encrypted passwords
- 🗃️ File Versioning — keeps previous versions of updated files
- 🌐 Remote Access — works over Tailscale VPN without exposing to internet

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.13 |
| Framework | FastAPI |
| Server | Uvicorn |
| Database | SQLite |
| Auth | JWT + bcrypt |
| AI | Ollama (local LLM) |
| Frontend | Single HTML file |
| Deployment | Docker / systemd |

---

## Quick Start (Docker — Recommended)

**Requirements:** [Docker Desktop](https://www.docker.com/products/docker-desktop/)

```bash
# 1. Clone the repo
git clone -b dev https://github.com/nithishvenkat4/CLOTE.git
cd CLOTE

# 2. Create your config
cp .env.example .env
# Open .env and set your SECRET_KEY

# 3. Run
docker compose up -d
```

Open `http://localhost:8000` in your browser.

**Stop:**
```bash
docker compose down
```

---

## Manual Setup (Without Docker)

**Requirements:** Python 3.13+

```bash
git clone -b dev https://github.com/nithishvenkat4/CLOTE.git
cd CLOTE/server

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

pip install -r requirements.txt

cp ../.env.example ../.env   # fill in SECRET_KEY

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | JWT signing secret (required) | — |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Session duration | `60` |
| `ALLOWED_ORIGINS` | CORS origins | `*` |
| `SMTP_USER` | Email for notifications | optional |
| `SMTP_PASS` | Email app password | optional |
| `OLLAMA_HOST` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | LLM model to use | `llama3.2` |

---

## AI Features (Optional)

CLOTE can connect to a local [Ollama](https://ollama.com) instance for AI-powered file interactions.

```bash
# Install Ollama, then pull a model
ollama pull llama3.2
```

Set `OLLAMA_HOST` and `OLLAMA_MODEL` in your `.env`. If Ollama is not running, all other features work normally.

---

## Project Structure

```
CLOTE/
├── client/
│   └── CLOTE.html          # Frontend UI
├── server/
│   ├── main.py             # App entry point
│   ├── auth.py             # Authentication logic
│   ├── config.py           # Environment config
│   ├── database.py         # SQLite setup
│   ├── requirements.txt    # Python dependencies
│   ├── routes/
│   │   ├── auth_routes.py
│   │   ├── file_routes.py
│   │   ├── folder_routes.py
│   │   ├── project_routes.py
│   │   ├── share_routes.py
│   │   ├── trash_routes.py
│   │   ├── bulk_routes.py
│   │   ├── audit_routes.py
│   │   └── ai_routes.py
│   └── storage/
│       ├── files/          # Uploaded files
│       └── versions/       # File version history
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── install.sh              # Linux one-command installer
```

---

## Linux Server Install (One Command)

```bash
sudo bash install.sh
```

Installs CLOTE as a systemd service that starts automatically on boot.

---

## API Docs

When running, visit `http://localhost:8000/docs` for the full interactive API documentation (Swagger UI).

---

## License

MIT — free to use, modify, and self-host.

---

## Author

Built by [Nithish V](https://github.com/nithishvenkat4)

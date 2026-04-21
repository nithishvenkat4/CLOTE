# CLOTE — Self-Hosted-CLOUD with File Management and Version Control System

![Python](https://img.shields.io/badge/Python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

**CLOTE is a self-hosted file management platform that provides secure, multi-user file storage with versioning, access control, and optional AI-powered interaction — all running on your own infrastructure.**

It is designed as a privacy-first alternative to cloud storage systems, giving users full control over their data without relying on third-party services.

---

## Features

* File and folder management — upload, download, organize, rename, delete
* Project-based organization for grouping files
* File sharing via generated links
* Trash and restore functionality (soft delete)
* Bulk operations for efficient file handling
* Audit logs for tracking system activity
* File versioning with rollback support
* Multi-user support on a single server
* Role-based access control for projects and resources
* Secure authentication using JWT and encrypted passwords
* Optional AI assistant via local LLM (Ollama integration)
* Remote access support via private VPN (Tailscale)

---

## Why CLOTE?

* Fully self-hosted — no vendor lock-in
* Privacy-first design — data remains under your control
* Lightweight and easy to deploy
* Designed for both individual and team use
* Extensible architecture for future enhancements

---

## Quick Start (Docker)

**Requirements:** Docker

```bash
git clone -b dev https://github.com/nithishvenkat4/CLOTE.git
cd CLOTE
cp .env.example .env
# configure SECRET_KEY

docker compose up -d
```

Open: http://localhost:8000

Stop the service:

```bash
docker compose down
```

> Note: Docker runs the backend service. The frontend must be opened separately (see below).

---

## Manual Setup

**Requirements:** Python 3.13+

```bash
git clone -b dev https://github.com/nithishvenkat4/CLOTE.git
cd CLOTE/server

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

pip install -r requirements.txt

cp ../.env.example ../.env
# configure SECRET_KEY

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Frontend (Client UI)

The frontend is a static interface located at:

```
client/CLOTE.html
```

### Running the application

1. Start the backend server
2. Open the frontend file in your browser

```bash
start client/CLOTE.html        # Windows
# or
open client/CLOTE.html         # macOS
# or
xdg-open client/CLOTE.html     # Linux
```

### Development option

Run a simple static server:

```bash
cd client
python -m http.server 3000
```

Then open:

http://localhost:3000

The frontend communicates with the backend via the configured API URL (default: `http://localhost:8000`).

---

## Remote Access (Tailscale VPN)

CLOTE can be accessed securely from remote devices using a private VPN such as Tailscale.

### Setup

1. Install Tailscale on server and client devices
2. Start the CLOTE backend server
3. Obtain the Tailscale IP (e.g., `100.x.x.x`)
4. Update the API base URL in `client/CLOTE.html`:

```javascript
const BASE_URL = "http://100.x.x.x:8000";
```

5. Access the frontend from any connected device

### Benefits

* No port forwarding required
* Secure private network access
* Remote usage without exposing the server publicly

---

## Multi-User and Access Control

CLOTE supports multiple users connected to a single server instance.

### Role-Based Access Control

* Users can be assigned roles
* Access to projects and files can be restricted
* Enables controlled collaboration and security

### Multi-User Architecture

* Single deployment serving multiple users
* Isolated sessions per user
* Suitable for both personal and team environments

---

## File Versioning

CLOTE maintains a version history for files.

* Previous versions are stored automatically on updates
* Stored in:

```
server/storage/versions/
```

* Users can restore earlier versions when needed

---

## Environment Variables

| Variable                    | Description               |
| --------------------------- | ------------------------- |
| SECRET_KEY                  | JWT signing secret        |
| ACCESS_TOKEN_EXPIRE_MINUTES | Session duration          |
| ALLOWED_ORIGINS             | CORS configuration        |
| SMTP_USER                   | Email (optional)          |
| SMTP_PASS                   | Email password (optional) |
| OLLAMA_HOST                 | Local AI server           |
| OLLAMA_MODEL                | Model name                |

---

## AI Integration (Optional)

CLOTE can integrate with a local Ollama instance for AI-powered file interaction.

```bash
ollama pull llama3.2
```

Configure the environment variables accordingly. The system functions normally without AI enabled.

---

## Project Structure

```
CLOTE/
├── client/
│   └── CLOTE.html
├── server/
│   ├── routes/
│   ├── storage/
│   └── core modules
├── Dockerfile
├── docker-compose.yml
└── install.sh
```

---

## Linux Installation

```bash
sudo bash install.sh
```

Installs CLOTE as a system service.

---

## API Documentation

Available at:

http://localhost:8000/docs

---

## Future Improvements

* Advanced search and indexing
* Mobile-friendly interface
* External storage integrations
* Enhanced role management

---

## Contributing

Contributions are welcome. Please open an issue or submit a pull request.

---

## License

MIT License

---

## Author

Nithish V
https://github.com/nithishvenkat4

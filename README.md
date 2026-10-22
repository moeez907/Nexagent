# NexAgent — Autonomous AI Web Agent Platform

[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React_18-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![Playwright](https://img.shields.io/badge/Automation-Playwright-2EAD33?logo=playwright&logoColor=white)](https://playwright.dev/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL_16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

**NexAgent** is an advanced, website-agnostic autonomous web agent platform. Unlike rigid scraping scripts or linear workflow tools (such as Zapier or n8n), NexAgent deploys **Vision-Language Models (VLMs)** combined with **Playwright browser automation** to browse the live web, understand complex interfaces, reason dynamically through multi-step journeys, and execute tasks exactly like a human operator.

---

## 📌 Table of Contents
1. [What is NexAgent? (Project Overview)](#-what-is-nexagent-project-overview)
2. [Where to Add Your API Key (API Key Guide)](#-where-to-add-your-api-key)
3. [How to Run (Step-by-Step)](#-how-to-run-step-by-step)
   - [Method 1: Docker (Recommended — 1 Command)](#method-1-docker-one-click-run---recommended)
   - [Method 2: Manual Local Development (Without Docker)](#method-2-manual-local-development-without-docker)
4. [Platform Architecture](#-platform-architecture)
5. [Key Capabilities & Features](#-key-capabilities--features)
6. [Accessing Application Endpoints](#-accessing-application-endpoints)
7. [Useful Docker Management Commands](#-useful-docker-management-commands)
8. [Troubleshooting & FAQs](#-troubleshooting--faqs)

---

## 🧠 What is NexAgent? (Project Overview)

NexAgent is built to solve tasks across any website without hardcoded selectors or pre-built integrations.

### Core Capabilities:
- **Autonomous Multi-Step Navigation:** Decomposes complex user goals (e.g., *"Search for top 5 mechanical keyboards on Amazon, extract names, prices, and reviews into a table"*, or *"Navigate to the portal, search for records, and export findings"*).
- **Intelligent Form Filling & Data Entry:** Automatically identifies and populates form fields, text areas, dropdowns, radio buttons, checkboxes, and file uploaders across dynamic web pages (e.g., Google Forms, contact sheets, registration portals, and multi-stage applications) with human-like typing and validation.
- **Human-in-the-Loop & CAPTCHA Resolution:** When encountering bot barriers (such as Google reCAPTCHA, Cloudflare Turnstile, hCaptcha, puzzle sliders, or 2FA OTP codes), the agent intelligently pauses execution, alerts the user with an intervention banner, and enables live interactive canvas control so the human can solve the CAPTCHA. Once completed, the agent automatically detects success and resumes its mission seamlessly.
- **Vision & DOM Intelligence:** Captures high-resolution page viewports and pairs them with extracted DOM accessibility trees, allowing Vision LLMs (Nebius / Nemotron VL) to pinpoint interactive elements with surgical precision.
- **Live Interactive Viewport (WebSocket Streaming):** Watch the agent navigate in real time with ultra-low latency JPEG streaming over WebSockets.
- **Enterprise Persistent Storage:** Full user authentication, password hashing, active session management, task histories, screenshots, and structured JSON results stored in PostgreSQL.

---

## 🔑 Where to Add Your API Key

NexAgent uses the **Nebius AI Token Factory** Vision model (`nvidia/Nemotron-3.5-Super-VL`) for web perception and reasoning.

### 📍 File Location:
You add your API key in the **root `.env` file** of this project:
### Note 
That When you clone the repo then file will be .env.example then remame the file .env and then add the api key
```
Nexagent/
├── .env           <--- PUT YOUR KEY HERE
├── .env.example
├── docker-compose.yml
...
```

### ⚙️ Step-by-Step API Key Setup:

1. In the root directory of the project, check if `.env` exists. If not, copy `.env.example`:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` in any text editor.
3. Locate line 14:
   ```env
   # LLM Configuration (Nebius Token Factory)
   LLM_PROVIDER=nebius
   NEBIUS_API_KEY=your_actual_nebius_api_key_here
   NEBIUS_BASE_URL=https://api.tokenfactory.us-north1.nebius.com/v1/
   NEBIUS_MODEL=nvidia/Nemotron-3.5-Super-VL
   ```
4. Paste your actual key after `NEBIUS_API_KEY=`. Example:
   ```env
   NEBIUS_API_KEY=v1.CmQKHHN0YXRpY2tle...
   ```
5. Save the file.

> **Note:** If you are running the backend locally without Docker, you can also place the same `.env` file inside the `backend/` folder (`backend/.env`).

---

## 🚀 How to Run (Step-by-Step)

---

### Method 1: Docker (One-Click Run — Recommended)

With Docker, you do **not** need to install or configure Python, Node.js, PostgreSQL, Redis, or Playwright Chromium binaries on your system. **Docker spins up everything together in isolated containers.**

> **Only 1 Action Required:** Add your `NEBIUS_API_KEY` in `.env` and run `docker compose up`!

#### Step 1: Ensure Docker Desktop is Running
Make sure [Docker Desktop](https://www.docker.com/products/docker-desktop/) is running on your machine.

#### Step 2: Open Terminal in Project Directory
```bash
cd "Nexagent"
```

#### Step 3: Put Your API Key in `.env`
Open `.env` and paste your `NEBIUS_API_KEY`:
```env
NEBIUS_API_KEY=your_actual_nebius_api_key_here
```
*(PostgreSQL, Redis, database name, and passwords are all pre-configured with zero manual configuration needed)*

#### Step 4: Run the Single Docker Command
```bash
docker compose up
```
*(Or `docker compose up --build` on initial build, or `docker compose up -d` to run in background)*

#### What Starts Automatically in Docker:
1. **PostgreSQL 16 Container:** Starts automatically, creates the `web_agent` database, and sets up healthchecks.
2. **Redis 7 Container:** Starts automatically for live task state, caching, and WebSocket pub/sub.
3. **FastAPI Backend Container:** Starts automatically, connects to PostgreSQL, creates all tables (`users`, `tasks`, `conversations`, etc.) automatically, and loads Playwright Chromium.
4. **React Frontend + Nginx Container:** Builds the UI and serves it with WebSocket and API reverse proxy.

#### Step 5: Open the Application
Open your browser and navigate to:
👉 **[http://localhost:5173](http://localhost:5173)** or **[http://localhost](http://localhost)**

---

### Method 2: Manual Local Development (Without Docker)

If you prefer to run services natively on your local machine:

#### Prerequisites:
- Python 3.10 or 3.11
- Node.js (v18+) & npm
- PostgreSQL running locally on port `5432` with a database named `web_agent`
- Optional: Redis running locally on port `6379` (an automatic in-memory fallback will be used if Redis is not present)

#### Step 1: Backend Setup
1. Open a terminal in the `backend` folder:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   # Windows:
   python -m venv ..\venv
   ..\venv\Scripts\activate

   # Linux / macOS:
   python3 -m venv ../venv
   source ../venv/bin/activate
   ```
3. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Install Playwright browser binaries:
   ```bash
   playwright install chromium
   ```
5. Configure `backend/.env` with your database URL and `NEBIUS_API_KEY`:
   ```env
   POSTGRES_URL=postgresql+asyncpg://postgres:your_password@localhost:5432/web_agent
   NEBIUS_API_KEY=your_key_here
   ```
6. Start the backend server:
   ```bash
   python main.py
   ```
   *(Backend will be live at `http://127.0.0.1:8000`)*

#### Step 2: Frontend Setup
1. Open a new terminal window in the `frontend` folder:
   ```bash
   cd frontend
   ```
2. Install frontend packages:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
4. Open the displayed URL (typically **[http://localhost:5173](http://localhost:5173)**).

---

## 🏗️ Platform Architecture

```
                    ┌────────────────────────────────────────────────────────┐
                    │                      User Browser                      │
                    │               (http://localhost:5173)                  │
                    └───────────────┬────────────────────────┬───────────────┘
                                    │ HTTP Requests          │ WebSockets (/ws)
                                    ▼                        ▼
                    ┌────────────────────────────────────────────────────────┐
                    │               Nginx Reverse Proxy (Frontend)           │
                    └───────────────────────────┬────────────────────────────┘
                                                │
                                                ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                 FastAPI Backend (:8000)                                 │
│                                                                                         │
│  ┌───────────────────────┐   ┌───────────────────────────┐   ┌───────────────────────┐  │
│  │   Auth & Task Routes  │   │   Task & State Manager    │   │  Live WS Broadcaster  │  │
│  └───────────┬───────────┘   └─────────────┬─────────────┘   └───────────┬───────────┘  │
│              │                             │                             │              │
│              ▼                             ▼                             ▼              │
│  ┌───────────────────────┐   ┌───────────────────────────┐   ┌───────────────────────┐  │
│  │     SQLAlchemy        │   │    Playwright Chromium    │   │   Nebius Vision LLM   │  │
│  │     Async Engine      │   │     (Headless Engine)     │   │      (Nemotron VL)    │  │
│  └───────────┬───────────┘   └───────────────────────────┘   └───────────────────────┘  │
└──────────────┼─────────────────────────────┼────────────────────────────────────────────┘
               ▼                             ▼
┌──────────────────────────────┐ ┌──────────────────────────────┐
│        PostgreSQL 16         │ │           Redis 7            │
│   (Users, Tasks, History)    │ │   (Ephemeral State & Cache)  │
└──────────────────────────────┘ └──────────────────────────────┘
```

---

## 🌟 Key Capabilities & Features

| Feature | Description |
|---------|-------------|
| **Automated Form Filling** | Dissects dynamic forms (e.g. Google Forms, lead sheets, portal signups) and populates text, options, and uploads automatically. |
| **Human-in-the-Loop CAPTCHA Solver** | Auto-detects bot checks (reCAPTCHA, Cloudflare Turnstile, hCaptcha, 2FA), triggers interactive takeover, and resumes autonomy. |
| **Zero-Configuration DB** | Tables (`users`, `tasks`, `task_events`, etc.) are auto-created on initial boot. |
| **Interactive Canvas** | Click, double-click, scroll, and type directly into the live agent browser viewport. |
| **Live Step Visualizer** | Step-by-step breakdown showing the agent's thought process, planned action, target element, and execution status. |
| **Clean Result Extraction** | Returns structured findings, data summaries, and execution reports upon mission completion. |
| **Secure Authentication** | User registration and login with salt-hashed passwords and cookie-based session verification. |
| **Workspace Persistence** | Active missions and chat history are saved so page refreshes never lose progress. |

---

## 🌐 Accessing Application Endpoints

Once running, access the following URLs:

- **Web Application:** [http://localhost:5173](http://localhost:5173) or [http://localhost](http://localhost)
- **Interactive API Documentation (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Health Endpoint:** [http://localhost:8000/health](http://localhost:8000/health)
- **PostgreSQL Database:** `localhost:5432` (Default User: `postgres`, Password: `postgres`, DB: `web_agent`)

---

## 🛠️ Useful Docker Management Commands

| Task | Command |
|------|---------|
| Start all containers in background | `docker compose up -d` |
| View live logs across all containers | `docker compose logs -f` |
| View backend logs only | `docker compose logs -f backend` |
| View database logs only | `docker compose logs -f postgres` |
| Stop all containers | `docker compose down` |
| Stop and completely reset database volumes | `docker compose down -v` |
| Rebuild all containers from scratch | `docker compose up --build --force-recreate` |

---

## ❓ Troubleshooting & FAQs

### 1. `Docker: port is already allocated (5432 or 8000)`
- **Reason:** You may have a local PostgreSQL server or Python process already running on your machine.
- **Fix:** Stop your local PostgreSQL service (or change `POSTGRES_PORT=5433` in `.env`) before starting Docker.

### 2. `Authentication error: NEBIUS_API_KEY is missing or invalid`
- **Reason:** The agent needs the Nebius key to perceive and navigate web pages.
- **Fix:** Make sure you added your key into the root `.env` file under `NEBIUS_API_KEY=...` and restarted the backend (`docker compose restart backend`).

### 3. How to verify that database tables were created?
- On container boot, the backend runs `init_db()` automatically. You can check the backend logs:
  ```bash
  docker compose logs backend
  ```
  You will see: `Connected to PostgreSQL database successfully.`

---

## 📜 License & Credits

Built as part of the **NexAgent** Autonomous Web Automation platform. Powered by Nebius AI, Playwright, FastAPI, and React.

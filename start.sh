#!/usr/bin/env bash
# ============================================================================
# NexAgent - Autonomous Web Agent 1-Click Startup for macOS & Linux
# ============================================================================

set -e

echo "============================================================================"
echo "                     NEXAGENT - AUTONOMOUS WEB AGENT"
echo "============================================================================"
echo ""

# 1. Check Docker status
if ! docker info >/dev/null 2>&1; then
    echo "[ERROR] Docker is not running or not installed!"
    echo "Please ensure Docker / Docker Desktop is running, then run this script again."
    exit 1
fi

# 2. Check and initialize .env file
if [ ! -f ".env" ]; then
    echo "[*] No .env file found. Creating from .env.example..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "[OK] .env file created!"
    else
        echo "NEBIUS_API_KEY=" > .env
        echo "LLM_PROVIDER=nebius" >> .env
    fi
fi

# 3. Check if NEBIUS_API_KEY is configured
CURRENT_KEY=$(grep -E "^NEBIUS_API_KEY=" .env | cut -d '=' -f2- | tr -d ' "\r\n')
if [ -z "$CURRENT_KEY" ] || [ "$CURRENT_KEY" = "your_actual_nebius_api_key_here" ]; then
    echo ""
    echo "----------------------------------------------------------------------------"
    echo " [ACTION REQUIRED] Nebius API Key is not configured yet!"
    echo "----------------------------------------------------------------------------"
    read -p " Paste your Nebius API Key here (or press Enter to set in .env): " USER_KEY
    if [ -n "$USER_KEY" ]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s/^NEBIUS_API_KEY=.*/NEBIUS_API_KEY=$USER_KEY/" .env
        else
            sed -i "s/^NEBIUS_API_KEY=.*/NEBIUS_API_KEY=$USER_KEY/" .env
        fi
        echo "[OK] API Key saved to .env!"
    else
        echo "[!] You can edit the .env file anytime to set your NEBIUS_API_KEY."
    fi
    echo ""
fi

# 4. Start Docker Compose Stack
echo "============================================================================"
echo " Starting NexAgent Stack (PostgreSQL, Redis, Backend, Frontend)..."
echo "============================================================================"
echo ""
echo "Application will be available at: http://localhost:5173"
echo ""

docker compose up --build "$@"

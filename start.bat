@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM NexAgent - Autonomous Web Agent 1-Click Startup for Windows
REM ============================================================================

echo ============================================================================
echo                      NEXAGENT - AUTONOMOUS WEB AGENT
echo ============================================================================
echo.

REM 1. Check if Docker is installed and running
docker info >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Docker is not running or not installed!
    echo Please make sure Docker Desktop is installed and running, then try again.
    echo.
    pause
    exit /b 1
)

REM 2. Check and initialize .env file
if not exist ".env" (
    echo [*] No .env file found. Creating from .env.example...
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [OK] .env file created!
    ) else (
        echo [WARNING] .env.example not found. Creating blank .env...
        echo NEBIUS_API_KEY=> .env
        echo LLM_PROVIDER=nebius>> .env
    )
)

REM 3. Check if NEBIUS_API_KEY is configured
set "HAS_KEY=0"
for /f "tokens=1,* delims==" %%A in (.env) do (
    if "%%A"=="NEBIUS_API_KEY" (
        set "KEY_VAL=%%B"
        if defined KEY_VAL (
            if not "!KEY_VAL!"=="" (
                if not "!KEY_VAL!"=="your_actual_nebius_api_key_here" (
                    set "HAS_KEY=1"
                )
            )
        )
    )
)

if "!HAS_KEY!"=="0" (
    echo.
    echo ----------------------------------------------------------------------------
    echo  [ACTION REQUIRED] Nebius API Key is not configured yet!
    echo ----------------------------------------------------------------------------
    set /p USER_KEY=" Paste your Nebius API Key here (or press Enter to configure in .env): "
    if defined USER_KEY (
        if not "!USER_KEY!"=="" (
            powershell -Command "(Get-Content .env) -replace '^NEBIUS_API_KEY=.*', ('NEBIUS_API_KEY=' + $env:USER_KEY) | Set-Content .env"
            echo [OK] API Key saved to .env!
        )
    ) else (
        echo [!] You can also edit the .env file anytime to set your NEBIUS_API_KEY.
    )
    echo.
)

REM 4. Start Docker Compose Stack
echo ============================================================================
echo  Starting NexAgent Stack (PostgreSQL, Redis, Backend, Frontend)...
echo ============================================================================
echo.
echo Application will be available at: http://localhost:5173
echo.

docker compose up --build %*

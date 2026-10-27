"""
FastAPI Main Application Entry Point.
Nexagent Backend.
"""
import sys
import asyncio
import socket
import logging
import argparse
import os
import json

from contextlib import asynccontextmanager


def _select_provider_from_cli() -> None:
    """Apply direct-start provider selection before settings and managers load."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--provider", default="nebius")
    args, _ = parser.parse_known_args()
    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
    elif not os.environ.get("LLM_PROVIDER"):
        os.environ["LLM_PROVIDER"] = "nebius"


_select_provider_from_cli()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db, async_session_factory, TaskModel
from app.auth.service import SESSION_COOKIE, get_user_from_token
from sqlalchemy import select
from app.core.redis import redis_client
from app.browser.session_manager import session_manager
from app.task_manager.manager import task_manager
from app.api.routes import router as api_router
from app.api.websocket import ws_manager

# Configure Logging
logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("web_agent.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and Shutdown Lifespan Hooks.
    """
    logger.info("Initializing Nexagent Backend...")
    # Initialize DB tables
    try:
        await asyncio.wait_for(init_db(), timeout=45)
    except asyncio.TimeoutError as exc:
        logger.error("PostgreSQL initialization timed out after 45 seconds.")
        raise RuntimeError("PostgreSQL initialization timed out. Start PostgreSQL before the backend.") from exc
    # Initialize Redis client
    try:
        await asyncio.wait_for(redis_client.initialize(), timeout=15)
    except asyncio.TimeoutError as exc:
        logger.error("Redis initialization timed out after 15 seconds.")
        raise RuntimeError("Redis initialization timed out. Start Memurai before the backend.") from exc

    # Bind WebSocket broadcast callback to TaskManager
    task_manager.set_ws_broadcast_callback(ws_manager.broadcast_to_task)

    logger.info("Backend initialization complete.")
    yield
    logger.info("Shutting down backend services...")
    await session_manager.shutdown()
    await redis_client.close()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="Nexagent API",
    description="Nexagent: website-agnostic autonomous browser automation platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register REST Router
app.include_router(api_router)


@app.get("/")
async def root_health_check():
    provider = settings.LLM_PROVIDER.strip().lower()
    return {
        "status": "healthy",
        "service": "Nexagent",
        "llm_provider": provider,
        "llm_model": settings.NEBIUS_MODEL,
        "environment": settings.APP_ENV
    }


@app.websocket("/ws/tasks/{task_id}")
async def task_websocket_endpoint(websocket: WebSocket, task_id: str):
    async with async_session_factory() as db:
        task_result = await db.execute(select(TaskModel).where(TaskModel.id == task_id))
        task = task_result.scalar_one_or_none()
        user = await get_user_from_token(db, websocket.cookies.get(SESSION_COOKIE))
        guest_id = websocket.cookies.get("awa_guest")
        if not task or (user and task.user_id != user.id) or (not user and task.guest_id != guest_id):
            await websocket.close(code=1008, reason="Task is not available for this session.")
            return
    await ws_manager.connect(websocket, task_id)
    try:
        try:
            replay = await redis_client.get_json(f"task:{task_id}:events")
            if isinstance(replay, list) and replay:
                await websocket.send_json({
                    "task_id": task_id,
                    "event_type": "EVENT_REPLAY",
                    "timestamp": asyncio.get_event_loop().time(),
                    "data": {"events": replay}
                })
        except Exception as error:
            logger.warning("Could not replay task events for %s: %s", task_id, error)
        while True:
            # Keep socket alive and process incoming client messages if any
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if isinstance(msg, dict) and msg.get("type") == "INTERACTION" and "payload" in msg:
                    payload = msg["payload"]
                    action = payload.get("action")
                    session = session_manager.get_session(task_id)
                    if not session:
                        session = await session_manager.get_or_create_interactive_session(task_id)
                    if session:
                        if action == "mousedown":
                            await session.mouse_down(payload.get("x_ratio", 0.5), payload.get("y_ratio", 0.5))
                        elif action == "mousemove":
                            await session.mouse_move(payload.get("x_ratio", 0.5), payload.get("y_ratio", 0.5))
                        elif action == "mouseup":
                            await session.mouse_up(payload.get("x_ratio"), payload.get("y_ratio"))
                        elif action == "click":
                            await session.click_at_ratio(payload.get("x_ratio", 0.5), payload.get("y_ratio", 0.5))
                        elif action == "double_click":
                            await session.double_click_at_ratio(payload.get("x_ratio", 0.5), payload.get("y_ratio", 0.5))
                        elif action == "scroll":
                            await session.scroll_by(payload.get("delta_y", 300), payload.get("x_ratio"), payload.get("y_ratio"))
                        elif action == "type":
                            if payload.get("text"):
                                await session.type_text(payload["text"])
                        elif action == "press":
                            await session.press_key(payload.get("key", "Enter"))
                        elif action == "back":
                            await session.go_back()
                        elif action == "forward":
                            await session.go_forward()
                        elif action == "reload":
                            await session.reload()
                        elif action == "navigate":
                            if payload.get("url"):
                                await session.navigate_to(payload["url"])

                        # Broadcast updated live frame to frontend immediately after click/key/navigation/scroll
                        if action in ("click", "mouseup", "double_click", "press", "type", "reload", "navigate", "scroll"):
                            await asyncio.sleep(0.04)
                            frame_data = await session.capture_base64_frame()
                            curr_url = session.current_url
                            if frame_data:
                                await ws_manager.broadcast_to_task(task_id, {
                                    "task_id": task_id,
                                    "event_type": "BROWSER_FRAME",
                                    "data": {"frame_data": frame_data, "url": curr_url}
                                })
            except Exception as e:
                logger.debug(f"WS interaction dispatch error: {e}")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, task_id)
    except Exception as e:
        logger.error(f"WebSocket connection error for task {task_id}: {e}")
        ws_manager.disconnect(websocket, task_id)


if __name__ == "__main__":
    import uvicorn
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as port_check:
        port_check.settimeout(0.5)
        if port_check.connect_ex(("127.0.0.1", settings.PORT)) == 0:
            logger.info("Backend is already running at http://127.0.0.1:%s", settings.PORT)
            sys.exit(0)
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG and sys.platform != "win32",
        reload_excludes=["tests/*", "*.pyc", "__pycache__/*", "data/*", "sessions/*"],
        loop="asyncio"
    )

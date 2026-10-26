"""
Playwright Browser Session Manager.
Manages Chromium lifecycle, context isolation, tracing, and session directory artifacts.
"""
import os
import uuid
import asyncio
import hashlib
import json
import logging
from typing import Awaitable, Callable, Dict, Optional
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory, BrowserSessionModel

logger = logging.getLogger("web_agent.browser.session_manager")


class BrowserSession:
    def __init__(self, session_id: str, session_dir: str, context: BrowserContext, page: Page, owns_context: bool = True, seed_path: Optional[str] = None, has_proxy: bool = False):
        self.session_id = session_id
        self.session_dir = session_dir
        self.context = context
        self.page = page
        self.owns_context = owns_context
        self.created_at = os.path.getctime(session_dir) if os.path.exists(session_dir) else 0.0
        self._cdp_session = None
        self._stream_callback: Optional[Callable[[str], Awaitable[None]]] = None
        self._frame_busy = False
        self._last_frame_time = 0.0
        self.seed_path = seed_path
        self.has_proxy = has_proxy

    @property
    def current_url(self) -> str:
        try:
            return self.page.url if (self.page and not self.page.is_closed()) else ""
        except Exception:
            return ""

    async def persist_storage_state(self, path: Optional[str] = None):
        target_path = path or self.seed_path
        if not target_path:
            return
        try:
            state = await self.context.storage_state()
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as state_file:
                json.dump(state, state_file)
            logger.info("Browser storage state persisted to: %s", target_path)
        except Exception as err:
            logger.warning("Could not persist browser storage state to %s: %s", target_path, err)

    async def start_live_stream(self, callback: Callable[[str], Awaitable[None]]):
        """Stream the actual browser page through CDP with backpressure and adaptive frame rate."""
        self._stream_callback = callback
        if self._cdp_session:
            return
        try:
            self._cdp_session = await self.context.new_cdp_session(self.page)
        except Exception as err:
            logger.warning("Could not establish CDP session for live stream: %s", err)
            return

        import time

        async def handle_frame(event):
            try:
                session_id = event.get("sessionId")
                if self._cdp_session and session_id is not None:
                    try:
                        await self._cdp_session.send("Page.screencastFrameAck", {"sessionId": session_id})
                    except Exception:
                        pass

                now = time.time()
                # Rate-limit to max ~15 fps (min 65ms between frames) and drop if previous frame is still broadcasting
                if self._frame_busy or (now - self._last_frame_time < 0.065):
                    return

                if self._stream_callback:
                    self._frame_busy = True
                    self._last_frame_time = now
                    try:
                        frame_uri = f"data:image/jpeg;base64,{event['data']}"
                        res = self._stream_callback(frame_uri)
                        if asyncio.iscoroutine(res):
                            await res
                    finally:
                        self._frame_busy = False
            except Exception as error:
                self._frame_busy = False
                logger.debug("Live browser frame error: %s", error)

        self._cdp_session.on("Page.screencastFrame", lambda event: asyncio.create_task(handle_frame(event)))
        try:
            await self._cdp_session.send("Page.startScreencast", {
                "format": "jpeg",
                "quality": 50,
                "maxWidth": 1024,
                "maxHeight": 640,
                "everyNthFrame": 2,
            })
            logger.info("CDP Screencast started successfully for session %s.", self.session_id)
        except Exception as err:
            logger.warning("Failed to start CDP screencast: %s", err)

    async def stop_live_stream(self):
        if not self._cdp_session:
            return
        try:
            await self._cdp_session.send("Page.stopScreencast")
            await self._cdp_session.detach()
        except Exception:
            pass
        self._cdp_session = None
        self._stream_callback = None
        self._frame_busy = False

    def set_stream_callback(self, callback: Callable[[str], Awaitable[None]]):
        self._stream_callback = callback

    async def capture_screenshot(self, name: str = "state.jpg") -> str:
        filepath = os.path.join(self.session_dir, "screenshots", name)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        # Fast JPEG encoding (quality 65) for ultra-fast live preview streaming
        try:
            await self.page.screenshot(
                path=filepath,
                full_page=False,
                type="jpeg",
                quality=65,
                timeout=10000,
            )
            return filepath
        except Exception as error:
            logger.warning("Screenshot capture skipped for session %s: %s", self.session_id, error)
            return ""

    async def capture_base64_frame(self) -> str:
        """Captures in-memory JPEG screenshot and returns base64 data URI for zero-file-latency live streaming."""
        import base64
        try:
            buffer = await self.page.screenshot(type="jpeg", quality=65, full_page=False, timeout=5000)
            return f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"
        except Exception as error:
            logger.debug("Live frame capture skipped for session %s: %s", self.session_id, error)
            return ""

    async def click_at_ratio(self, x_ratio: float, y_ratio: float):
        """
        Translates canvas ratio coordinates (0.0 - 1.0) into viewport pixel coordinates (1280x800)
        and performs a natural human click (move + down + delay + up).
        """
        viewport = self.page.viewport_size or {"width": 1280, "height": 800}
        pixel_x = int(x_ratio * viewport["width"])
        pixel_y = int(y_ratio * viewport["height"])
        try:
            await self.page.mouse.move(pixel_x, pixel_y)
            await self.page.mouse.click(pixel_x, pixel_y, delay=80)
        except Exception as err:
            logger.warning("click_at_ratio failed at (%s, %s): %s", pixel_x, pixel_y, err)

    async def double_click_at_ratio(self, x_ratio: float, y_ratio: float):
        viewport = self.page.viewport_size or {"width": 1280, "height": 800}
        pixel_x = int(x_ratio * viewport["width"])
        pixel_y = int(y_ratio * viewport["height"])
        await self.page.mouse.dblclick(pixel_x, pixel_y)

    async def mouse_down(self, x_ratio: float, y_ratio: float):
        viewport = self.page.viewport_size or {"width": 1280, "height": 800}
        pixel_x = int(x_ratio * viewport["width"])
        pixel_y = int(y_ratio * viewport["height"])
        await self.page.mouse.move(pixel_x, pixel_y)
        await self.page.mouse.down()

    async def mouse_move(self, x_ratio: float, y_ratio: float):
        viewport = self.page.viewport_size or {"width": 1280, "height": 800}
        pixel_x = int(x_ratio * viewport["width"])
        pixel_y = int(y_ratio * viewport["height"])
        await self.page.mouse.move(pixel_x, pixel_y)

    async def mouse_up(self, x_ratio: Optional[float] = None, y_ratio: Optional[float] = None):
        if x_ratio is not None and y_ratio is not None:
            viewport = self.page.viewport_size or {"width": 1280, "height": 800}
            pixel_x = int(x_ratio * viewport["width"])
            pixel_y = int(y_ratio * viewport["height"])
            await self.page.mouse.move(pixel_x, pixel_y)
        await self.page.mouse.up()

    async def type_text(self, text: str):
        """
        Types string text into the currently focused element on the live page.
        """
        logger.info(f"User typed text into live canvas: '{text}'")
        await self.page.keyboard.type(text, delay=50)

    async def press_key(self, key: str):
        """
        Presses a keyboard key (e.g. 'Enter', 'Backspace', 'Tab') on the live page.
        """
        logger.info(f"User pressed key on live canvas: '{key}'")
        await self.page.keyboard.press(key)

    async def scroll_by(self, delta_y: int, x_ratio: Optional[float] = None, y_ratio: Optional[float] = None):
        """
        Scrolls the page or element using real Playwright mouse wheel event at cursor coordinates.
        """
        viewport = self.page.viewport_size or {"width": 1280, "height": 800}
        if x_ratio is not None and y_ratio is not None:
            pixel_x = int(x_ratio * viewport["width"])
            pixel_y = int(y_ratio * viewport["height"])
            try:
                await self.page.mouse.move(pixel_x, pixel_y)
            except Exception:
                pass
        try:
            # Real hardware mouse wheel
            await self.page.mouse.wheel(0, delta_y)
        except Exception:
            await self.page.evaluate(f"window.scrollBy(0, {delta_y})")

    async def bring_to_front(self):
        """Brings the live browser window to the front of desktop screen."""
        try:
            await self.page.bring_to_front()
        except Exception as e:
            logger.debug("bring_to_front warning: %s", e)

    async def go_back(self):
        """Navigates back to previous page in browser history."""
        try:
            await self.page.go_back(wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            logger.warning(f"Browser go_back warning: {e}")

    async def go_forward(self):
        """Navigates forward in browser history."""
        try:
            await self.page.go_forward(wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            logger.warning(f"Browser go_forward warning: {e}")

    async def reload(self):
        """Reloads current active page."""
        try:
            await self.page.reload(wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            logger.warning(f"Browser reload warning: {e}")

    async def navigate_to(self, url: str):
        """Navigates directly to target URL."""
        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)

    async def close(self):
        try:
            await self.stop_live_stream()
            if self.owns_context:
                await self.context.close()
        except Exception as e:
            logger.error(f"Error closing browser context for session {self.session_id}: {e}")


class BrowserSessionManager:
    """
    Manages Playwright browser instance and session lifecycles.
    """

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._persistent_context: Optional[BrowserContext] = None
        self._active_sessions: Dict[str, BrowserSession] = {}
        self._context_lock = asyncio.Lock()

    async def initialize(self):
        if not self._playwright:
            import sys, asyncio
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            self._playwright = await async_playwright().start()

        if self._browser and self._browser.is_connected():
            return

        if settings.BROWSER_ELECTRON_CDP:
            self._browser = await self._playwright.chromium.connect_over_cdp(settings.BROWSER_CDP_URL)
            logger.info("Connected Playwright to the visible Electron browser over CDP.")
        else:
            launch_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--no-first-run",
                "--no-service-autorun",
                "--lang=en-US,en",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            ]
            proxy_config = None
            if settings.BROWSER_PROXY_SERVER:
                proxy_config = {"server": settings.BROWSER_PROXY_SERVER}
                if settings.BROWSER_PROXY_USERNAME:
                    proxy_config["username"] = settings.BROWSER_PROXY_USERNAME
                if settings.BROWSER_PROXY_PASSWORD:
                    proxy_config["password"] = settings.BROWSER_PROXY_PASSWORD

            self._browser = None
            # 1. Attempt to launch local Chrome channel (Windows / desktop)
            try:
                self._browser = await self._playwright.chromium.launch(
                    channel="chrome",
                    headless=settings.BROWSER_HEADLESS,
                    slow_mo=settings.BROWSER_SLOW_MO_MS,
                    args=launch_args,
                    ignore_default_args=["--enable-automation"],
                )
                logger.info("Launched local Chrome channel.")
            except Exception as launch_err:
                logger.info("Chrome channel not available (%s); launching bundled Chromium.", launch_err)

            # 2. Fallback to standard Chromium (AWS, Docker, Linux, headless servers)
            if self._browser is None:
                self._browser = await self._playwright.chromium.launch(
                    headless=settings.BROWSER_HEADLESS,
                    slow_mo=settings.BROWSER_SLOW_MO_MS,
                    args=launch_args,
                    ignore_default_args=["--enable-automation"],
                )
                logger.info("Launched bundled Chromium host.")
        logger.info("Playwright Chromium browser initialized.")

    @classmethod
    def get_default_seed_path(cls) -> str:
        return os.path.abspath(os.path.join(settings.BROWSER_PROFILE_DIR, "task_seeds", "default.json"))

    @classmethod
    def _seed_path(cls, owner_key: Optional[str]) -> str:
        if not owner_key:
            return cls.get_default_seed_path()
        safe_key = hashlib.sha256(owner_key.encode("utf-8")).hexdigest()
        return os.path.abspath(os.path.join(settings.BROWSER_PROFILE_DIR, "task_seeds", f"{safe_key}.json"))

    async def create_session(
        self,
        task_id: str,
        owner_key: Optional[str] = None,
        frame_callback: Optional[Callable[[str], Awaitable[None]]] = None,
        use_proxy: bool = True,
    ) -> BrowserSession:
        await self.initialize()

        session_id = str(uuid.uuid4())
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "sessions", session_id))
        os.makedirs(os.path.join(base_dir, "screenshots"), exist_ok=True)
        os.makedirs(os.path.join(base_dir, "logs"), exist_ok=True)
        os.makedirs(os.path.join(base_dir, "downloads"), exist_ok=True)

        async with self._context_lock:
            storage_state = None
            seed_path = self._seed_path(owner_key)
            target_load_path = None
            if seed_path and os.path.isfile(seed_path):
                target_load_path = seed_path
            elif os.path.isfile(self.get_default_seed_path()):
                target_load_path = self.get_default_seed_path()

            if target_load_path:
                try:
                    with open(target_load_path, "r", encoding="utf-8") as state_file:
                        storage_state = json.load(state_file)
                    logger.info("Loaded browser storage state seed from: %s", target_load_path)
                except (OSError, json.JSONDecodeError) as error:
                    logger.warning("Could not load task seed state from %s: %s", target_load_path, error)

            source_browser = self._browser
            if source_browser is None:
                raise RuntimeError("A browser instance is not available for an isolated task context.")

            proxy_config = None
            if use_proxy and settings.BROWSER_PROXY_SERVER:
                proxy_config = {"server": settings.BROWSER_PROXY_SERVER}
                if settings.BROWSER_PROXY_USERNAME:
                    proxy_config["username"] = settings.BROWSER_PROXY_USERNAME
                if settings.BROWSER_PROXY_PASSWORD:
                    proxy_config["password"] = settings.BROWSER_PROXY_PASSWORD

            context = await source_browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="en-US",
                timezone_id="America/New_York",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                accept_downloads=True,
                storage_state=storage_state,
                proxy=proxy_config,
            )
            # Comprehensive stealth evasions to prevent Google / Cloudflare bot rejection
            await context.add_init_script("""
                try {
                    delete Object.getPrototypeOf(navigator).webdriver;
                } catch(e) {}
                try {
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                } catch(e) {}

                if (!window.chrome) {
                    window.chrome = {};
                }
                window.chrome.runtime = { connect: function() {}, sendMessage: function() {} };
                window.chrome.app = { isInstalled: false };

                try {
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                } catch(e) {}

                try {
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                } catch(e) {}

                try {
                    Object.defineProperty(window, 'outerWidth', { get: () => window.innerWidth });
                    Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight + 85 });
                } catch (e) {}

                try {
                    for (const prop of Object.getOwnPropertyNames(window)) {
                        if (prop.startsWith('cdc_') || prop.startsWith('__playwright')) {
                            delete window[prop];
                        }
                    }
                } catch (e) {}
            """)
            page = await context.new_page()
        owns_context = True
        page.set_default_timeout(settings.ACTION_TIMEOUT_MS)
        page.set_default_navigation_timeout(settings.PAGE_LOAD_TIMEOUT_MS)

        session = BrowserSession(
            session_id, base_dir, context, page, owns_context=owns_context, seed_path=seed_path, has_proxy=bool(proxy_config)
        )
        if frame_callback:
            await session.start_live_stream(frame_callback)
        self._active_sessions[task_id] = session
        try:
            async with async_session_factory() as db:
                result = await db.execute(select(BrowserSessionModel).where(BrowserSessionModel.task_id == task_id))
                db_session = result.scalar_one_or_none()
                if db_session:
                    db_session.session_dir = base_dir
                    db_session.is_active = True
                else:
                    db.add(BrowserSessionModel(task_id=task_id, session_dir=base_dir, is_active=True))
                await db.commit()
        except Exception as db_err:
            logger.warning("Could not persist browser session %s to database: %s", session_id, db_err)
        logger.info(f"Created browser session {session_id} for task {task_id} (proxy={bool(proxy_config)}).")
        return session

    async def fallback_session_to_direct(
        self,
        task_id: str,
        owner_key: Optional[str] = None,
        frame_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> BrowserSession:
        """Disables proxy for this session and reopens a clean direct context."""
        old_session = self._active_sessions.pop(task_id, None)
        if old_session:
            try:
                await old_session.close()
            except Exception as e:
                logger.debug("Error closing old session during direct fallback: %s", e)
        logger.info("Falling back to direct connection for task %s...", task_id)
        return await self.create_session(
            task_id=task_id,
            owner_key=owner_key,
            frame_callback=frame_callback,
            use_proxy=False,
        )

    def get_session(self, task_id: str) -> Optional[BrowserSession]:
        session = self._active_sessions.get(task_id)
        if session and not session.page.is_closed():
            return session
        # Check any active open session in memory
        for tid, s in self._active_sessions.items():
            if s and not s.page.is_closed():
                return s
        return None

    async def get_or_create_interactive_session(self, task_id: str, default_url: Optional[str] = None) -> Optional[BrowserSession]:
        session = self.get_session(task_id)
        if session:
            return session

        from app.core.database import TaskModel
        target_url = default_url or "https://www.google.com"
        try:
            async with async_session_factory() as db:
                result = await db.execute(select(TaskModel).where(TaskModel.id == task_id))
                task = result.scalar_one_or_none()
                if task and task.current_url and task.current_url not in ("about:blank", ""):
                    target_url = task.current_url
        except Exception as e:
            logger.debug("Could not lookup task URL: %s", e)

        from app.task_manager.manager import task_manager
        frame_cb = lambda frame: task_manager._broadcast(
            task_id,
            "BROWSER_FRAME",
            {"frame_data": frame},
            persist=False,
        )

        try:
            session = await self.create_session(task_id, frame_callback=frame_cb)
            if target_url:
                try:
                    await session.page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
                except Exception as e:
                    logger.debug(f"Navigation error in restored session: {e}")
            return session
        except Exception as e:
            logger.error(f"Error creating interactive session for task {task_id}: {e}")
            return None

    async def adopt_session(
        self,
        old_task_id: str,
        new_task_id: str,
        frame_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> Optional[BrowserSession]:
        session = self._active_sessions.pop(old_task_id, None)
        if not session:
            return None

        # Verify page is still open and healthy
        try:
            if session.page.is_closed():
                await session.close()
                return None
        except Exception:
            return None

        if frame_callback:
            session.set_stream_callback(frame_callback)

        self._active_sessions[new_task_id] = session

        async with async_session_factory() as db:
            result = await db.execute(select(BrowserSessionModel).where(BrowserSessionModel.task_id == new_task_id))
            db_session = result.scalar_one_or_none()
            if db_session:
                db_session.session_dir = session.session_dir
                db_session.is_active = True
            else:
                db.add(BrowserSessionModel(task_id=new_task_id, session_dir=session.session_dir, is_active=True))

            old_res = await db.execute(select(BrowserSessionModel).where(BrowserSessionModel.task_id == old_task_id))
            old_db_session = old_res.scalar_one_or_none()
            if old_db_session:
                old_db_session.is_active = False

            await db.commit()

        logger.info(
            f"Transferred active browser session {session.session_id} from task {old_task_id} to continuation task {new_task_id} (active url: {session.page.url})."
        )
        return session

    async def close_session(self, task_id: str):
        session = self._active_sessions.pop(task_id, None)
        if session:
            await session.close()
            logger.info(f"Closed session for task {task_id}.")
        async with async_session_factory() as db:
            result = await db.execute(select(BrowserSessionModel).where(BrowserSessionModel.task_id == task_id))
            db_session = result.scalar_one_or_none()
            if db_session:
                db_session.is_active = False
                await db.commit()

    async def shutdown(self):
        for task_id in list(self._active_sessions.keys()):
            await self.close_session(task_id)
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                logger.debug("Browser was already closed during shutdown: %s", e)
            self._browser = None
        if self._persistent_context:
            try:
                await self._persistent_context.close()
            except Exception as e:
                logger.debug("Persistent browser profile was already closed: %s", e)
            self._persistent_context = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.debug("Playwright was already stopped during shutdown: %s", e)
            self._playwright = None
        logger.info("BrowserSessionManager shut down cleanly.")


session_manager = BrowserSessionManager()

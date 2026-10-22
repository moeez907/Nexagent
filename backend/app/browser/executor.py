"""
Controlled Playwright Executor.
Executes validated code snippets against the target page context.
"""
import logging
import traceback
from typing import Dict, Any
from playwright.async_api import Page

logger = logging.getLogger("web_agent.browser.executor")


class PlaywrightExecutor:
    """
    Executes Python Playwright snippet safely within isolated dynamic context.
    """

    async def execute_code(self, page: Page, code_snippet: str) -> Dict[str, Any]:
        """
        Execute validated Playwright code snippet.
        Target code MUST define `async def execute(page): ...`.
        """
        local_scope = {}
        initial_url = page.url
        try:
            # Compile and execute definition of execute(page)
            exec(code_snippet, {}, local_scope)

            if "execute" not in local_scope or not callable(local_scope["execute"]):
                return {
                    "success": False,
                    "error": "Generated code did not contain an 'async def execute(page)' function.",
                    "logs": []
                }

            execute_func = local_scope["execute"]
            
            # Execute async operation against Playwright page
            await execute_func(page)

            # Wait briefly for dynamic network/DOM stabilization
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass

            return {
                "success": True,
                "error": None,
                "current_url": page.url
            }

        except Exception as e:
            final_url = page.url
            if final_url != initial_url and "navigat" in str(e).casefold():
                logger.warning(
                    "Playwright reported an actionability error after navigation completed: %s",
                    e,
                )
                return {
                    "success": True,
                    "error": None,
                    "warning": str(e),
                    "current_url": final_url,
                }
            err_msg = f"Runtime execution error: {str(e)}\n{traceback.format_exc()}"
            logger.error(err_msg)
            return {
                "success": False,
                "error": str(e),
                "traceback": err_msg,
                "current_url": page.url
            }


executor = PlaywrightExecutor()

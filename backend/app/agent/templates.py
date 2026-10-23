"""
Reusable Automation Templates for Playwright Web Automation.
Provides fast-path deterministic code templates for standard web browser operations.
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("web_agent.agent.templates")


class AutomationTemplateRegistry:
    """
    Registry of reusable Playwright Python code snippets.
    Generates single-step execution code `async def execute(page):` from action intents.
    """

    @staticmethod
    def generate_code(action_intent: Dict[str, Any]) -> Optional[str]:
        """
        Attempts to match structured action intent to a deterministic automation template.
        Returns executable Python snippet or None if no standard template matches.
        """
        action = action_intent.get("action", "")
        target = action_intent.get("target") or {}

        if action == "navigate":
            url = target.get("url")
            if url:
                return (
                    "async def execute(page):\n"
                    f"    await page.goto('{url}', wait_until='domcontentloaded', timeout=30000)"
                )

        elif action == "search":
            query = target.get("text", "")
            ref = str(target.get("ref") or "")
            if query and ref:
                safe_query = query.replace("'", "\\'")
                safe_ref = ref.replace('"', '&quot;')
                return (
                    "async def execute(page):\n"
                    f"    search_box = page.locator('[data-agent-ref=\"{safe_ref}\"]').first\n"
                    f"    await search_box.click()\n"
                    f"    await search_box.press_sequentially('{safe_query}', delay=60)\n"
                    "    await search_box.press('Enter')"
                )

        elif action == "click":
            ref = str(target.get("ref") or "")

            if ref:
                safe_ref = ref.replace("'", "\\'")
                return (
                    "async def execute(page):\n"
                    f"    loc = page.locator('[data-agent-ref=\"{safe_ref}\"]').first\n"
                    f"    try:\n"
                    f"        await loc.click(timeout=7000)\n"
                    f"    except Exception:\n"
                    f"        await loc.click(timeout=5000, force=True)"
                )

        elif action in {"fill", "fill_form"}:
            fields = target.get("fields")
            if fields and isinstance(fields, list):
                lines = ["async def execute(page):"]
                for item in fields:
                    f_ref = str(item.get("ref") or "").strip()
                    if not f_ref:
                        continue
                    safe_ref = f_ref.replace("'", "\\'").replace('"', '&quot;')
                    f_act = str(item.get("action") or "fill").lower()
                    f_text = str(item.get("text") if item.get("text") is not None else item.get("value", "")).replace("'", "\\'")
                    if f_act in {"fill", "type"}:
                        lines.append(f"    await page.locator('[data-agent-ref=\"{safe_ref}\"]').first.fill('{f_text}')")
                    elif f_act == "select_option":
                        opt_arg = "value" if item.get("value") else "label"
                        lines.append(f"    await page.locator('[data-agent-ref=\"{safe_ref}\"]').first.select_option({opt_arg}='{f_text}')")
                    elif f_act in {"check", "uncheck"}:
                        lines.append(f"    await page.locator('[data-agent-ref=\"{safe_ref}\"]').first.click(timeout=15000)")
                    elif f_act == "click":
                        lines.append(f"    await page.locator('[data-agent-ref=\"{safe_ref}\"]').first.click(timeout=15000)")
                if len(lines) > 1:
                    return "\n".join(lines)

            ref = target.get("ref")
            text = target.get("text", "")

            if ref:
                safe_ref = str(ref).replace("'", "\\'")
                safe_text = str(text).replace("'", "\\'")
                return (
                    "async def execute(page):\n"
                    f"    await page.locator('[data-agent-ref=\"{safe_ref}\"]').first.fill('{safe_text}')"
                )
        elif action == "select_option":
            option_value = target.get("value")
            option_label = target.get("text")
            ref = str(target.get("ref") or "")
            if ref and (option_value or option_label):
                option_argument = "value" if option_value else "label"
                option_text = option_value if option_value else option_label
                safe_option_text = str(option_text).replace("'", "\\'")
                safe_ref = ref.replace('"', '&quot;')
                return (
                    "async def execute(page):\n"
                    f"    dropdown = page.locator('[data-agent-ref=\"{safe_ref}\"]').first\n"
                    f"    await dropdown.select_option({option_argument}='{safe_option_text}')"
                )

        elif action == "press":
            key = target.get("text", "Enter")
            return (
                "async def execute(page):\n"
                f"    await page.keyboard.press('{key}')"
            )

        elif action == "go_back":
            return (
                "async def execute(page):\n"
                "    await page.go_back()"
            )

        elif action == "wait":
            duration_ms = target.get("duration_ms", 2000)
            return (
                "async def execute(page):\n"
                f"    await page.wait_for_timeout({duration_ms})"
            )

        elif action in ["extract", "extract_text", "finish"]:
            return (
                "async def execute(page):\n"
                "    pass"
            )

        elif action == "file_upload":
            ref = str(target.get("ref") or "").replace('"', '&quot;')
            file_path = target.get("file_path", "")
            if ref and file_path:
                return (
                    "async def execute(page):\n"
                    f"    await page.locator('[data-agent-ref=\"{ref}\"]').set_input_files('{file_path}')"
                )

        elif action in {"dialog", "handle_popup"} and target.get("native_dialog"):
            dialog_action = target.get("dialog_action") or target.get("popup_action", "dismiss")
            if dialog_action == "accept":
                return (
                    "async def execute(page):\n"
                    "    page.once('dialog', lambda dialog: dialog.accept())\n"
                )
            else:
                return (
                    "async def execute(page):\n"
                    "    page.once('dialog', lambda dialog: dialog.dismiss())\n"
                )

        elif action == "dialog":
            dialog_action = target.get("dialog_action", "accept")
            if dialog_action == "accept":
                return (
                    "async def execute(page):\n"
                    "    page.once('dialog', lambda dialog: dialog.accept())\n"
                )
            return (
                "async def execute(page):\n"
                "    page.once('dialog', lambda dialog: dialog.dismiss())\n"
            )

        elif action == "screenshot":
            path = target.get("path", "screenshot.png")
            return (
                "async def execute(page):\n"
                f"    await page.screenshot(path='{path}', full_page=True)"
            )

        elif action == "hover":
            ref = str(target.get("ref") or "").replace('"', '&quot;')
            if ref:
                return (
                    "async def execute(page):\n"
                    f"    await page.locator('[data-agent-ref=\"{ref}\"]').first.hover()"
                )

        elif action in {"check", "uncheck"}:
            ref = str(target.get("ref") or "").replace('"', '&quot;')
            if ref:
                return (
                    "async def execute(page):\n"
                    f"    await page.locator('[data-agent-ref=\"{ref}\"]').first.{action}()"
                )

        return None

    @staticmethod
    def list_templates() -> Dict[str, Dict[str, str]]:
        """
        Returns metadata about available automation templates.
        """
        return {
            "navigate": {"description": "Navigates browser to target URL with DOM content loaded wait strategy."},
            "click": {"description": "Clicks the exact live DOM ref selected by the planner."},
            "fill": {"description": "Fills form field input element with text content."},
            "select_option": {"description": "Selects dropdown menu option by value or label."},
            "press": {"description": "Sends keyboard key events (e.g. Enter, Tab, Escape)."},
            "go_back": {"description": "Navigates back to the previous page in history."},
            "wait": {"description": "Waits for explicit selector or timeout duration."},
            "extract": {"description": "Extracts required data from the current observed DOM."},
            "extract_text": {"description": "Extracts inner text content from selector target."},
            "file_upload": {"description": "Uploads specified file to file input field."},
            "dialog": {"description": "Attaches event listener to accept or dismiss modal JavaScript dialogs."},
            "handle_popup": {"description": "Handles a goal-relevant DOM popup or native JavaScript dialog."},
            "screenshot": {"description": "Captures full page PNG screenshot."},
            "hover": {"description": "Hovers the exact live DOM ref selected by the planner."},
            "check": {"description": "Checks the exact live DOM ref selected by the planner."},
            "uncheck": {"description": "Unchecks the exact live DOM ref selected by the planner."},
        }


template_registry = AutomationTemplateRegistry()

"""
Code Validator.
Performs AST static security inspection and Playwright API validation.
"""
import ast
import logging
from typing import Dict, Any, List, Optional, Set

from app.agent.url_guard import url_guard

logger = logging.getLogger("web_agent.agent.validator")


class ASTSecurityVisitor(ast.NodeVisitor):
    """
    AST Visitor to reject unsafe imports, system calls, and unauthorized operations.
    """

    FORBIDDEN_MODULES = {"os", "sys", "subprocess", "socket", "shutil", "builtins", "importlib", "ctypes", "requests", "urllib"}
    FORBIDDEN_FUNCTIONS = {"eval", "exec", "__import__", "compile", "open", "input", "globals", "locals"}

    def __init__(self):
        self.errors: List[str] = []
        self.navigation_urls: List[str] = []
        self.locator_refs: List[str] = []
        self.forbidden_locator_methods = {
            "get_by_role", "get_by_text", "get_by_label", "get_by_placeholder",
            "get_by_test_id", "frame_locator",
        }

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            if alias.name.split('.')[0] in self.FORBIDDEN_MODULES:
                self.errors.append(f"Forbidden import: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module and node.module.split('.')[0] in self.FORBIDDEN_MODULES:
            self.errors.append(f"Forbidden import from: '{node.module}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Detect forbidden functions
        if isinstance(node.func, ast.Name):
            if node.func.id in self.FORBIDDEN_FUNCTIONS:
                self.errors.append(f"Forbidden function call: '{node.func.id}'")

        # Detect page.goto(url) calls to extract target URL for URLPolicyGuard check
        if isinstance(node.func, ast.Attribute) and node.func.attr == "goto":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                self.navigation_urls.append(node.args[0].value)

        if isinstance(node.func, ast.Attribute):
            if node.func.attr in self.forbidden_locator_methods:
                self.errors.append(f"Locator must use a live data-agent-ref; forbidden method: '{node.func.attr}'")
            if node.func.attr == "locator":
                if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                    self.errors.append("Locator selector must be a literal live data-agent-ref.")
                else:
                    selector = node.args[0].value
                    if not selector.startswith('[data-agent-ref="') or not selector.endswith('"]'):
                        self.errors.append("Raw CSS/XPath selectors are forbidden; use a live data-agent-ref.")
                    else:
                        self.locator_refs.append(selector[len('[data-agent-ref="'):-2])

        self.generic_visit(node)


class CodeValidator:
    """
    Validates generated Playwright Python code snippets.
    """

    def validate_code(
        self,
        task_id: str,
        code_snippet: str,
        browser_state: Optional[Dict[str, Any]] = None,
        action_intent: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not code_snippet or not code_snippet.strip():
            return {"is_valid": False, "error": "Generated code snippet is empty."}

        # 1. Syntax Validation
        try:
            tree = ast.parse(code_snippet)
        except SyntaxError as e:
            return {"is_valid": False, "error": f"Python syntax error in generated code: {e}"}

        # 2. AST Security Inspection
        visitor = ASTSecurityVisitor()
        visitor.visit(tree)

        if visitor.errors:
            error_str = "; ".join(visitor.errors)
            logger.warning(f"AST Security Violation for task {task_id}: {error_str}")
            return {"is_valid": False, "error": f"AST Security Violation: {error_str}"}

        execute_functions = [
            node for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "execute"
        ]
        if len(execute_functions) != 1 or len(execute_functions[0].args.args) != 1 or execute_functions[0].args.args[0].arg != "page":
            return {"is_valid": False, "error": "Generated code must define exactly async def execute(page)."}

        live_refs: Set[str] = {
            str(element.get("ref"))
            for element in (browser_state or {}).get("interactive_elements", [])
            if element.get("ref")
        }
        unknown_refs = sorted(set(visitor.locator_refs) - live_refs) if browser_state is not None else []
        if unknown_refs:
            return {"is_valid": False, "error": f"Generated code targets stale or unknown live refs: {unknown_refs}."}

        if action_intent and ((action_intent.get("action") == "scroll") or "scroll" in code_snippet.casefold() or "window.evaluate" in code_snippet):
            return {"is_valid": False, "error": "Scrolling and arbitrary page evaluation are not allowed actions."}

        action = (action_intent or {}).get("action")
        target = (action_intent or {}).get("target") or {}
        interactive_actions = {"search", "click", "fill", "fill_form", "select_option", "check", "uncheck", "handle_popup", "hover"}
        if action in interactive_actions:
            if action == "fill_form" or target.get("fields"):
                fields = target.get("fields") or []
                expected_refs = {str(f.get("ref")) for f in fields if f.get("ref")}
                if not expected_refs and target.get("ref"):
                    expected_refs = {str(target.get("ref"))}
                if not expected_refs:
                    return {"is_valid": False, "error": f"Action '{action}' requires live target refs."}
                if any(ref not in live_refs for ref in visitor.locator_refs):
                    return {"is_valid": False, "error": "Generated code uses a locator outside the live DOM refs."}
                if any(ref not in expected_refs for ref in visitor.locator_refs):
                    return {"is_valid": False, "error": "Generated code uses a locator outside the selected target fields."}
            else:
                expected_ref = str(target.get("ref") or "")
                if not expected_ref:
                    return {"is_valid": False, "error": f"Action '{action}' requires a live target ref."}
                if expected_ref not in visitor.locator_refs:
                    return {"is_valid": False, "error": "Generated code does not use the selected live target ref."}
                if any(ref != expected_ref for ref in visitor.locator_refs):
                    return {"is_valid": False, "error": "Generated code uses a locator outside the selected live target."}

        # 3. URL Policy Validation for page.goto calls
        for url in visitor.navigation_urls:
            is_allowed = url_guard.validate_navigation_target(task_id, url)
            if not is_allowed:
                return {
                    "is_valid": False,
                    "error": f"URL Policy Guard Violation: URL '{url}' is hallucinated or unauthorized."
                }

        return {"is_valid": True, "error": None}


code_validator = CodeValidator()

"""
URL Policy Guard.
Strict security & correctness module preventing LLM URL hallucinations.
"""
import logging
import re
from typing import Dict, Set, List, Optional
from urllib.parse import urlparse, urlunparse

from app.core.state_machine import URLProvenanceSource

logger = logging.getLogger("web_agent.agent.url_guard")


class URLPolicyGuard:
    """
    Enforces URL provenance rules. Reject fabricated, guessed, or LLM-generated URLs.
    """

    def __init__(self):
        # Maps task_id -> Set of allowed URLs discovered by browser
        self._allowed_urls: Dict[str, Set[str]] = {}
        # Maps task_id -> Set of user-provided explicit URLs
        self._user_urls: Dict[str, Set[str]] = {}

    def extract_urls_from_text(self, text: str) -> List[str]:
        """Extract explicit HTTP/HTTPS URLs from text."""
        url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
        matches = re.findall(url_pattern, text)
        cleaned = []
        for m in matches:
            if not m.startswith("http"):
                m = "https://" + m
            cleaned.append(self._normalize_url(m))
        return cleaned

    def _normalize_url(self, url: str) -> str:
        """Normalize URL syntax without changing its destination path."""
        parsed = urlparse(url.strip())
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return ""
        port = parsed.port
        netloc = hostname
        if port and not ((parsed.scheme.lower() == "http" and port == 80) or (parsed.scheme.lower() == "https" and port == 443)):
            netloc = f"{hostname}:{port}"
        path = parsed.path or "/"
        return urlunparse((parsed.scheme.lower(), netloc, path, parsed.params, parsed.query, ""))

    def register_user_urls(self, task_id: str, goal_text: str) -> List[str]:
        """Identify and register user-provided explicit URLs from task goal."""
        urls = self.extract_urls_from_text(goal_text)
        if task_id not in self._user_urls:
            self._user_urls[task_id] = set()
        for u in urls:
            self._user_urls[task_id].add(self._normalize_url(u))
            logger.info(f"Registered user-provided URL for task {task_id}: {u}")
        return urls

    def register_discovered_links(self, task_id: str, links: List[Dict[str, str]]):
        """Register browser-discovered links during observation."""
        if task_id not in self._allowed_urls:
            self._allowed_urls[task_id] = set()
        for link in links:
            url = link.get("url")
            if url and url.startswith("http"):
                normalized_url = self._normalize_url(url)
                if normalized_url:
                    self._allowed_urls[task_id].add(normalized_url)

    def validate_navigation_target(
        self,
        task_id: str,
        target_url: str,
        claimed_source: Optional[str] = None
    ) -> bool:
        """
        Validate whether target_url is authorized by provenance.
        Returns True if allowed, False if rejected (LLM hallucination/guess).
        """
        normalized_target = self._normalize_url(target_url) if target_url else ""
        if not normalized_target:
            logger.warning(f"URL Policy Violation: Malformed target URL '{target_url}'")
            return False

        # Search engine URLs are default allowed entry points
        search_engine_hosts = {"google.com", "www.google.com", "bing.com", "www.bing.com", "duckduckgo.com", "www.duckduckgo.com", "yahoo.com", "www.yahoo.com"}
        parsed = urlparse(normalized_target)
        domain = parsed.hostname or ""
        if domain in search_engine_hosts:
            logger.info(f"URL Policy: Allowed search engine target '{normalized_target}'")
            return True

        # Check if user-provided
        user_set = self._user_urls.get(task_id, set())
        if normalized_target in user_set:
            logger.info(f"URL Policy: Allowed user-provided URL '{normalized_target}'")
            return True

        # Check if browser-discovered link
        discovered_set = self._allowed_urls.get(task_id, set())
        if normalized_target in discovered_set:
            logger.info(f"URL Policy: Allowed browser-discovered link '{normalized_target}'")
            return True

        # Check if same-domain as an already allowed user or discovered URL
        allowed_domains = {
            (urlparse(u).hostname or "").lower()
            for u in user_set.union(discovered_set)
            if (urlparse(u).hostname or "").lower()
        }
        if domain.lower() in allowed_domains:
            logger.info(f"URL Policy: Allowed same-domain target '{normalized_target}' on verified domain '{domain}'")
            return True

        logger.warning(
            f"URL Policy VIOLATION REJECTED for task {task_id}: "
            f"URL '{normalized_target}' was not in user input or browser discovered links! "
            f"(Source claimed: '{claimed_source}')"
        )
        return False


url_guard = URLPolicyGuard()


import os
import re
import glob
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger("web_agent.rag.indexer")


class DocumentIndexer:
    """
    Parses Playwright HTML documentation files and chunks them into semantic documents
    suitable for vector embedding and retrieval.
    """

    def __init__(self, docs_path: str):
        self.docs_path = docs_path

    def _determine_category(self, filename: str, content_sample: str) -> str:
        """
        Categorizes documentation based on filename and contents.
        """
        fn = filename.lower()
        if "locator" in fn:
            return "locators"
        elif "assert" in fn:
            return "assertions"
        elif "auth" in fn:
            return "authentication"
        elif "frame" in fn:
            return "frames"
        elif "dialog" in fn:
            return "dialogs"
        elif "network" in fn or "mock" in fn:
            return "network"
        elif "download" in fn:
            return "downloads"
        elif "upload" in fn or "input" in fn:
            return "input"
        elif "event" in fn:
            return "events"
        elif "page" in fn:
            return "pages"
        elif "browser" in fn:
            return "browsers"
        elif "codegen" in fn:
            return "codegen"
        elif "trace" in fn or "debug" in fn:
            return "debugging"
        return "general"

    def _extract_code_snippets(self, soup: BeautifulSoup) -> List[str]:
        """
        Extracts code snippets from <pre> and <code> blocks.
        """
        snippets = []
        for code_elem in soup.find_all(["pre", "code"]):
            text = code_elem.get_text().strip()
            if text and ("page." in text or "playwright" in text or "await " in text or "def " in text):
                # Keep reasonably sized snippets
                if 10 <= len(text) <= 2000:
                    snippets.append(text)
        return snippets[:10]

    def _chunk_text(self, text: str, max_chars: int = 800, overlap: int = 150) -> List[str]:
        """
        Splits long text into overlapping chunks.
        """
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) <= max_chars:
            return [text] if text else []

        chunks = []
        start = 0
        while start < len(text):
            end = start + max_chars
            if end < len(text):
                # Break at sentence or word boundary if possible
                last_space = text.rfind(' ', start + max_chars - 100, end)
                if last_space != -1 and last_space > start:
                    end = last_space
            chunk = text[start:end].strip()
            if len(chunk) >= 50:
                chunks.append(chunk)
            start = end - overlap if end < len(text) else len(text)

        return chunks

    def load_and_chunk_docs(self) -> List[Dict[str, Any]]:
        """
        Scans docs_path recursively for .html files and parses them into semantic chunks.
        """
        if not os.path.exists(self.docs_path):
            logger.warning(f"Docs path does not exist: {self.docs_path}")
            return []

        html_files = glob.glob(f"{self.docs_path}/**/*.html", recursive=True)
        html_files += glob.glob(f"{self.docs_path}/*.html")
        html_files = list(set(html_files))

        logger.info(f"Found {len(html_files)} HTML documentation files for indexing.")
        all_chunks: List[Dict[str, Any]] = []

        for filepath in html_files:
            filename = os.path.basename(filepath)
            rel_path = os.path.relpath(filepath, self.docs_path)

            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    soup = BeautifulSoup(f.read(), "html.parser")

                # Remove script and style elements
                for script in soup(["script", "style", "nav", "footer"]):
                    script.extract()

                # Title extraction
                title_tag = soup.find("title") or soup.find("h1")
                doc_title = title_tag.get_text().strip() if title_tag else filename.replace(".html", "")

                category = self._determine_category(filename, str(soup))
                code_snippets = self._extract_code_snippets(soup)

                # Extract sections by heading tags (h1, h2, h3)
                sections = []
                headings = soup.find_all(["h1", "h2", "h3"])

                if headings:
                    for i, heading in enumerate(headings):
                        h_title = heading.get_text().strip()
                        content_parts = []
                        curr = heading.next_sibling
                        while curr:
                            if isinstance(curr, Tag) and curr.name in ["h1", "h2", "h3"]:
                                break
                            if isinstance(curr, Tag):
                                content_parts.append(curr.get_text(separator=" ", strip=True))
                            elif isinstance(curr, str):
                                content_parts.append(curr.strip())
                            curr = curr.next_sibling
                        
                        section_text = " ".join(filter(None, content_parts))
                        if section_text:
                            sections.append((h_title, section_text))

                if not sections:
                    # Fallback if no headings found
                    full_text = soup.get_text(separator=" ", strip=True)
                    sections.append((doc_title, full_text))

                # Create chunks from sections
                chunk_index = 0
                for sec_title, sec_text in sections:
                    text_chunks = self._chunk_text(sec_text, max_chars=800, overlap=150)
                    for text_chunk in text_chunks:
                        chunk_id = f"{filename}_{chunk_index}"
                        chunk_index += 1
                        
                        # Find code snippet relevant to chunk if present
                        chunk_code = [c for c in code_snippets if any(term in c.lower() for term in sec_title.lower().split()[:2])]

                        all_chunks.append({
                            "id": chunk_id,
                            "filename": filename,
                            "filepath": rel_path,
                            "doc_title": doc_title,
                            "section_title": sec_title,
                            "category": category,
                            "content": f"{sec_title}: {text_chunk}",
                            "raw_text": text_chunk,
                            "code_snippets": chunk_code[:2] if chunk_code else code_snippets[:1],
                        })

            except Exception as e:
                logger.error(f"Error processing doc file {filepath}: {e}")

        logger.info(f"Generated total of {len(all_chunks)} semantic chunks from Playwright documentation.")
        return all_chunks

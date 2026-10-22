
import os
import glob
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

from app.core.config import settings
from app.rag.document_indexer import DocumentIndexer
from app.rag.vector_store import VectorStore

logger = logging.getLogger("web_agent.rag.playwright_rag")


class PlaywrightKnowledgeRAG:
    """
    Full-featured Playwright Knowledge RAG system with ChromaDB integration,
    semantic search, prompt augmentation, and keyword fallback.
    """

    def __init__(self, docs_path: str = settings.PLAYWRIGHT_DOCS_PATH):
        self.docs_path = docs_path
        self._abs_docs_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", self.docs_path))
        self.indexer = DocumentIndexer(self._abs_docs_path)
        self.vector_store = VectorStore()

    def index_documentation(self) -> Dict[str, Any]:
        """
        Runs document indexing and stores semantic chunks in ChromaDB.
        """
        logger.info(f"Starting documentation indexing from: {self._abs_docs_path}")
        chunks = self.indexer.load_and_chunk_docs()
        count = self.vector_store.add_documents(chunks)
        return {
            "status": "success",
            "indexed_chunks": count,
            "docs_path": self._abs_docs_path,
            "vector_stats": self.vector_store.get_stats()
        }

    def ensure_indexed(self):
        """
        Ensures ChromaDB index contains documents; triggers index if collection is empty.
        """
        if self.vector_store.collection.count() == 0 and os.path.exists(self._abs_docs_path):
            logger.info("ChromaDB index empty. Auto-triggering document indexing...")
            self.index_documentation()

    def search_knowledge(
        self,
        query: str,
        top_k: int = settings.RAG_TOP_K,
        category_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search Playwright documentation semantically via ChromaDB vector index.
        Falls back to keyword matching if vector store is empty.
        """
        if not settings.RAG_ENABLED:
            return []

        self.ensure_indexed()

        # Semantic Search via ChromaDB
        results = self.vector_store.search(query, top_k=top_k, category_filter=category_filter)
        if results:
            return results

        # Keyword Fallback if vector store returned no results
        logger.info(f"Semantic search returned empty results for '{query}'. Running keyword fallback.")
        return self._keyword_search_fallback(query, top_k)

    def _keyword_search_fallback(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """
        Simple BM25 / keyword search fallback over raw HTML documentation.
        """
        if not os.path.exists(self._abs_docs_path):
            return []

        query_terms = set(query.lower().split())
        html_files = glob.glob(f"{self._abs_docs_path}/**/*.html", recursive=True)
        results = []

        for filepath in html_files[:20]:
            try:
                filename = os.path.basename(filepath)
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    soup = BeautifulSoup(f.read(), "html.parser")
                    text = soup.get_text(separator=" ", strip=True)
                    score = sum(1 for term in query_terms if term in text.lower())
                    if score > 0:
                        results.append({
                            "filename": filename,
                            "section_title": filename.replace(".html", "").title(),
                            "category": "general",
                            "snippet": text[:400],
                            "code_snippets": [],
                            "score": float(score)
                        })
            except Exception:
                continue

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def augment_prompt(self, base_prompt: str, action_intent: Dict[str, Any]) -> str:
        """
        Augments prompt with retrieved Playwright API documentation and code snippets.
        """
        action = action_intent.get("action", "")
        target = action_intent.get("target", {})
        recovery_context = action_intent.get("recovery_context", "")
        failed_code = action_intent.get("failed_code", "")
        retry_number = action_intent.get("retry_number", "")
        recovery_query = (
            "Find the correct Playwright Python repair for a failed browser action. "
            f"Action: {action}. Intent: {action_intent.get('intent', '')}. "
            f"Target: {target}. Retry: {retry_number}. Failure: {recovery_context}. "
            f"Failed code: {failed_code}. "
            "Which alternative locator, Playwright action, or code pattern should replace it?"
        )
        query = (
            f"playwright python {recovery_query} {target.get('text', '')} "
            f"{target.get('selector', '')}"
        ).strip()

        docs = self.search_knowledge(query, top_k=2)
        if not docs:
            return base_prompt

        augmented_context = "\n--- PLAYWRIGHT KNOWLEDGE RAG CONTEXT ---\n"
        augmented_context += (
            "Analyze these references against the failed code and current DOM. "
            "Generate corrected code; do not copy an example blindly and do not invent URLs.\n"
        )
        for doc in docs:
            augmented_context += f"• Section: {doc.get('section_title', 'General')} ({doc.get('filename', '')})\n"
            augmented_context += f"  Snippet: {doc.get('snippet', '')[:300]}\n"
            if doc.get("code_snippets"):
                augmented_context += f"  Code Example:\n  {doc['code_snippets'][0][:250]}\n"
        augmented_context += "---------------------------------------\n"

        return f"{base_prompt}\n{augmented_context}"

    def get_rag_stats(self) -> Dict[str, Any]:
        """
        Retrieves index and status statistics.
        """
        return {
            "rag_enabled": settings.RAG_ENABLED,
            "docs_path": self._abs_docs_path,
            "docs_exist": os.path.exists(self._abs_docs_path),
            "vector_store_stats": self.vector_store.get_stats()
        }


# Global RAG Singleton
class _LazyRAGService:
    def __init__(self):
        self._service = None

    def __getattr__(self, name):
        if self._service is None:
            self._service = PlaywrightKnowledgeRAG()
        return getattr(self._service, name)


rag_service = _LazyRAGService()

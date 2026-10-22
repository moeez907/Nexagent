
import os
import json
import logging
from typing import List, Dict, Any, Optional

import chromadb
from chromadb.utils import embedding_functions

from app.core.config import settings

logger = logging.getLogger("web_agent.rag.vector_store")


class VectorStore:
    """
    ChromaDB vector database manager supporting BAAI/bge-m3 embeddings and semantic retrieval.
    """

    def __init__(
        self,
        persist_dir: str = settings.CHROMA_DB_DIR,
        collection_name: str = settings.RAG_COLLECTION_NAME,
        model_name: str = settings.RAG_EMBEDDING_MODEL
    ):
        self.persist_dir = os.path.abspath(persist_dir)
        self.collection_name = collection_name
        self.model_name = model_name
        
        # Ensure persistence directory exists
        os.makedirs(self.persist_dir, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=self.persist_dir)
        self.embedding_function = self._init_embedding_function()
        try:
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"}
            )
        except ValueError as e:
            if "Embedding function conflict" in str(e):
                logger.warning(
                    f"Embedding function conflict on collection '{self.collection_name}'. "
                    "Recreating collection to use updated embedding function."
                )
                try:
                    self.client.delete_collection(name=self.collection_name)
                except Exception:
                    pass
                self.collection = self.client.create_collection(
                    name=self.collection_name,
                    embedding_function=self.embedding_function,
                    metadata={"hnsw:space": "cosine"}
                )
            else:
                raise e
        logger.info(f"ChromaDB VectorStore initialized at '{self.persist_dir}' using model '{self.model_name}'.")

    def _init_embedding_function(self):
        """
        Initializes embedding function for BAAI/bge-m3 with fallback to ONNX default embedding.
        """
        try:
            # Try sentence-transformers BAAI/bge-m3 if available
            import sentence_transformers
            logger.info(f"Loading SentenceTransformer embedding function with model: {self.model_name}")
            return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=self.model_name)
        except Exception as e:
            logger.warning(f"Could not load SentenceTransformer '{self.model_name}': {e}. Falling back to default ONNX embeddings.")
            return embedding_functions.DefaultEmbeddingFunction()

    def add_documents(self, chunks: List[Dict[str, Any]]) -> int:
        """
        Adds or updates document chunks in the ChromaDB collection.
        """
        if not chunks:
            return 0

        ids = [c["id"] for c in chunks]
        documents = [c["content"] for c in chunks]
        metadatas = [
            {
                "filename": c["filename"],
                "filepath": c["filepath"],
                "doc_title": c["doc_title"],
                "section_title": c["section_title"],
                "category": c["category"],
                "code_snippets": json.dumps(c.get("code_snippets", [])),
                "raw_text": c["raw_text"][:500]
            }
            for c in chunks
        ]

        # Batch upsert to ChromaDB
        batch_size = 100
        for i in range(0, len(chunks), batch_size):
            end = i + batch_size
            self.collection.upsert(
                ids=ids[i:end],
                documents=documents[i:end],
                metadatas=metadatas[i:end]
            )

        logger.info(f"Successfully indexed {len(chunks)} document chunks into ChromaDB collection '{self.collection_name}'.")
        return len(chunks)

    def search(
        self,
        query: str,
        top_k: int = settings.RAG_TOP_K,
        category_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes semantic vector search for a query string.
        """
        if self.collection.count() == 0:
            logger.warning("Vector store is empty. No results returned.")
            return []

        where_clause = {"category": category_filter} if category_filter else None

        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, self.collection.count()),
            where=where_clause
        )

        formatted_results = []
        if results and results.get("ids") and results["ids"][0]:
            ids = results["ids"][0]
            docs = results["documents"][0]
            metadatas = results["metadatas"][0]
            distances = results["distances"][0] if "distances" in results and results["distances"] else [0.0] * len(ids)

            for i in range(len(ids)):
                meta = metadatas[i]
                code_snippets = []
                if "code_snippets" in meta and meta["code_snippets"]:
                    try:
                        code_snippets = json.loads(meta["code_snippets"])
                    except Exception:
                        code_snippets = []

                similarity_score = round(1.0 - distances[i], 4) if distances[i] <= 1.0 else round(1.0 / (1.0 + distances[i]), 4)

                formatted_results.append({
                    "id": ids[i],
                    "filename": meta.get("filename", ""),
                    "doc_title": meta.get("doc_title", ""),
                    "section_title": meta.get("section_title", ""),
                    "category": meta.get("category", ""),
                    "snippet": docs[i],
                    "code_snippets": code_snippets,
                    "score": similarity_score,
                })

        return formatted_results

    def get_stats(self) -> Dict[str, Any]:
        """
        Returns index stats including doc count and embedding metadata.
        """
        count = self.collection.count()
        return {
            "collection_name": self.collection_name,
            "document_count": count,
            "embedding_model": self.model_name,
            "persist_dir": self.persist_dir,
            "is_indexed": count > 0
        }

import chromadb
from chromadb.utils import embedding_functions
import os
from typing import List, Dict, Optional

PERSIST_DIR = os.path.join(os.path.dirname(__file__), 'chroma_db')
COLLECTION_NAME = 'sterling_vance_policy'

class PolicyVectorStore:
    """ChromaDB-backed vector store with HNSW index, metadata payload, and metadata filtering."""
    def __init__(self, persist_dir=PERSIST_DIR, embedding_model='all-MiniLM-L6-v2'):
        self.client = chromadb.PersistentClient(path=persist_dir)
        try:
            self.ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=embedding_model)
        except Exception:
            self.ef = embedding_functions.DefaultEmbeddingFunction()
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self.ef,
            metadata={'hnsw:space': 'cosine'}
        )
  
    def ingest(self, chunks: List[Dict], reset: bool = False) -> int:
        if reset:
            try:
                self.client.delete_collection(name=COLLECTION_NAME)
            except Exception:
                pass
            self.collection = self.client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=self.ef,
                metadata={'hnsw:space': 'cosine'}
            )
        
        ids = []
        documents = []
        metadatas = []
        for chunk in chunks:
            ids.append(chunk['chunk_id'])
            documents.append(chunk['text'])
            meta = {k: v for k,v in chunk.items() if k not in ('text','chunk_id') and v is not None}
            metadatas.append(meta)
            
        self.collection.add(ids=ids, documents=documents, metadatas=metadatas)
        return len(chunks)
  
    def search(self, query: str, n_results: int = 5, where: Optional[Dict] = None) -> List[Dict]:
        res = self.collection.query(query_texts=[query], n_results=n_results, where=where)
        results = []
        if not res['ids']:
            return results
        for i in range(len(res['ids'][0])):
            results.append({
                'chunk_id': res['ids'][0][i],
                'text': res['documents'][0][i],
                'metadata': res['metadatas'][0][i] if res['metadatas'] else {},
                'distance': res['distances'][0][i] if res['distances'] else 0.0,
                'rank': i
            })
        return results
  
    def search_with_filter(self, query: str, reason_code: str = None, section: str = None, n_results: int = 5) -> List[Dict]:
        where = {}
        if reason_code:
            where['reason_code'] = reason_code
        if section:
            where['section'] = section
        
        if not where:
            where = None
            
        return self.search(query, n_results=n_results, where=where)
  
    def count(self) -> int:
        return self.collection.count()

def get_store(reset=False) -> PolicyVectorStore:
    store = PolicyVectorStore()
    if store.count() == 0 or reset:
        from .chunker import get_chunks
        chunks = get_chunks('section')
        store.ingest(chunks, reset=reset)
    return store

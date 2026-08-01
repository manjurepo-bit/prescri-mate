import os
import re
import math
import json
import uuid
import numpy as np
from collections import Counter
from datetime import datetime
from dotenv import load_dotenv
load_dotenv(override=True)
from qdrant_client import QdrantClient, models
import google.generativeai as genai

# Setup Gemini API Key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Define directories
DB_PATH = "c:/genai/apps/prescimate/qdrant_db"
VOCAB_PATH = "c:/genai/apps/prescimate/vocab.json"
os.makedirs(os.path.dirname(VOCAB_PATH), exist_ok=True)

# Initialize Qdrant Client (In-Memory for lock-free stability and hot-reload compliance)
client = QdrantClient(":memory:")

class LocalSparseVectorizer:
    def __init__(self, vocab_path):
        self.vocab_path = vocab_path
        self.vocab = {}
        self.idf = {}
        self.doc_count = 0
        self.doc_freqs = Counter()
        self.load()

    def load(self):
        if os.path.exists(self.vocab_path):
            try:
                with open(self.vocab_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.vocab = data.get('vocab', {})
                    self.idf = data.get('idf', {})
                    self.doc_count = data.get('doc_count', 0)
                    self.doc_freqs = Counter(data.get('doc_freqs', {}))
            except Exception:
                pass

    def save(self):
        with open(self.vocab_path, 'w', encoding='utf-8') as f:
            json.dump({
                'vocab': self.vocab,
                'idf': self.idf,
                'doc_count': self.doc_count,
                'doc_freqs': dict(self.doc_freqs)
            }, f, indent=2)

    def update_with_doc(self, doc):
        tokens = self._tokenize(doc)
        new_tokens = set(tokens)
        self.doc_count += 1
        
        for token in new_tokens:
            self.doc_freqs[token] += 1
            if token not in self.vocab:
                self.vocab[token] = len(self.vocab)
        
        # Recompute IDF
        for token in self.vocab:
            freq = self.doc_freqs[token]
            self.idf[token] = math.log((self.doc_count - freq + 0.5) / (freq + 0.5) + 1.0)
            
        self.save()

    def _tokenize(self, text):
        return re.findall(r'[a-zA-Z0-9]+', text.lower())

    def transform(self, text):
        tokens = self._tokenize(text)
        counter = Counter(tokens)
        
        indices = []
        values = []
        
        for token, count in counter.items():
            if token in self.vocab:
                idx = self.vocab[token]
                tf = count
                idf = self.idf.get(token, 0.0)
                weight = tf * idf
                indices.append(int(idx))
                values.append(float(weight))
                
        if indices:
            sorted_pairs = sorted(zip(indices, values))
            indices, values = zip(*sorted_pairs)
            return list(indices), list(values)
        return [], []

# Instantiated vectorizer
vectorizer = LocalSparseVectorizer(VOCAB_PATH)

def init_collections():
    """Create collections if they do not exist."""
    # 1. Users collection
    if not client.collection_exists("users"):
        client.create_collection(
            collection_name="users",
            vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE)
        )
    
    # 2. Prescriptions collection (Single Dense Vector)
    if not client.collection_exists("prescriptions_v2"):
        client.create_collection(
            collection_name="prescriptions_v2",
            vectors_config=models.VectorParams(size=768, distance=models.Distance.COSINE)
        )

# Initialize on import
init_collections()

def get_dense_embedding(text, is_query=False):
    """Obtain dense embeddings using Gemini's text-embedding-004."""
    if not GEMINI_API_KEY:
        # Return dummy vector if API key is missing for any reason
        return [0.0] * 768
    
    task_type = "retrieval_query" if is_query else "retrieval_document"
    try:
        response = genai.embed_content(
            model="models/gemini-embedding-001",
            content=text,
            task_type=task_type
        )
        return response['embedding']
    except Exception as e:
        print(f"Embedding error: {e}")
        return [0.0] * 768

# --- User Auth Database Access ---

def create_user(username, password_hash):
    """Add a new user to Qdrant."""
    user_id = str(uuid.uuid4())
    # Add point with dummy vector (all 0s)
    client.upsert(
        collection_name="users",
        points=[
            models.PointStruct(
                id=user_id,
                vector=[0.0] * 768,
                payload={
                    "username": username.strip().lower(),
                    "password_hash": password_hash,
                    "created_at": datetime.now().isoformat()
                }
            )
        ]
    )
    return user_id

def get_user_by_username(username):
    """Fetch user by username from Qdrant payload."""
    clean_username = username.strip().lower()
    search_result = client.scroll(
        collection_name="users",
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="username",
                    match=models.MatchValue(value=clean_username)
                )
            ]
        ),
        limit=1
    )
    
    points = search_result[0]
    if points:
        return {
            "id": points[0].id,
            **points[0].payload
        }
    return None

# --- Prescription History and Hybrid Search ---

def save_prescription(user_id, image_name, extracted_text, raw_meds, explanation, lang_code, translated_explanation):
    """Save parsed prescription to Qdrant using dense index."""
    # Concatenate texts for representation
    full_text = f"{extracted_text} {json.dumps(raw_meds)} {explanation} {translated_explanation}"
    
    # Get dense embedding representation
    dense_vec = get_dense_embedding(full_text, is_query=False)
    
    presc_id = str(uuid.uuid4())
    
    client.upsert(
        collection_name="prescriptions_v2",
        points=[
            models.PointStruct(
                id=presc_id,
                vector=dense_vec,
                payload={
                    "user_id": user_id,
                    "image_name": image_name,
                    "extracted_text": extracted_text,
                    "raw_meds": raw_meds,
                    "explanation": explanation,
                    "lang_code": lang_code,
                    "translated_explanation": translated_explanation,
                    "timestamp": datetime.now().isoformat()
                }
            )
        ]
    )
    return presc_id

def get_user_history(user_id, search_query=None):
    """Retrieve history for a user, performing dense vector search if query is provided."""
    user_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=user_id)
            )
        ]
    )
    
    if not search_query:
        # Regular scroll retrieval (sorted by date inside python, or scroll limits)
        result = client.scroll(
            collection_name="prescriptions_v2",
            scroll_filter=user_filter,
            limit=50
        )
        points = result[0]
        # Sort manually by timestamp desc
        items = [{"id": pt.id, **pt.payload} for pt in points]
        items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return items
    
    # Dense vector search query
    query_dense = get_dense_embedding(search_query, is_query=True)
    
    try:
        dense_search = client.search(
            collection_name="prescriptions_v2",
            query_vector=query_dense,
            query_filter=user_filter,
            limit=10
        )
        return [{"id": pt.id, **pt.payload} for pt in dense_search]
    except Exception as e:
        print(f"Dense search query failed: {e}. Falling back to scrolling.")
        return get_user_history(user_id)

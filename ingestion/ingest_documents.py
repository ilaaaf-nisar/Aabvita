#!/usr/bin/env python3
"""Ingest local knowledge base documents into ChromaDB using 768-dim OpenRouter embeddings."""

import argparse
import hashlib
import os
import re
import time
from pathlib import Path

import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv
from openai import OpenAI
from pypdf import PdfReader

# Resolve project root: Aabvita/
ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT / "knowledge_base"
VECTOR_DB_DIR = ROOT / "vector_db"
ENV_PATH = ROOT / ".env"

if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
    print(f" Loaded environment from: {ENV_PATH}", flush=True)
else:
    print(f" Warning: .env not found at {ENV_PATH}", flush=True)

API_KEY = os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    raise ValueError("OPENROUTER_API_KEY is not set. Please add it to your root .env file.")

EMBEDDING_MODEL = "openai/text-embedding-3-small"

COLLECTIONS = {
    "diet": "diet_knowledge",
    "exercise": "exercise_knowledge",
    "medical": "medical_knowledge",
    "nutrition_technical": "nutrition_technical",
}

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY,
)


def get_embeddings(texts, model=EMBEDDING_MODEL, max_retries=3):
    """Generate 768-dimensional embeddings via OpenRouter."""
    if not texts:
        return []

    for attempt in range(max_retries):
        try:
            response = client.embeddings.create(
                input=texts,
                model=model,
                dimensions=768,  # Request 768-dim output
            )
            vectors = [item.embedding for item in response.data]

            if len(vectors) != len(texts):
                raise RuntimeError("Embedding count mismatch from OpenRouter API.")
            return vectors

        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:
                wait_time = 2 ** (attempt + 1)
                print(f"  [Rate limit] Retrying in {wait_time}s...", flush=True)
                time.sleep(wait_time)
                continue
            raise e


def extract_text_from_file(file_path: Path):
    """Extract text from PDF, TXT, or MD files."""
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        reader = PdfReader(str(file_path))
        for page_number, page in enumerate(reader.pages, start=1):
            raw_text = page.extract_text() or ""
            text = re.sub(r"[ \t]+", " ", raw_text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if text:
                yield page_number, text

    elif suffix in [".txt", ".md"]:
        text = file_path.read_text(encoding="utf-8", errors="ignore").strip()
        if text:
            yield 1, text


def split_text(text, chunk_size=1200, overlap=200):
    """Split text into overlapping character-based chunks."""
    if chunk_size <= overlap or overlap < 0:
        raise ValueError("Invalid chunk size or overlap.")

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start + chunk_size // 2:
                end = boundary

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end == len(text):
            break

        start = max(start + 1, end - overlap)

    return chunks


def ingest_file(collection, file_path, category, batch_size=40):
    """Ingest one file into ChromaDB."""
    relative_path = str(file_path.relative_to(KNOWLEDGE_DIR))
    records = []

    for page_number, page_text in extract_text_from_file(file_path):
        chunks = split_text(page_text)
        for chunk_index, chunk in enumerate(chunks):
            unique_value = f"{category}|{relative_path}|{page_number}|{chunk_index}|{chunk}"
            chunk_id = hashlib.sha256(unique_value.encode("utf-8")).hexdigest()

            records.append({
                "id": chunk_id,
                "text": chunk,
                "metadata": {
                    "source": file_path.name,
                    "relative_path": relative_path,
                    "page": page_number,
                    "chunk": chunk_index,
                    "agent": category,
                    "embedding_model": EMBEDDING_MODEL,
                },
            })

    if not records:
        print(f"  [Empty] No text extracted from {file_path.name}", flush=True)
        return 0

    old = collection.get(where={"relative_path": relative_path}, include=[])
    old_ids = old.get("ids", [])
    if old_ids:
        for i in range(0, len(old_ids), 500):
            collection.delete(ids=old_ids[i : i + 500])

    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        texts = [record["text"] for record in batch]
        vectors = get_embeddings(texts)

        collection.upsert(
            ids=[record["id"] for record in batch],
            documents=texts,
            embeddings=vectors,
            metadatas=[record["metadata"] for record in batch],
        )

    print(f"   Indexed {file_path.name}: {len(records)} chunks", flush=True)
    return len(records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", choices=["all", *COLLECTIONS], default="all")
    parser.add_argument("--reset", action="store_true", help="Reset collections before indexing")
    args = parser.parse_args()

    print(f"\n--- Ingestion Pipeline Started (768 Dimensions) ---", flush=True)
    print(f"Root: {ROOT}", flush=True)
    print(f"Knowledge Directory: {KNOWLEDGE_DIR}", flush=True)
    print(f"Vector DB Directory: {VECTOR_DB_DIR}\n", flush=True)

    VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)

    client_chroma = chromadb.PersistentClient(
        path=str(VECTOR_DB_DIR),
        settings=Settings(anonymized_telemetry=False),
    )

    categories = list(COLLECTIONS) if args.agent == "all" else [args.agent]
    total_chunks = 0

    for category in categories:
        folder = KNOWLEDGE_DIR / category
        collection_name = COLLECTIONS[category]

        print(f"Checking category [{category}] at {folder}...", flush=True)
        if not folder.exists():
            print(f" Directory not found: {folder}", flush=True)
            continue

        files = sorted([
            f for f in folder.rglob("*")
            if f.is_file() and f.suffix.lower() in [".pdf", ".txt", ".md"]
        ])

        if not files:
            print(f"  No documents (.pdf, .txt, .md) found in {folder}", flush=True)
            continue

        if args.reset:
            try:
                client_chroma.delete_collection(collection_name)
                print(f"  Reset existing collection: {collection_name}", flush=True)
            except Exception:
                pass

        collection = client_chroma.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        print(f" Found {len(files)} file(s). Processing...", flush=True)
        for doc_file in files:
            total_chunks += ingest_file(collection, doc_file, category)

    print(f"\n Ingestion complete! Total indexed chunks: {total_chunks}", flush=True)
    print(f" Vector database stored at: {VECTOR_DB_DIR}\n", flush=True)


if __name__ == "__main__":
    main()
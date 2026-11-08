
#!/usr/bin/env python3
"""Validate retrieval from the AI Fitness Coach knowledge base."""

import argparse

import chromadb

from ingest_documents import (
    COLLECTIONS,
    VECTOR_DB_DIR,
    get_embeddings
)

TEST_QUESTIONS = {
    "diet": [
        "What is a balanced diet for Indian adults?",
        "What foods provide dietary protein?",
        "How should a healthy plate be structured?"
    ],
    "exercise": [
        "How do I perform a squat correctly?",
        "What exercises strengthen the chest?",
        "How much physical activity should adults perform?"
    ],
    "medical": [
        "What is chronic kidney disease?",
        "What does elevated serum creatinine indicate?",
        "What factors contribute to obesity?"
    ],
    "nutrition_technical": [
        "How are USDA nutrient values documented?",
        "What is the difference between analytical and calculated nutrient data?"
    ]
}


def search_collection(
    collection,
    query,
    top_k=3
):
    query_vector = get_embeddings([query])[0]

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=min(top_k, collection.count()),
        include=[
            "documents",
            "metadatas",
            "distances"
        ]
    )

    return results


def print_results(query, results):
    print(f"\nQuestion: {query}")
    print("-" * 70)

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for index, (document, metadata, distance) in enumerate(
        zip(documents, metadatas, distances),
        start=1
    ):
        print(f"\nResult {index}")
        print(f"Source: {metadata.get('source')}")
        print(f"Page: {metadata.get('page')}")
        print(f"Cosine distance: {distance:.4f}")
        print(f"Text: {document[:650]}")

    print("\nReview whether these passages answer the question.")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--agent",
        choices=["all", *COLLECTIONS],
        default="all"
    )

    parser.add_argument(
        "--query",
        type=str,
        default=None
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=3
    )

    args = parser.parse_args()

    if args.query and args.agent == "all":
        parser.error(
            "Specify --agent when using a custom --query."
        )

    if args.top_k < 1:
        parser.error("--top-k must be positive.")

    if not VECTOR_DB_DIR.exists():
        raise FileNotFoundError(
            "Vector database not found. Run ingest_documents.py first."
        )

    client = chromadb.PersistentClient(
        path=str(VECTOR_DB_DIR)
    )

    categories = (
        list(COLLECTIONS)
        if args.agent == "all"
        else [args.agent]
    )

    for category in categories:
        collection_name = COLLECTIONS[category]

        try:
            collection = client.get_collection(collection_name)
        except Exception:
            print(f"Missing collection: {collection_name}")
            continue

        count = collection.count()

        if count == 0:
            print(f"Empty collection: {collection_name}")
            continue

        print(f"\n{'=' * 70}")
        print(f"AGENT: {category.upper()}")
        print(f"COLLECTION: {collection_name}")
        print(f"TOTAL CHUNKS: {count}")

        questions = (
            [args.query]
            if args.query
            else TEST_QUESTIONS[category]
        )

        for question in questions:
            results = search_collection(
                collection,
                question,
                top_k=args.top_k
            )

            print_results(question, results)


if __name__ == "__main__":
    main()

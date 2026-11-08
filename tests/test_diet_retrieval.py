from agents import diet_agent, rag_runtime


class _Collection:
    def __init__(self, passages):
        self.passages = passages
        self.queries = []

    def count(self):
        return len(self.passages)

    def query(self, *, query_embeddings, n_results, include):
        self.queries.append((query_embeddings, n_results, include))
        selected = self.passages[:n_results]
        return {
            "documents": [[passage[0] for passage in selected]],
            "metadatas": [[passage[1] for passage in selected]],
            "distances": [[passage[2] for passage in selected]],
        }


class _Client:
    def __init__(self, collections):
        self.collections = collections
        self.requested = []

    def get_collection(self, name):
        self.requested.append(name)
        return self.collections[name]


def test_diet_agent_searches_both_diet_collections(monkeypatch):
    observed = {}

    def fake_answer(question, collections, system_prompt, top_k,
                    tool_context=None, user_context=None):
        observed["collections"] = collections
        return {"answer": "Diet guidance.", "sources": []}

    monkeypatch.setattr(diet_agent, "answer", fake_answer)
    diet_agent.ask_diet("How do I make a balanced Kashmiri meal?")

    assert observed["collections"] == ("diet_knowledge", "nutrition_technical")


def test_multi_collection_retrieval_merges_relevant_passages(monkeypatch, tmp_path):
    diet = _Collection([
        ("General diet passage", {"source": "diet.pdf", "page": 1}, 0.3),
        ("Shared passage", {"source": "shared.pdf", "page": 2}, 0.6),
    ])
    nutrition = _Collection([
        ("Kashmiri nutrition passage", {"source": "recipe.pdf", "page": 4}, 0.1),
        ("Shared passage", {"source": "shared.pdf", "page": 2}, 0.2),
    ])
    client = _Client({
        "diet_knowledge": diet,
        "nutrition_technical": nutrition,
    })
    monkeypatch.setattr(rag_runtime, "DB_PATH", tmp_path)
    monkeypatch.setattr(
        rag_runtime.chromadb, "PersistentClient", lambda path: client
    )
    monkeypatch.setattr(rag_runtime, "embed_texts", lambda texts: [[0.1, 0.2]])

    hits = rag_runtime.retrieve(
        ("diet_knowledge", "nutrition_technical"),
        "Kashmiri meal nutrition",
        top_k=3,
    )

    assert client.requested == ["diet_knowledge", "nutrition_technical"]
    assert [hit["text"] for hit in hits] == [
        "Kashmiri nutrition passage",
        "Shared passage",
        "General diet passage",
    ]
    assert len({hit["text"] for hit in hits}) == len(hits)

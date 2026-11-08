import os
from pathlib import Path
from dotenv import load_dotenv

# Resolve project root: Aabvita/
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

import chromadb
from chromadb.config import Settings
from openai import OpenAI


class FitnessCoach:
    def __init__(
        self,
        chat_model: str = "meta-llama/llama-3.3-70b-instruct",
        embed_model: str = "openai/text-embedding-3-small",
    ):
        self.chat_model = chat_model
        self.embed_model = embed_model

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set. Please add it to your root .env file.")

        # OpenRouter client
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

        self.vector_db_path = str(ROOT / "vector_db")
        self.chroma_client = chromadb.PersistentClient(
            path=self.vector_db_path,
            settings=Settings(anonymized_telemetry=False),
        )

        self.system_prompt = (
            "You are FitGenius, a warm and experienced personal fitness coach speaking directly with someone face to face.\n\n"
            "How to reply:\n"
            "- Answer the question directly in your first sentence.\n"
            "- Sound human and calm, not like a report or a manual.\n"
            "- Use plain language and explain any technical term you use.\n"
            "- Keep paragraphs short; use bullets only for steps or options.\n"
            "- Never mention sources, documents, filenames, page numbers, models, or that you looked anything up.\n"
            "- Never add a sources, references, or disclaimer section.\n"
            "- End with one practical next step or one short follow-up question when it fits.\n\n"
            "Safety rules:\n"
            "- Never diagnose medical conditions.\n"
            "- Never recommend extreme diets.\n"
            "- Never encourage exercising through pain.\n"
            "- Consider allergies and physical limitations.\n"
            "- Recommend professional medical advice when necessary as natural advice rather than a legal notice."
        )

        self.history = [{"role": "system", "content": self.system_prompt}]

    def retrieve_context(self, query: str, collection_name: str = "exercise_knowledge", n_results: int = 3) -> str:
        """Embed user query truncated to 768 dimensions and retrieve matching context."""
        try:
            collection = self.chroma_client.get_collection(collection_name)
        except Exception:
            return ""

        # Request 768 dimensions to match your existing collection
        response = self.client.embeddings.create(
            input=[query],
            model=self.embed_model,
            dimensions=768,
        )
        query_vector = response.data[0].embedding

        results = collection.query(
            query_embeddings=[query_vector],
            n_results=n_results,
        )

        docs = results.get("documents", [[]])[0]
        return "\n\n".join(docs)

    def generate_response(self, user_prompt: str, collection_name: str = "exercise_knowledge") -> str:
        """Single-turn generation with context."""
        context = self.retrieve_context(user_prompt, collection_name=collection_name)
        user_message = f"Context:\n{context}\n\nUser Question: {user_prompt}" if context else user_prompt

        response = self.client.chat.completions.create(
            model=self.chat_model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=400,
        )
        return response.choices[0].message.content

    def send_message(self, user_prompt: str, collection_name: str = "exercise_knowledge") -> str:
        """Multi-turn interactive chat loop with context."""
        context = self.retrieve_context(user_prompt, collection_name=collection_name)
        current_content = f"Context:\n{context}\n\nUser: {user_prompt}" if context else user_prompt

        self.history.append({"role": "user", "content": current_content})

        response = self.client.chat.completions.create(
            model=self.chat_model,
            messages=self.history,
            temperature=0.5,
            max_tokens=500,
        )

        reply = response.choices[0].message.content
        self.history.append({"role": "assistant", "content": reply})
        return reply


if __name__ == "__main__":
    coach = FitnessCoach()
    print("FitGenius: Hey there! I'm your fitness coach. What are we working on today? (Type 'quit' to exit)\n")

    while True:
        user_input = input("You: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("FitGenius: Take care! Keep moving and stay healthy. Goodbye!")
            break

        if not user_input.strip():
            continue

        response = coach.send_message(user_input, collection_name="exercise_knowledge")
        print(f"\nFitGenius: {response}\n")
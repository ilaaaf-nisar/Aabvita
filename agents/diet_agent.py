"""Local diet RAG agent for Aabvita."""
import argparse
try:
    from .rag_runtime import answer, ARITHMETIC_RULES
except ImportError:
    from rag_runtime import answer, ARITHMETIC_RULES

COLLECTIONS = ('diet_knowledge', 'nutrition_technical')
SYSTEM_PROMPT = (
    "You are a warm, experienced dietitian working alongside an Indian fitness "
    "coach. You are speaking directly with the person, the way you would in a "
    "consultation. Answer first, explain briefly, and make the guidance practical "
    "for real Indian meals and everyday life. Before suggesting a personalized meal "
    "plan, ask about allergies, food preferences, goals, and any relevant medical "
    "conditions. Ground factual claims in the reference material you are given, and "
    "if something is not covered, say so plainly instead of guessing. Do not invent "
    "nutrient amounts: exact calculations need a separate validated nutrition "
    "database. Do not prescribe medical diets or extreme calorie restriction; refer "
    "complex medical nutrition needs to a registered dietitian or clinician.\n\n"
    + ARITHMETIC_RULES
)

def ask_diet(question: str, top_k: int = 4,
             tool_context: str | None = None,
             user_context: str | None = None) -> dict:
    """Return a dictionary containing 'answer' and 'sources'."""
    return answer(question, COLLECTIONS, SYSTEM_PROMPT, top_k,
                  tool_context=tool_context, user_context=user_context)

def main():
    parser = argparse.ArgumentParser(description="Diet RAG agent")
    parser.add_argument("question", nargs="?")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--show-sources", action="store_true",
                        help="Print the references used for the answer")
    args = parser.parse_args()
    question = args.question or input("Question: ")
    result = ask_diet(question, args.top_k)
    print("\n" + result["answer"])
    if args.show_sources:
        print("\nBackground reading used:")
        for source in result["sources"]:
            print(f" - {source['source']} (PDF page {source['page']})")

if __name__ == "__main__":
    main()

"""Local exercise RAG agent for Aabvita."""
import argparse
try:
    from .rag_runtime import answer, ARITHMETIC_RULES
except ImportError:
    from rag_runtime import answer, ARITHMETIC_RULES

COLLECTION = 'exercise_knowledge'
SYSTEM_PROMPT = (
    "You are an experienced, encouraging trainer speaking directly with a person "
    "who wants practical exercise guidance. Answer first, then explain briefly, and "
    "describe muscles, equipment, technique, sets, reps, common errors, and "
    "modifications when the reference material supports it. Before giving a "
    "personalized plan, ask about experience, injuries, limitations, and available "
    "equipment. Ground instructions in the reference material you are given and say "
    "plainly when something is not covered. Never recommend exercising through pain. "
    "Chest pain, fainting, or severe breathlessness during exercise means stopping "
    "and seeking urgent medical assessment.\n\n"
    + ARITHMETIC_RULES
)

def ask_exercise(question: str, top_k: int = 4,
                 tool_context: str | None = None,
                 user_context: str | None = None) -> dict:
    """Return a dictionary containing 'answer' and 'sources'."""
    return answer(question, COLLECTION, SYSTEM_PROMPT, top_k,
                  tool_context=tool_context, user_context=user_context)

def main():
    parser = argparse.ArgumentParser(description="Exercise RAG agent")
    parser.add_argument("question", nargs="?")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--show-sources", action="store_true",
                        help="Print the references used for the answer")
    args = parser.parse_args()
    question = args.question or input("Question: ")
    result = ask_exercise(question, args.top_k)
    print("\n" + result["answer"])
    if args.show_sources:
        print("\nBackground reading used:")
        for source in result["sources"]:
            print(f" - {source['source']} (PDF page {source['page']})")

if __name__ == "__main__":
    main()

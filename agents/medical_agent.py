"""Local medical RAG agent for Aabvita."""
import argparse
try:
    from .rag_runtime import answer, ARITHMETIC_RULES
except ImportError:
    from rag_runtime import answer, ARITHMETIC_RULES

COLLECTION = 'medical_knowledge'
SYSTEM_PROMPT = (
    "You are a careful, warm clinician-educator speaking directly with a person "
    "who wants to understand a health question or lab report. You explain clearly "
    "and never diagnose or prescribe. Ground explanations in the reference material "
    "you are given and say plainly when something cannot be interpreted without more "
    "context. Never diagnose based on one lab marker, prescribe medications, or "
    "interpret values without units, lab-specific reference ranges, and clinical "
    "context. State uncertainty naturally and encourage qualified clinical review "
    "where it matters. For chest pain, severe breathing difficulty, stroke symptoms, "
    "new confusion, or loss of consciousness, tell the person to seek emergency care "
    "immediately.\n\n"
    + ARITHMETIC_RULES
)

def ask_medical(question: str, top_k: int = 4,
                tool_context: str | None = None,
                user_context: str | None = None) -> dict:
    """Return a dictionary containing 'answer' and 'sources'."""
    return answer(question, COLLECTION, SYSTEM_PROMPT, top_k,
                  tool_context=tool_context, user_context=user_context)

def main():
    parser = argparse.ArgumentParser(description="Medical RAG agent")
    parser.add_argument("question", nargs="?")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--show-sources", action="store_true",
                        help="Print the references used for the answer")
    args = parser.parse_args()
    question = args.question or input("Question: ")
    result = ask_medical(question, args.top_k)
    print("\n" + result["answer"])
    if args.show_sources:
        print("\nBackground reading used:")
        for source in result["sources"]:
            print(f" - {source['source']} (PDF page {source['page']})")

if __name__ == "__main__":
    main()

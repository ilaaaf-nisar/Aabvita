import json

from agents import orchestrator, rag_runtime
from agents.conversation_context import ConversationState, extract_rules


def _answer(question):
    return {
        "answer": f"A general response to: {question}",
        "sources": [],
    }


def _stub_agents(monkeypatch, calls):
    def record(agent):
        def ask(question, *, top_k=4, tool_context=None, user_context=None):
            calls[agent] = {
                "question": question,
                "top_k": top_k,
                "user_context": user_context,
                "tool_context": tool_context,
            }
            return _answer(question)
        return ask

    monkeypatch.setitem(orchestrator.AGENTS, "diet", record("diet"))
    monkeypatch.setitem(orchestrator.AGENTS, "exercise", record("exercise"))
    monkeypatch.setitem(orchestrator.AGENTS, "medical", record("medical"))
    def combine(question, results, errors, tool_context=None):
        return (
            f"{question} {len(results)} {len(errors)} "
            f"{tool_context or ''}"
        )

    monkeypatch.setattr(orchestrator, "synthesize", combine)


def test_profile_persists_and_follow_up_context_is_safe(tmp_path):
    path = tmp_path / "session.json"
    state = ConversationState(path)
    state.profile.update({
        "weight_kg": 72,
        "height_cm": 175,
        "age": 31,
        "goal": "maintain",
    })
    state.pending_food = {
        "food": "diabetes-friendly oats",
        "grams": 100,
        "candidates": [
            {"description": "Rolled oats", "fdc_id": 1},
            {"description": "Butter, salted", "ndb_no": "01001", "source": "sr28"},
        ],
    }
    state.remember_turn("How do I perform a squat?", ["exercise"])
    state.save()

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["profile"]["weight_kg"] == 72
    assert stored["last_subject"] == "squat"
    assert "food" not in stored["pending_food"]
    assert "diabetes" not in path.read_text(encoding="utf-8").lower()
    assert "How do I perform a squat?" not in path.read_text(encoding="utf-8")

    restored = ConversationState(path)
    assert restored.profile["weight_kg"] == 72
    assert restored.pending_food["candidates"][1] == {
        "description": "Butter, salted",
        "ndb_no": "01001",
        "source": "sr28",
    }
    assert restored.resolve_follow_up("Can I do it daily?").find("squat") >= 0
    assert restored.context_for_agent("exercise") is None


def test_explicit_correction_updates_persisted_profile(tmp_path, monkeypatch):
    calls = {}
    _stub_agents(monkeypatch, calls)
    path = tmp_path / "profile.json"
    state = ConversationState(path)

    orchestrator.ask_coach(
        "I weigh 82 kg.",
        state=state,
        routing="keywords",
        extraction="rules",
    )
    orchestrator.ask_coach(
        "Correction: my weight is 77 kg.",
        state=state,
        routing="keywords",
        extraction="rules",
    )

    restored = ConversationState(path)
    assert restored.profile["weight_kg"] == 77


def test_latest_explicit_correction_wins_within_one_message():
    extracted = extract_rules(
        "I weigh 82 kg, but correction: I now weigh 77 kg. "
        "I wanted to lose weight, but now I want to maintain my weight."
    )
    assert extracted["profile"]["weight_kg"] == 77
    assert extracted["profile"]["goal"] == "maintain"


def test_persisted_follow_up_reuses_safe_subject(tmp_path, monkeypatch):
    calls = {}
    _stub_agents(monkeypatch, calls)
    path = tmp_path / "follow-up.json"
    first_session = ConversationState(path)
    orchestrator.ask_coach(
        "How do I perform a squat?",
        state=first_session,
        routing="keywords",
        extraction="rules",
    )

    next_session = ConversationState(path)
    result = orchestrator.ask_coach(
        "Can I do it daily?",
        state=next_session,
        routing="keywords",
        extraction="rules",
    )

    assert result["agents_used"] == ["exercise"]
    assert "squat" in calls["exercise"]["question"].lower()


def test_profile_context_requires_consent_and_is_agent_specific(monkeypatch):
    calls = {}
    _stub_agents(monkeypatch, calls)
    state = ConversationState(share_profile_context=True)
    state.profile.update({
        "weight_kg": 72,
        "height_cm": 175,
        "age": 31,
        "sex": "female",
        "goal": "lose",
        "activity_level": "moderate",
    })

    result = orchestrator.ask_coach(
        "How do I train squats while losing weight?",
        state=state,
        routing="keywords",
        extraction="rules",
    )

    assert set(result["agents_used"]) == {"diet", "exercise"}
    diet_context = json.loads(calls["diet"]["user_context"].split("\n", 1)[1])
    exercise_context = json.loads(calls["exercise"]["user_context"].split("\n", 1)[1])
    assert set(diet_context) == {"weight_kg", "goal", "activity_level"}
    assert set(exercise_context) == {
        "age", "weight_kg", "height_cm", "activity_level", "goal",
    }
    assert "sex" not in diet_context
    assert "sex" not in exercise_context


def test_authorized_profile_context_reaches_rag_prompt(monkeypatch):
    captured = {}
    def fake_retrieve(collection, question, top_k):
        captured["retrieval"] = (collection, question, top_k)
        return [
            {"text": "Reference passage", "source": "guide.pdf", "page": 1},
        ]

    def fake_chat(messages, *, temperature):
        captured["prompt"] = messages[-1]["content"]
        captured["temperature"] = temperature
        return "Response"

    monkeypatch.setattr(rag_runtime, "retrieve", fake_retrieve)
    monkeypatch.setattr(rag_runtime, "chat", fake_chat)
    result = rag_runtime.answer(
        "Suggest a workout",
        "exercise_knowledge",
        "system prompt",
        user_context='{"activity_level": "moderate"}',
    )

    assert result["answer"] == "Response"
    assert captured["retrieval"] == ("exercise_knowledge", "Suggest a workout", 4)
    assert captured["temperature"] == 0.2
    assert "activity_level" in captured["prompt"]
    assert "do not ask the user to repeat them" in captured["prompt"]


def test_medical_details_stay_with_medical_agent_without_consent(
    tmp_path, monkeypatch
):
    calls = {}
    _stub_agents(monkeypatch, calls)
    path = tmp_path / "private-session.json"
    state = ConversationState(path)

    result = orchestrator.ask_coach(
        "How can I exercise safely with diabetes?",
        state=state,
        routing="keywords",
        extraction="rules",
    )

    assert result["agents_used"] == ["medical"]
    assert "diabetes" in calls["medical"]["question"].lower()
    assert "exercise" not in calls
    stored = path.read_text(encoding="utf-8").lower()
    assert "diabetes" not in stored


def test_medical_sharing_requires_separate_consent(monkeypatch):
    calls = {}
    _stub_agents(monkeypatch, calls)
    state = ConversationState(share_medical_context=True)

    result = orchestrator.ask_coach(
        "How can I exercise safely with diabetes?",
        state=state,
        routing="keywords",
        extraction="rules",
    )

    assert {"medical", "exercise"} <= set(result["agents_used"])
    assert "diabetes" in calls["exercise"]["question"].lower()


def test_calculators_use_remembered_profile(monkeypatch):
    calls = {}
    _stub_agents(monkeypatch, calls)
    state = ConversationState()
    state.profile.update({
        "weight_kg": 72,
        "height_cm": 175,
        "age": 31,
        "sex": "female",
        "activity_level": "moderate",
        "goal": "lose",
    })

    result = orchestrator.ask_coach(
        "What is my BMI and daily calorie needs?",
        state=state,
        routing="keywords",
        extraction="rules",
    )

    assert result["tool_results"]["bmi"]["bmi"] > 0
    assert result["tool_results"]["calories"]["tdee_kcal_per_day"] > 0


def test_rules_keep_only_explicit_profile_fields():
    extracted = extract_rules("I weigh 70 kg, but suppose I were 90 kg.")
    assert extracted["profile"]["weight_kg"] == 70

---
title: Aabvita
emoji: 🧠
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
license: mit
---


# Aabvita

**Your Health. Intelligently Guided.**

Aabvita is a local web app for health, nutrition, and exercise questions. A
FastAPI server connects the browser UI to a multi-agent orchestrator. The
orchestrator routes questions to diet, medical, and exercise agents, which use
local ChromaDB knowledge collections and OpenRouter language models. Explicit
nutrition and body-metric calculations are handled by deterministic Python
tools rather than model-generated arithmetic.

## Contents

- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Run the web app](#run-the-web-app)
- [Configuration](#configuration)
- [Knowledge-base indexing](#knowledge-base-indexing)
- [Nutrition databases](#nutrition-databases)
- [Tests](#tests)
- [Privacy and local data](#privacy-and-local-data)

## Architecture

```text
Browser (web/index.html, app.js, styles.css)
       |
       | GET /, GET /static/*, POST /api/chat, POST /api/privacy, POST /api/reset
       v
FastAPI (web_app.py)
       |
       +--> Session and consent state (agents/conversation_context.py)
       |
       v
Orchestrator (agents/orchestrator.py)
       |
       +--> Emergency-language check
       +--> Rule-based extraction and optional LLM extraction
       +--> Hybrid keyword/LLM routing
       +--> Deterministic calculations and food lookup (agents/tool_runtime.py)
       |       +--> BMI, calorie, and protein calculators (tools/)
       |       +--> FoodData Central SQLite database
       |       +--> SR28 SQLite fallback when FDC search has no matches
       |
       +--> Diet agent ------> diet_knowledge + nutrition_technical
       +--> Exercise agent --> exercise_knowledge
       +--> Medical agent ---> medical_knowledge
                              (agents/*_agent.py, agents/rag_runtime.py)
                                      |
                                      +--> ChromaDB (vector_db/)
                                      +--> OpenRouter chat and embeddings
       |
       v
Plain-language response to the browser
```

### Request and answer flow

1. The browser sends the user’s message and privacy settings to `/api/chat`.
2. FastAPI validates the request and gets the conversation state for that
   browser session.
3. The orchestrator first checks for emergency language, then extracts only
   supported structured values and determines which specialist agents are
   relevant.
4. Deterministic tools handle requested calculations and food lookups. Food
   lookup prefers FoodData Central; if it has no matches, SR28 is searched as
   a fallback. FDC IDs and SR28 NDB numbers remain separate.
5. Specialist agents retrieve relevant passages from their ChromaDB
   collections and use the configured OpenRouter model to draft answers.
6. The orchestrator combines specialist answers and authoritative tool
   results. The web API returns the answer without exposing internal agent
   names or source-file metadata.

The diet, exercise, and medical agents share retrieval and model-call
infrastructure, but have separate instructions and knowledge collections.
Nutrition values, BMI, calorie estimates, and protein targets are calculated
by Python code; the language model is instructed not to perform arithmetic.

### Main API routes

| Route | Purpose |
|---|---|
| `GET /` | Serve the web interface |
| `GET /health` | Health check; returns `{"status":"ok"}` |
| `GET /api/health` | Backward-compatible health-check route |
| `POST /api/chat` | Process a chat message |
| `POST /api/privacy` | Update profile persistence and context-sharing choices |
| `POST /api/reset` | Clear the session state |

Interactive API documentation is disabled in the FastAPI configuration.

## Project structure

```text
Aabvita/
|-- agents/                   # Routing, session context, specialist agents, RAG and tool bridges
|   |-- conversation_context.py
|   |-- diet_agent.py
|   |-- exercise_agent.py
|   |-- medical_agent.py
|   |-- orchestrator.py
|   |-- rag_runtime.py
|   `-- tool_runtime.py
|-- chatbot/
|   `-- llm.py                 # Standalone FitnessCoach client; not the web app entry point
|-- data/
|   |-- Food_Data/             # FoodData Central CSV source tables
|   |   |-- branded_food.csv
|   |   |-- food.csv
|   |   |-- food_category.csv
|   |   |-- food_nutrient.csv
|   |   |-- food_portion.csv
|   |   |-- measure_unit.csv
|   |   `-- nutrient.csv
|   |-- sr28/                  # USDA Standard Reference 28 source tables
|   |   |-- DATA_SRC.txt
|   |   |-- DATSRCLN.txt
|   |   |-- DERIV_CD.txt
|   |   |-- FD_GROUP.txt
|   |   |-- FOOD_DES.txt
|   |   |-- FOOTNOTE.txt
|   |   |-- LANGDESC.txt
|   |   |-- LANGUAL.txt
|   |   |-- NUT_DATA.txt
|   |   |-- NUTR_DEF.txt
|   |   |-- SRC_CD.txt
|   |   `-- WEIGHT.txt
|   `-- user_sessions/         # Optional local profile/session state; created when enabled
|-- databases/                 # Generated SQLite nutrition databases
|   |-- usda_nutrition.db
|   `-- usda_sr28.db
|-- debug/                     # Manual database inspection and diagnostic scripts
|   |-- debug_nutrients.py
|   |-- inspect_usda.py
|   |-- test_sr28_db.py
|   `-- test_usda_db.py
|-- ingestion/
|   |-- ingest_documents.py    # Build/update ChromaDB knowledge collections
|   `-- validate_retrieval.py  # Manually inspect retrieval quality
|-- knowledge_base/
|   |-- diet/                  # Diet guidance, labels, food data, and dietary references
|   |-- exercise/              # Exercise coaching and activity guidelines
|   |-- medical/               # Clinical and condition reference material
|   `-- nutrition_technical/   # Detailed nutrition and Kashmiri recipe references
|-- tests/                     # Automated pytest coverage
|   |-- test_conversation_memory.py
|   |-- test_diet_retrieval.py
|   |-- test_nutrition_features.py
|   `-- test_web_app.py
|-- tools/                     # Deterministic calculations and food-database lookups
|   |-- bmi_calculator.py
|   |-- calorie_calculator.py
|   |-- nutrition_tool.py
|   `-- protein_calculator.py
|-- vector_db/                 # Generated persistent ChromaDB files; do not edit manually
|-- web/
|   |-- app.js                 # Browser interaction, chat, and privacy settings
|   |-- index.html             # Page structure and content
|   |-- styles.css             # Visual styling and responsive layout
|   `-- README.md              # Web-interface quick-start notes
|-- build_sr28_db.py           # Import SR28 text files into databases/usda_sr28.db
|-- build_usda_db.py           # Import FoodData Central CSV files into SQLite
|-- .gitignore                 # Excludes local secrets, environments, caches, and sessions
|-- requirements-deploy.txt    # Lean web-runtime dependencies
|-- requirements.txt           # Full development, ingestion, and runtime dependencies
|-- web_app.py                 # FastAPI app and HTTP endpoints
`-- .env                       # Local configuration and API key; never commit
```

The reference library currently contains:

- `knowledge_base/diet/`: `Composition of diet.pdf`,
  `DGI_Booklet_English_CMYK.pdf`, `dietry guidelines for indians.pdf`,
  `Field_Descriptions_Oct2020.pdf`, `Food_Label_Booklet.pdf`,
  `Foundation_Foods_Documentation_Apr2024.pdf`, and
  `My_Plate_for_the_day_J24.pdf`.
- `knowledge_base/exercise/`: `Complete_Exercise_Coaching_Manual.pdf` and
  `physical activity guidelines.pdf`.
- `knowledge_base/medical/`: `Chronic Kidney Disease.pdf`,
  `Clinical_Diagnostic_Handbook.pdf`, `Diseases.pdf`, and
  `Weight_Management_and_Metabolic_Health_Clinical_Handbook.pdf`.
- `knowledge_base/nutrition_technical/`: `detailed_kashmiri_recipes.pdf`,
  `Kashmiri_dishes.pdf`, and `nutrition.pdf`.

The contents of `vector_db/` and `databases/` are generated data, not source
code. `.venv/`, `.venv311/`, `__pycache__/`, and `.pytest_cache/` are also
local/generated directories and are excluded from source control.

### Important source files

- `agents/orchestrator.py` — emergency checks, extraction, routing, tool
  execution, response synthesis, and CLI entry point.
- `agents/conversation_context.py` — validates user-provided profile data,
  extracts supported request details, resolves follow-ups, and manages
  opt-in local state.
- `agents/rag_runtime.py` — shared OpenRouter client, ChromaDB retrieval, and
  model-based answer generation.
- `agents/diet_agent.py`, `agents/exercise_agent.py`, and
  `agents/medical_agent.py` — specialist prompts and knowledge-collection
  assignments.
- `agents/tool_runtime.py` — invokes explicit deterministic tools and packages
  their results for the orchestrator.
- `tools/nutrition_tool.py` — FoodData Central food search, SR28 fallback,
  nutrient lookup, and serving-size conversion.
- `tools/bmi_calculator.py`, `tools/calorie_calculator.py`, and
  `tools/protein_calculator.py` — deterministic calculators.
- `web_app.py` — FastAPI routes, session management, and UI/static-file serving.

`chatbot/llm.py` provides an additional standalone chat client. The web app
starts from `web_app.py` and uses `agents/orchestrator.py`.

## Run the web app

Run these commands from the project root in PowerShell:

```powershell
py -3.11 -m venv .venv311
.\.venv311\Scripts\Activate.ps1
python -m pip install -r requirements-deploy.txt
python -m pip install pytest pypdf
python -m uvicorn web_app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Binding to `127.0.0.1` keeps the server
accessible only from the local computer. Stop it with **Ctrl+C**.

`requirements-deploy.txt` contains the dependencies needed to run the web
runtime. `pytest` enables the test suite, and `pypdf` is needed for document
ingestion. The full `requirements.txt` currently pins `networkx==3.7`, which
requires Python 3.12 or newer; use Python 3.12+ for that full dependency set
unless its incompatible pins are updated.

## Configuration

Create a root `.env` file and set:

```text
OPENROUTER_API_KEY=your-key
```

The key is used for language-model calls and embeddings. Never add a real key
to source control. The shared RAG runtime also accepts these optional
environment settings:

- `MY_COACH_VECTOR_DB` — ChromaDB directory; defaults to `vector_db/`.
- `MY_COACH_CHAT_MODEL` — chat model; defaults to
  `meta-llama/llama-3.3-70b-instruct`.
- `MY_COACH_EMBED_MODEL` — embedding model; defaults to
  `openai/text-embedding-3-small`.

The embedding model and vector dimensions must be compatible with the
embeddings already stored in the ChromaDB collections.

## Knowledge-base indexing

Source reference documents belong in `knowledge_base/` under one of the
category directories: `diet/`, `exercise/`, `medical/`, or
`nutrition_technical/`. PDF, TXT, and Markdown files are supported.

From the project root, index all categories:

```powershell
python ingestion\ingest_documents.py
```

Index one category or rebuild selected collections:

```powershell
python ingestion\ingest_documents.py --agent diet
python ingestion\ingest_documents.py --agent exercise --reset
python ingestion\ingest_documents.py --agent medical --reset
python ingestion\ingest_documents.py --agent nutrition_technical --reset
```

`--reset` deletes and rebuilds the selected ChromaDB collection. Ingestion
extracts and chunks documents, requests embeddings from OpenRouter, and stores
the results in `vector_db/`. This requires network access and a valid API key.
`ingestion/validate_retrieval.py` can be used to manually check retrieval.

The current persistent ChromaDB contains these collections:

| Collection | Used by |
|---|---|
| `diet_knowledge` | Diet agent |
| `nutrition_technical` | Diet agent |
| `exercise_knowledge` | Exercise agent |
| `medical_knowledge` | Medical agent |

## Nutrition databases

The nutrition SQLite databases are separate from the ChromaDB knowledge
collections:

- `databases/usda_nutrition.db` — current FoodData Central data used first for
  food search, nutrients, and portions.
- `databases/usda_sr28.db` — legacy Standard Reference 28 data used only when
  FoodData Central search has no matches.

The FoodData Central importer expects `food.csv`, `food_nutrient.csv`,
`nutrient.csv`, `food_category.csv`, `food_portion.csv`, `measure_unit.csv`,
and `branded_food.csv` in `data/Food_Data/`. Rebuild the database from the
project root with:

```powershell
python build_usda_db.py
```

`--branded-only` imports just the branded-food table without rebuilding the
other tables:

```powershell
python build_usda_db.py --branded-only
```

The SR28 importer expects the USDA SR28 text tables in `data/sr28/`. Build or
rebuild that database with:

```powershell
python build_sr28_db.py
```

SR28 uses NDB numbers, not FoodData Central IDs. The application preserves
that distinction when presenting and calculating fallback results.

Database rebuilds replace imported tables. Keep the source files and back up
any database that must be preserved before rebuilding.

## Tests

Run the complete test suite from the project root:

```powershell
python -m pytest -q
```

Tests cover conversation memory and privacy, retrieval behavior, nutrition
imports and calculations, and the web API.

## Privacy and local data

- Profile persistence is off by default. When enabled, only validated,
  allow-listed profile fields and safe topic labels are stored under
  `data/user_sessions/`.
- Raw chat text, assistant responses, and medical details are not written to
  those profile files.
- The browser's profile/context-sharing controls are passed to the server for
  each request.
- `.env`, virtual environments, caches, Python bytecode, and
  `data/user_sessions/` are excluded by `.gitignore`. Keep credentials and
  private session data out of source control.

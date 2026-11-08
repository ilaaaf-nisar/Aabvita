# Aabvita web interface

From the project root, start the local web app:

```powershell
python -m uvicorn web_app:app --host 127.0.0.1 --port 8000
```

Then open `http://127.0.0.1:8000` in a browser. Keep the host on `127.0.0.1`
to make the interface available only on this computer.

The app uses the existing orchestrator, agents, nutrition database, and vector
database. OpenRouter credentials must be configured in the project `.env`.
Profile persistence is off by default. When enabled, only the existing
allow-listed profile fields and safe topic labels are stored under
`data/user_sessions/`; chat text and medical details are not written there.
Turning persistence off or selecting **New chat** removes the saved profile for
that browser session.

Food lookups use FoodData Central first and search the USDA Standard Reference
28 database only when no FoodData Central match is found. The SR28 fallback is
available when `databases/usda_sr28.db` has been built from `data/sr28` by
running `python build_sr28_db.py` from the project root. SR28 NDB numbers are
kept separate from FoodData Central IDs.

# GitQuest / BUG//DUNGEON

GitQuest is a gamified developer-learning platform that turns real GitHub issues into approachable quests. The experience presents bugs and feature requests as dungeon challenges so beginners can practice repository exploration, debugging, implementation, and verification without being handed a complete solution.

## What is included

The current repository contains a Flask backend, a browser-based BUG//DUNGEON interface, and a Google GenAI service.

- Select a public GitHub repository by URL.
- Retrieve open issues while filtering out pull requests.
- Generate structured quests from issue data with Gemma/Gemini models.
- Show beginner-friendly briefings, objectives, progressive hints, and verification checklists.
- Track prototype player XP, cleared quests, badges, class selection, and sound preferences in browser `localStorage`.
- Handle GitHub errors, rate limits, missing AI keys, malformed model output, and validation failures.

The current prototype does **not** yet provide server-side accounts, a database, closed-issue training, persistent cross-device progression, or consistency scoring.

## Architecture

```text
Browser UI (templates/index.html + static/)
              |
              v
        Flask application
          /api/issues
          /api/quest
              |
       +------+------+
       |             |
 GitHub REST API  Google GenAI
                  Gemma/Gemini
```

## Repository structure

| Path | Purpose |
| --- | --- |
| `app.py` | Flask app, API routes, validation, CORS, and error handling. |
| `github_service.py` | GitHub URL parsing, issue retrieval, normalization, and rate-limit handling. |
| `ai_service.py` | GenAI client, quest schemas, prompts, JSON validation, hints, and evaluation helpers. |
| `templates/index.html` | BUG//DUNGEON browser interface. |
| `static/app.js` | Frontend state, repository scanning, quest interaction, XP, badges, and audio controls. |
| `static/style.css` | Dungeon-themed UI styling and responsive layout. |
| `static/world_map.png` / `static/world_map.mp4` | Visual assets used by the interface. |
| `test_app.py` | Flask endpoint tests. |
| `test_github.py` | Offline GitHub service tests and optional live smoke test. |
| `test_ai_service.py` | Mocked AI integration and schema tests. |
| `.env.example` | Environment variable template. |
| `requirements.txt` | Python dependencies. |

## Requirements

- Python 3.10 or newer
- A Google GenAI API key for live quest generation
- Optional GitHub personal access token for a higher GitHub API rate limit

## Setup

From the repository directory:

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add your values:

```dotenv
GITHUB_TOKEN=your_github_token_here
GEMINI_API_KEY=your_gemini_api_key_here
GEMMA_MODEL=gemma-4-26b-a4b-it
PORT=5000
```

`GITHUB_TOKEN` is optional. The AI service accepts `GEMINI_API_KEY` or `GOOGLE_API_KEY`. Model selection supports `GEMMA_MODEL`, `GEMINI_MODEL`, or `MODEL_NAME`, with the first configured value taking precedence.

Never commit `.env` or API keys.

## Run the application

```bash
python app.py
```

The Flask server listens on:

```text
http://127.0.0.1:5000
```

The API currently exposes a JSON response at `/`. The `templates/index.html` and `static/` UI assets are included for the BUG//DUNGEON frontend experience; frontend/API wiring can be extended as the product evolves.

Health check:

```bash
curl http://127.0.0.1:5000/health
```

Expected response:

```json
{"status": "ok"}
```

## API usage

### Retrieve repository issues

`POST /api/issues`

Request:

```json
{
  "repo_url": "https://github.com/pallets/flask",
  "limit": 5
}
```

Response:

```json
{
  "issues": [
    {
      "number": 123,
      "title": "Example issue",
      "body": "Issue description",
      "labels": ["bug"],
      "html_url": "https://github.com/pallets/flask/issues/123",
      "repo": "pallets/flask"
    }
  ],
  "count": 1
}
```

Results are capped at 10 in the prototype, and GitHub pull requests are excluded from the returned issue list.

### Generate a quest

`POST /api/quest`

Request:

```json
{
  "issue": {
    "number": 123,
    "title": "Fix an example bug",
    "body": "Describe the problem here.",
    "labels": ["bug", "good first issue"],
    "repo": "owner/repository",
    "html_url": "https://github.com/owner/repository/issues/123"
  }
}
```

The service returns a validated quest containing a title, tagline, difficulty, category, XP reward, estimated time, briefing, objectives, progressive hints, verification checklist, and source issue reference.

## AI service helpers

The Python service can also be used directly:

```python
from ai_service import evaluate_submission, generate_hint, generate_quest

quest = generate_quest(issue)
hint = generate_hint(issue, level=1)
evaluation = evaluate_submission(issue, submission="My proposed fix...")
```

AI output is validated with Pydantic. AI-generated XP and evaluation results are not a durable authority for player progression; a future persistence layer should own rewards, hint purchases, and completion rules.

## Testing

Run all offline tests:

```bash
python -m unittest -v
```

The tests mock GitHub and Google GenAI requests, so API keys are not needed for the normal test suite. To run the optional live GitHub smoke test:

```bash
python test_github.py --live
```

## Roadmap

The next product expansion is planned around:

1. Closed-issue training quests with confirmed resolution evidence.
2. Open-issue challenges unlocked by configurable progression rules.
3. Server-side user progress, XP, and hint purchases.
4. Consistency scoring with a configurable grace period and decay.
5. Better frontend/API wiring for interactive quest completion.

Personalized repository recommendations and independent issue discovery are outside the current implementation scope.

## Security

- Keep API keys in `.env` or deployment secrets.
- Do not put credentials in prompts, fixtures, logs, or commits.
- Treat AI suggestions for unresolved issues as unverified.
- The backend returns safe error messages instead of internal stack traces.

## License

This project is available under the MIT License. See `LICENSE`.

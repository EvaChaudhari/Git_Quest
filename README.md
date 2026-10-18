# GitQuest 🎮⚔️

**AI-Powered GitHub Repository Analysis & Gamified Quest Engine**

GitQuest is a developer engagement platform that transforms real open-source GitHub issues into structured, gamified engineering quests. By combining the official GitHub REST API with Google Gemma and Gemini AI models, GitQuest generates immersive RPG-style story briefings, clear technical summaries, actionable multi-step objectives, progressive hint tiers (with XP penalties), and verification checklists.

---

## 1. Features

- **GitHub Repository Analysis**: Validates and parses public GitHub URLs, retrieves open issues, filters out pull requests, and standardizes issue data into a clean, normalized schema.
- **AI Quest Generation**: Uses Google Gemma (`gemma-4-26b-a4b-it`) via the `google-genai` SDK to convert issue descriptions into game-like developer missions.
- **Dual Briefings**: Each quest provides both an immersive narrative lore hook and an accurate technical explanation of the underlying problem.
- **Progressive Hint System**: 3 tiers of hints (*Gentle Nudge*, *Investigation Lead*, *Tactical Blueprint*) with scaling XP costs to guide players without spoiling solutions.
- **Clean RESTful API**: Built with Flask, featuring structured JSON error responses, standard HTTP status codes, and input validation.
- **Frontend-Ready CORS**: Configured to safely permit cross-origin requests from frontend development origins (`http://localhost:3000` and `http://localhost:5173`) on `/api/*` routes.
- **Zero-Secret Exposure**: Sensitive credentials (`GEMINI_API_KEY`, `GITHUB_TOKEN`) are handled strictly server-side and never logged or leaked to clients.
- **100% Offline Testable**: Comprehensive test suite covering all services, models, and API endpoints using mocks with zero external network or credential requirements.

---

## 2. Technology Stack

- **Language**: Python 3.10+ (tested on Python 3.15)
- **Web Framework**: Flask 3.1.3
- **Cross-Origin Resource Sharing**: Flask-CORS 6.0.5
- **HTTP Client**: Requests 2.34.2
- **AI Provider**: Google GenAI SDK (`google-genai` 2.31.0)
- **Data Validation & Schemas**: Pydantic 2.14.1
- **Environment Configuration**: python-dotenv 1.2.4
- **Testing Framework**: Python Standard Library `unittest` with `unittest.mock`

---

## 3. Repository Structure

```text
gitquest/
├── app.py               # Flask application: routes, input validation, error handlers, CORS
├── github_service.py    # GitHub API integration: URL parsing, open/closed issues, resolution evidence
├── ai_service.py        # AI quest engine: prompt construction, Gemma client, Stage A/B schemas
├── database.py          # Persistence layer: SQLite schema, transactions, demo user setup
├── gamification.py      # Gamification rules: XP ledger, hint unlocks, consistency scoring
├── test_app.py          # Flask backend test suite: route tests, validation, error scenarios
├── test_github.py       # GitHub service test suite: URL parsing, HTTP mocking, resolution evidence
├── test_ai_service.py   # AI service test suite: prompt verification, Stage A/B schemas, sanitization
├── test_gamification.py # Gamification unit tests: XP ledger, decay, Stage B unlock thresholds
├── requirements.txt     # Python project dependencies
├── .env.example         # Example configuration file with placeholders
├── .gitignore           # Git ignore rules for virtual environments, caches, and secrets
├── LICENSE              # Project license
└── README.md            # Comprehensive project documentation
```

---

## 4. Prerequisites

- Python 3.10 or higher installed on your system.
- Git.
- *(Optional but recommended)* A Google Gemini API Key from [Google AI Studio](https://aistudio.google.com/app/apikey) for live quest generation.
- *(Optional)* A GitHub Personal Access Token to raise GitHub API rate limits from 60 to 5,000 requests per hour.

---

## 5. Getting Started

### Step 1: Clone the Repository
```bash
git clone https://github.com/EvaChaudhari/gitquest.git
cd gitquest
```

### Step 2: Set Up Virtual Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy the example environment configuration:
```bash
cp .env.example .env
chmod 600 .env
```

Open `.env` in your text editor and configure your variables:
```env
# Google GenAI / Gemini API Key (Required for live quest generation)
GEMINI_API_KEY=your_gemini_api_key_here

# Gemma / Gemini model identifier (Defaults to gemma-4-26b-a4b-it)
GEMMA_MODEL=gemma-4-26b-a4b-it

# GitHub Personal Access Token (Optional, raises rate limit)
GITHUB_TOKEN=your_github_token_here

# Server Port (Defaults to 5000)
PORT=5000
```

---

## 6. Running the Application

### Start the Flask Server
```bash
python app.py
```
The server will start listening at: `http://127.0.0.1:5000`.

---

## 7. API Reference

### A. Root Status
- **Method**: `GET`
- **Path**: `/`
- **Description**: Returns API status and endpoint directory.
- **Example Response (200 OK)**:
  ```json
  {
    "message": "GitQuest Backend API is running.",
    "endpoints": {
      "health": "/health",
      "issues": "/api/issues (POST)",
      "quest": "/api/quest (POST)"
    }
  }
  ```

---

### B. Health Check
- **Method**: `GET`
- **Path**: `/health`
- **Description**: Lightweight health-check endpoint for monitoring uptime.
- **Example Response (200 OK)**:
  ```json
  {
    "status": "ok"
  }
  ```

---

### C. Retrieve Issues
- **Method**: `POST`
- **Path**: `/api/issues`
- **Headers**: `Content-Type: application/json`
- **Body**:
  ```json
  {
    "repo_url": "https://github.com/pallets/flask",
    "limit": 5
  }
  ```
- **Example Response (200 OK)**:
  ```json
  {
    "count": 1,
    "issues": [
      {
        "number": 6146,
        "title": "Add Cloudflare to Flask Hosting Platforms docs",
        "body": "Cloudflare workers supports deploying Flask applications...",
        "labels": ["documentation", "good first issue"],
        "html_url": "https://github.com/pallets/flask/issues/6146",
        "repo": "pallets/flask"
      }
    ]
  }
  ```
- **Error Codes**:
  - `400 Bad Request`: Missing or invalid `repo_url`, non-GitHub domain, or malformed URL.
  - `404 Not Found`: Repository does not exist or is private without token.
  - `429 Too Many Requests`: GitHub API rate limit exceeded.
  - `502 Bad Gateway`: GitHub API network timeout or upstream connectivity failure.

---

### D. Generate Open Challenge (Stage B)
- **Method**: `POST`
- **Path**: `/api/quest`
- **Headers**: `Content-Type: application/json`
- **Description**: Generates an open-issue challenge quest. Protects locked hints by masking unpurchased tiers with `[LOCKED]` so answers cannot be leaked to the browser.
- **Body**:
  ```json
  {
    "issue": {
      "number": 6146,
      "title": "Add Cloudflare to Flask Hosting Platforms docs",
      "body": "Cloudflare workers supports deploying Flask applications...",
      "labels": ["documentation", "good first issue"],
      "html_url": "https://github.com/pallets/flask/issues/6146",
      "repo": "pallets/flask"
    }
  }
  ```
- **Example Response (200 OK)**:
  ```json
  {
    "quest": {
      "quest_id": "quest_pallets_flask_6146",
      "stage": "B",
      "title": "The Cloudflare Beacon",
      "difficulty": "Novice",
      "xp": 100,
      "hints": [
        {
          "level": 1,
          "tier": "Gentle Nudge",
          "hint": "[LOCKED - Unlock this tier using XP to reveal]",
          "xp_cost": 10,
          "locked": true
        }
      ]
    }
  }
  ```

---

### E. Retrieve Closed Issues with Resolution Evidence (Stage A)
- **Method**: `POST`
- **Path**: `/api/training/issues`
- **Headers**: `Content-Type: application/json`
- **Body**:
  ```json
  {
    "repo_url": "https://github.com/pallets/flask",
    "limit": 5
  }
  ```
- **Example Response (200 OK)**:
  ```json
  {
    "count": 1,
    "issues": [
      {
        "number": 5012,
        "title": "Fix context teardown callback ordering",
        "repo": "pallets/flask",
        "resolution_evidence": {
          "status": "verified",
          "evidence_summary": "Issue resolved by merged Pull Request #5015.",
          "linked_prs": ["https://github.com/pallets/flask/pull/5015"],
          "merged_prs": ["https://github.com/pallets/flask/pull/5015"]
        }
      }
    ]
  }
  ```

---

### F. Generate Stage A Training Quest
- **Method**: `POST`
- **Path**: `/api/training/quest`
- **Headers**: `Content-Type: application/json`
- **Description**: Generates a beginner-friendly training quest from a closed issue. Authoritatively retrieves GitHub timeline evidence on the server. If evidence is `verified`, explains the actual merged patch without claiming AI generated it. If evidence is `unavailable` or `partial`, states that clearly without fabricating a solution.
- **Body**:
  ```json
  {
    "issue": {
      "number": 5012,
      "title": "Fix context teardown callback ordering",
      "repo": "pallets/flask"
    }
  }
  ```
- **Example Response (200 OK)**:
  ```json
  {
    "quest": {
      "quest_id": "quest_pallets_flask_5012_training",
      "stage": "A",
      "title": "The Order of Teardown",
      "resolution_status": "verified",
      "resolution_explanation": "Reordered callbacks in AppContext.teardown() to run in registration sequence.",
      "xp": 50
    }
  }
  ```

---

### G. Unlock Progressive Hint
- **Method**: `POST`
- **Path**: `/api/quest/hint/unlock`
- **Headers**: `Content-Type: application/json`
- **Description**: Deducts configured XP (Tier 1: 10 XP, Tier 2: 25 XP, Tier 3: 50 XP) atomically from the user's balance and unlocks the requested hint. Re-accessing an already purchased hint is free and idempotent.
- **Body**:
  ```json
  {
    "quest_id": "quest_pallets_flask_6146",
    "hint_tier": 1
  }
  ```
- **Example Response (200 OK)**:
  ```json
  {
    "success": true,
    "quest_id": "quest_pallets_flask_6146",
    "hint_tier": 1,
    "tier_name": "Gentle Nudge",
    "xp_deducted": 10,
    "balance": 40,
    "already_purchased": false,
    "hint": "Check the docs/deploying directory structure.",
    "unlocked_hint": {
      "level": 1,
      "tier": "Gentle Nudge",
      "hint": "Check the docs/deploying directory structure.",
      "locked": false
    }
  }
  ```

---

### H. Complete Quest
- **Method**: `POST`
- **Path**: `/api/quest/complete`
- **Headers**: `Content-Type: application/json`
- **Description**: Records completion of a quest in the database, awards server-configured XP (Stage A: 50 XP, Stage B: 100 XP), and refreshes the consistency score grace period timer. Prevents duplicate completion awards.
- **Body**:
  ```json
  {
    "quest_id": "quest_pallets_flask_5012_training",
    "stage": "A"
  }
  ```
- **Example Response (200 OK)**:
  ```json
  {
    "success": true,
    "quest_id": "quest_pallets_flask_5012_training",
    "stage": "A",
    "awarded_xp": 50,
    "balance": 50,
    "consistency_score": 100.0,
    "stage_b_unlocked": false,
    "already_completed": false,
    "message": "Quest 'quest_pallets_flask_5012_training' completed successfully."
  }
  ```

---

### I. User Profile & Progression Stats
- **Method**: `GET`
- **Path**: `/api/user/profile`
- **Description**: Returns demo user XP balance, habit consistency score, completed quests breakdown, and server-evaluated Stage B unlock status.
- **Example Response (200 OK)**:
  ```json
  {
    "profile": {
      "user_id": "demo_user",
      "username": "Demo Developer",
      "earned_xp": 250,
      "consistency_score": 100.0,
      "stage_b_unlocked": true,
      "stage_a_completed_count": 4,
      "total_completed_count": 4,
      "stage_b_thresholds": {
        "required_xp": 200,
        "current_xp": 250,
        "required_stage_a_quests": 3,
        "current_stage_a_quests": 4
      }
    }
  }
  ```

---

## 8. Running Automated Tests

All automated unit tests run completely offline and use unittest mocks. No active internet connection or API keys are required.

### Run All 74 Test Cases
```bash
python -m unittest discover
```

### Run Specific Test Modules
```bash
# Flask API route tests (34 tests)
python -m unittest test_app.py

# GitHub service tests (19 tests)
python -m unittest test_github.py

# AI service tests (10 tests)
python -m unittest test_ai_service.py

# Gamification and persistence tests (11 tests)
python -m unittest test_gamification.py
```

---

## 9. Prototype Authentication Limitation Notice

The current prototype uses a stable server-side demo profile (`demo_user`) to store persistent XP balances, transactions, and habit consistency scores. This allows testing all gamification features without forcing beginners through an OAuth sign-in flow on first launch.

**Production launch requirement**: Replace demo profile resolution with real session tokens or OAuth authentication (e.g. GitHub OAuth) and user isolation prior to multi-tenant deployment.

| Error Message | Cause | Resolution |
| :--- | :--- | :--- |
| `Field 'repo_url' is required` (400) | Empty or missing `repo_url` in `/api/issues`. | Supply a valid GitHub repository URL in the request payload. |
| `Non-GitHub host '...'` (400) | URL points to a non-GitHub domain (e.g. GitLab, Bitbucket). | GitQuest currently supports public repositories hosted on `github.com`. |
| `Repository '...' not found on GitHub` (404) | Typo in repository name or repository is private without access token. | Verify owner and repo spelling, or provide a `GITHUB_TOKEN` in `.env`. |
| `GitHub API rate limit exceeded` (429) | Exceeded 60 unauthenticated requests/hour limit. | Add a personal access token (`GITHUB_TOKEN`) to `.env` to raise limit to 5,000 req/hr. |
| `AI service is not configured (missing API key)` (503) | `GEMINI_API_KEY` is not present in environment or `.env`. | Obtain a free Gemini API key from Google AI Studio and configure `.env`. |
| `API key not valid. Please pass a valid API key` (502) | Placeholder value `your_gemini_api_key_here` used in `.env`. | Replace placeholder with your real API key string. |

---

## 10. Current Limitations & Roadmap

- **Issue Fetch Limit**: The prototype retrieves a maximum of 10 open issues per repository to ensure fast response times and conserve GitHub API quota.
- **Pull Requests Excluded**: Pull requests are automatically filtered out to focus quest creation on open issues.
- **Single-Turn Quest Generation**: Quests are generated in a single model turn; quest completion verification against real git commits will be added in future iterations.

---

## 11. Production & Deployment Considerations

1. **WSGI Server**: Do not run `python app.py` with Flask's built-in development server in production. Use a production WSGI HTTP server such as Gunicorn:
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```
2. **CORS Origins**: In production, update the `CORS` configuration in `app.py` to match your production frontend domain rather than `localhost`.
3. **Secret Storage**: Use platform secret managers (e.g. AWS Secrets Manager, GCP Secret Manager, or platform environment variables) instead of `.env` files.
4. **Rate Limiting**: Protect backend endpoints with reverse proxy rate limiters (e.g. Nginx or Cloudflare) to prevent API abuse.

---

## 12. License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
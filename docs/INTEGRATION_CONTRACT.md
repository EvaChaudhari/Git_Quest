# GitQuest — Full-Stack Integration Contract
**Version:** 1.0.0  
**Author:** Integration Engineering Team  
**Scope:** Person 1 (Flask Backend + GitHub Integration), Person 2 (Gemma AI Service), and Person 3 (Frontend Web Application)

---

## 1. Executive Summary & Repository Status

GitQuest is a gamified open-source learning platform. It guides developers through real open-source software problems via two distinct stages:
- **Stage A (Training Quests)**: Closed GitHub issues grounded in verifiable repository resolution evidence (merged PRs, commit diffs).
- **Stage B (Open-Issue Challenges)**: Open GitHub issues with progressive, server-locked hint tiers paid for with earned XP.
- **Server-Authoritative Gamification**: SQLite ledger tracking user XP, atomic hint deductions, habit consistency scoring, and Stage B unlock progression.

### Repository Layout & Discovery
- **Backend Directory**: `/Users/evariteshkumarchaudhari/Desktop/projects/gitquest`
  - Core Modules: `app.py`, `github_service.py`, `ai_service.py`, `database.py`, `gamification.py`.
  - Testing: Standard `unittest` suite (76 tests passing offline).
- **Frontend Directory**: **External / Inaccessible in Current Workspace**
  - An inspection of `/Users/evariteshkumarchaudhari/Desktop/projects/gitquest` confirms **no frontend directory or `package.json` exists within this repository**.
  - CORS in `app.py` is configured to receive requests from `http://localhost:3000` (Vite/React/Next default) and `http://localhost:5173` (Vite default).
  - This document acts as the definitive integration contract for the frontend repository to connect with the backend without discrepancies.

---

## 2. Server Configuration & Local Development

### Base URL & Ports
- **Backend Base URL**: `http://127.0.0.1:5000`
- **Default Local Port**: `5000` (Configurable via `PORT` in `.env`)
- **Allowed Frontend Origins**:
  - `http://localhost:3000`
  - `http://localhost:5173`
  - Additional origins can be configured via `GITQUEST_ALLOWED_ORIGINS` in `.env` (comma-separated).

### CORS Behavior
- Applied to all `/api/*` endpoints.
- Preflight `OPTIONS` requests return:
  - `Access-Control-Allow-Origin: <Requesting Origin if allowed>`
  - `Access-Control-Allow-Methods: GET, POST, OPTIONS`
  - `Access-Control-Allow-Headers: Content-Type, Authorization`

### Content-Type Requirements
- All `POST` endpoints require header: `Content-Type: application/json`.
- Requests lacking this header or sending malformed JSON receive `HTTP 400 Bad Request`.

---

## 3. Server Authority & Gamification Rules

The backend is the **sole source of truth** for all gamification metrics. Frontend applications must never calculate balances or authorize unlocks locally.

| Metric | Server Authoritative Value | Description |
| :--- | :--- | :--- |
| **Demo User Identity** | `"demo_user"` | Single stable prototype profile; no client-provided user ID is trusted. |
| **Stage A Quest Reward** | `50 XP` | Awarded once upon completion of a closed issue training quest. |
| **Stage B Quest Reward** | `100 XP` | Awarded once upon completion of an open issue challenge. |
| **Hint Tier 1 Cost** | `10 XP` | "Gentle Nudge" — Conceptual hint. |
| **Hint Tier 2 Cost** | `25 XP` | "Investigation Lead" — Targeted module/code navigation hint. |
| **Hint Tier 3 Cost** | `50 XP` | "Tactical Blueprint" — Implementation guidance. |
| **Stage B Unlock Rule** | Earned XP $\ge 200$ **AND** Completed Stage A Quests $\ge 3$ | Both requirements must be met; backend calculates `stage_b_unlocked`. |
| **Initial Consistency Score**| `100.0` | Habit tracking consistency score (scale 0.0 to 100.0). |
| **Inactivity Grace Period** | `48.0 Hours` | No decay occurs if eligible activity occurred within the last 48 hours. |
| **Consistency Decay** | `5.0 Points / Day` | Deducted for each full 24-hour period of inactivity beyond 48 hours. Floored at 0.0. |

---

## 4. Resolution Evidence Rules (Stage A)

A closed issue is **not** evidence of a verified solution by itself. The backend inspects GitHub timeline events and pull request metadata to establish evidence status:

| Status | Verification Criteria | AI Prompt Rule & Grounding | Frontend UI Badge |
| :--- | :--- | :--- | :--- |
| `verified` | Issue timeline contains a linked pull request with `merged: true` or a direct closing commit SHA. Changed files and sanitized unified diffs are extracted. | Synthesizes an explanation of the **actual code fix** merged into the repository. Never invents patches. | 🟢 **Verified Resolution** (Green) |
| `partial` | Issue timeline contains a linked pull request, but `merged: false` (closed without merge). | Explains what is known from discussion, clarifies fix was not merged or verified, guides learner without asserting a solution. | 🟡 **Unverified Resolution** (Yellow) |
| `unavailable` | No linked pull request or commit found in the issue timeline. | Explicitly states no verified patch is on record; structures quest around exploratory investigation. | ⚪ **Resolution Unavailable** (Gray) |

---

## 5. API Endpoint Specifications

---

### Endpoint 1: Health Check
- **Path**: `/health`
- **Method**: `GET`
- **Description**: Verifies backend server health and uptime.

#### Response (200 OK)
```json
{
  "status": "ok"
}
```

---

### Endpoint 2: Fetch Open Issues (Stage B Exploration)
- **Path**: `/api/issues`
- **Method**: `POST`
- **Description**: Retrieves open issues for a public GitHub repository. Automatically filters out pull requests.

#### Request Body
```json
{
  "repo_url": "https://github.com/pallets/flask",
  "limit": 10
}
```
- `repo_url` (`string`, required): Full public GitHub repository URL.
- `limit` (`integer`, optional): Number of issues to retrieve (defaults to 10, capped at 10).

#### Response (200 OK)
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

#### Error Responses
- `400 Bad Request`:
  ```json
  {"error": "Field 'repo_url' is required and must be a non-empty string."}
  ```
  or
  ```json
  {"error": "Non-GitHub host 'gitlab.com'. Only 'github.com' URLs are supported."}
  ```
- `404 Not Found`:
  ```json
  {"error": "Repository 'owner/repo' not found on GitHub."}
  ```
- `429 Too Many Requests`:
  ```json
  {"error": "GitHub API rate limit exceeded."}
  ```
- `502 Bad Gateway`:
  ```json
  {"error": "GitHub API network error or timeout."}
  ```

---

### Endpoint 3: Fetch Closed Issues with Evidence (Stage A Training)
- **Path**: `/api/training/issues`
- **Method**: `POST`
- **Description**: Retrieves closed issues for a repository, inspecting timeline events for linked PRs, merged commits, and verified code diffs.

#### Request Body
```json
{
  "repo_url": "https://github.com/pallets/flask",
  "limit": 5
}
```
- `repo_url` (`string`, required): Public GitHub repository URL.
- `limit` (`integer`, optional): Number of issues to retrieve (default: 5).

#### Response (200 OK)
```json
{
  "count": 1,
  "issues": [
    {
      "number": 5012,
      "title": "Fix context teardown callback ordering",
      "body": "Teardown callbacks were firing in reverse order...",
      "labels": ["bug"],
      "html_url": "https://github.com/pallets/flask/issues/5012",
      "repo": "pallets/flask",
      "resolution_evidence": {
        "status": "verified",
        "issue_number": 5012,
        "repo": "pallets/flask",
        "issue_url": "https://github.com/pallets/flask/issues/5012",
        "linked_pr": {
          "number": 5015,
          "title": "Ensure FIFO order on appcontext teardown",
          "html_url": "https://github.com/pallets/flask/pull/5015",
          "merged": true,
          "merged_at": "2023-04-12T15:30:00Z",
          "merge_commit_sha": "d8f1e2c4a5b6..."
        },
        "linked_prs": ["https://github.com/pallets/flask/pull/5015"],
        "merged_prs": ["https://github.com/pallets/flask/pull/5015"],
        "closing_commit": {
          "sha": "d8f1e2c4a5b6...",
          "html_url": "https://github.com/pallets/flask/commit/d8f1e2c4a5b6..."
        },
        "closing_commits": ["https://github.com/pallets/flask/commit/d8f1e2c4a5b6..."],
        "files_changed": [
          {
            "filename": "src/flask/ctx.py",
            "status": "modified",
            "additions": 4,
            "deletions": 2
          }
        ],
        "patch_excerpt": "@@ -102,4 +102,6 @@ ...",
        "diff_excerpts": ["@@ -102,4 +102,6 @@ ..."],
        "evidence_summary": "Issue resolved by merged Pull Request #5015 ('Ensure FIFO order on appcontext teardown').",
        "summary": "Issue resolved by merged Pull Request #5015 ('Ensure FIFO order on appcontext teardown').",
        "uncertainty_notes": null,
        "evidence_sources": [
          "https://github.com/pallets/flask/pull/5015",
          "https://github.com/pallets/flask/commit/d8f1e2c4a5b6..."
        ]
      }
    }
  ]
}
```

#### Error Responses
- Same error contract as `/api/issues` (`400`, `404`, `429`, `502`, `500`).

---

### Endpoint 4: Generate Training Quest (Stage A)
- **Path**: `/api/training/quest`
- **Method**: `POST`
- **Description**: Generates an educational training quest from a closed issue. Retrieves authoritative evidence on the server; grounds the quest in verified commits/PRs without fabricating solutions. Automatically records the quest in SQLite.

#### Request Body
```json
{
  "issue": {
    "number": 5012,
    "title": "Fix context teardown callback ordering",
    "repo": "pallets/flask",
    "body": "Teardown callbacks were firing in reverse order...",
    "labels": ["bug"],
    "html_url": "https://github.com/pallets/flask/issues/5012"
  },
  "model": "gemma-4-26b-a4b-it"
}
```
*(Note: Can also pass the issue object directly at the root).*

#### Response (200 OK)
```json
{
  "quest": {
    "quest_id": "quest_pallets_flask_5012_training",
    "quest_title": "The Sequence of Teardown",
    "title": "The Sequence of Teardown",
    "tagline": "Restore chronological order to the Flask application context shutdown.",
    "explanation": "Teardown callbacks registered on Flask application contexts must execute in registration order.",
    "difficulty": "Novice",
    "category": "Bug Squashing",
    "xp_reward": 50,
    "xp": 50,
    "estimated_time_minutes": 25,
    "tags": ["Python", "Flask", "Context", "Callbacks"],
    "stage": "A",
    "resolution_status": "verified",
    "resolution_explanation": "Pull request #5015 reversed callback traversal to ensure registration order during cleanup.",
    "evidence_sources": [
      "https://github.com/pallets/flask/pull/5015",
      "https://github.com/pallets/flask/commit/d8f1e2c4a5b6..."
    ],
    "briefing": {
      "lore_intro": "Deep within the Flask engine, callbacks are desynchronizing...",
      "technical_summary": "AppContext.teardown() callbacks were popped in LIFO order instead of executing in FIFO sequence."
    },
    "objectives": [
      {
        "step": 1,
        "title": "Reconnaissance",
        "instruction": "Open src/flask/ctx.py and inspect the teardown_appcontext loop."
      },
      {
        "step": 2,
        "title": "Root Cause Analysis",
        "instruction": "Verify why list iteration order inverted callback execution."
      },
      {
        "step": 3,
        "title": "Resolution Breakdown",
        "instruction": "Review PR #5015 to examine the callback execution order patch."
      }
    ],
    "steps": [
      {
        "step": 1,
        "title": "Reconnaissance",
        "instruction": "Open src/flask/ctx.py and inspect the teardown_appcontext loop."
      },
      {
        "step": 2,
        "title": "Root Cause Analysis",
        "instruction": "Verify why list iteration order inverted callback execution."
      },
      {
        "step": 3,
        "title": "Resolution Breakdown",
        "instruction": "Review PR #5015 to examine the callback execution order patch."
      }
    ],
    "hints": [
      {
        "level": 1,
        "tier": "Gentle Nudge",
        "hint": "Check how callbacks are iterated in the teardown method.",
        "xp_cost": 10,
        "locked": false
      },
      {
        "level": 2,
        "tier": "Investigation Lead",
        "hint": "Compare ctx.py in Flask 2.2 vs Flask 2.3.",
        "xp_cost": 25,
        "locked": false
      },
      {
        "level": 3,
        "tier": "Tactical Blueprint",
        "hint": "Iterate directly over callbacks list without calling reversed().",
        "xp_cost": 50,
        "locked": false
      }
    ],
    "verification_checklist": [
      "Callbacks trigger in FIFO order",
      "No memory leaks during app teardown"
    ],
    "source_issue": {
      "number": 5012,
      "title": "Fix context teardown callback ordering",
      "repo": "pallets/flask"
    }
  }
}
```

#### Error Responses
- `400 Bad Request` (State Mismatch - Open Issue):
  ```json
  {"error": "Stage A training quests require a closed issue with resolution evidence. For open issues, use /api/quest."}
  ```
- `400 Bad Request` (Missing Required Fields):
  ```json
  {"error": "Invalid issue: 'repo' is required and must be a non-empty string."}
  ```
- `400 Bad Request` (Malformed JSON):
  ```json
  {"error": "Request body must be JSON with Content-Type: application/json."}
  ```
- `502 Bad Gateway` (AI Service Error):
  ```json
  {"error": "Failed to generate a valid quest from the AI service response."}
  ```
- `503 Service Unavailable` (Missing API Key):
  ```json
  {"error": "AI service is not configured (missing API key)."}
  ```

---

### Endpoint 5: Generate Open Challenge (Stage B)
- **Path**: `/api/quest`
- **Method**: `POST`
- **Description**: Generates a challenge from an open issue. Redacts hint text with `[LOCKED]` unless already unlocked by the user in SQLite. Automatically registers quest in database.

#### Request Body
```json
{
  "issue": {
    "number": 6146,
    "title": "Add Cloudflare to Flask Hosting Platforms docs",
    "repo": "pallets/flask",
    "body": "Could we add a link to the Cloudflare workers guide?",
    "labels": ["documentation", "good first issue"],
    "html_url": "https://github.com/pallets/flask/issues/6146"
  }
}
```

#### Response (200 OK)
```json
{
  "quest": {
    "quest_id": "quest_pallets_flask_6146",
    "quest_title": "The Cloudflare Beacon",
    "title": "The Cloudflare Beacon",
    "tagline": "Connect the Flask sanctuary with the Cloudflare edge network.",
    "explanation": "Add Cloudflare Workers documentation link to the Flask hosting platforms guide.",
    "difficulty": "Novice",
    "category": "Docs & Discovery",
    "xp_reward": 100,
    "xp": 100,
    "estimated_time_minutes": 20,
    "tags": ["Documentation", "Flask", "Cloudflare"],
    "stage": "B",
    "briefing": {
      "lore_intro": "An urgent distress beacon signals across the perimeter...",
      "technical_summary": "Add Cloudflare Workers documentation link to the Flask hosting platforms guide."
    },
    "objectives": [
      {
        "step": 1,
        "title": "Locate Hosting Documentation",
        "instruction": "Open docs/deploying/index.rst and find the hosting platforms table."
      },
      {
        "step": 2,
        "title": "Add Cloudflare Entry",
        "instruction": "Add reference to the official Cloudflare Flask workers guide."
      }
    ],
    "steps": [
      {
        "step": 1,
        "title": "Locate Hosting Documentation",
        "instruction": "Open docs/deploying/index.rst and find the hosting platforms table."
      },
      {
        "step": 2,
        "title": "Add Cloudflare Entry",
        "instruction": "Add reference to the official Cloudflare Flask workers guide."
      }
    ],
    "hints": [
      {
        "level": 1,
        "tier": "Gentle Nudge",
        "hint": "[LOCKED - Unlock this tier using XP to reveal]",
        "xp_cost": 10,
        "locked": true
      },
      {
        "level": 2,
        "tier": "Investigation Lead",
        "hint": "[LOCKED - Unlock this tier using XP to reveal]",
        "xp_cost": 25,
        "locked": true
      },
      {
        "level": 3,
        "tier": "Tactical Blueprint",
        "hint": "[LOCKED - Unlock this tier using XP to reveal]",
        "xp_cost": 50,
        "locked": true
      }
    ],
    "verification_checklist": [
      "Docs build cleanly with Sphinx",
      "Hyperlink points to active Cloudflare guide"
    ],
    "source_issue": {
      "number": 6146,
      "title": "Add Cloudflare to Flask Hosting Platforms docs",
      "repo": "pallets/flask"
    }
  }
}
```

#### Error Responses
- `400 Bad Request` (State Mismatch - Closed Issue):
  ```json
  {"error": "Stage B challenges require an open issue. For closed issues, use /api/training/quest."}
  ```
- `400 Bad Request` (Missing Required Fields):
  ```json
  {"error": "Invalid issue: 'repo' is required and must be a non-empty string."}
  ```
- `400 Bad Request` (Malformed JSON):
  ```json
  {"error": "Request body must be JSON with Content-Type: application/json."}
  ```
- `502 Bad Gateway` (AI Service Error):
  ```json
  {"error": "Failed to generate a valid quest from the AI service response."}
  ```
- `503 Service Unavailable` (Missing API Key):
  ```json
  {"error": "AI service is not configured (missing API key)."}
  ```

---

### Endpoint 6: Unlock Progressive Hint
- **Path**: `/api/quest/hint/unlock`
- **Method**: `POST`
- **Description**: Atomically deducts hint tier cost from user's XP balance and returns the revealed hint text. Re-accessing an already purchased hint is free and idempotent.

#### Request Body
```json
{
  "quest_id": "quest_pallets_flask_6146",
  "hint_tier": 1
}
```
*(Accepts `hint_tier` or `hint_level`: `1`, `2`, or `3`).*

#### Response (200 OK — Successful Unlock)
```json
{
  "success": true,
  "quest_id": "quest_pallets_flask_6146",
  "hint_tier": 1,
  "tier_name": "Gentle Nudge",
  "xp_deducted": 10,
  "balance": 90,
  "already_purchased": false,
  "hint": "Check docs/deploying/index.rst for existing deployment links.",
  "unlocked_hint": {
    "level": 1,
    "tier": "Gentle Nudge",
    "hint": "Check docs/deploying/index.rst for existing deployment links.",
    "locked": false
  }
}
```

#### Response (200 OK — Re-Accessing Previously Unlocked Hint)
```json
{
  "success": true,
  "quest_id": "quest_pallets_flask_6146",
  "hint_tier": 1,
  "tier_name": "Gentle Nudge",
  "xp_deducted": 0,
  "balance": 90,
  "already_purchased": true,
  "hint": "Check docs/deploying/index.rst for existing deployment links.",
  "unlocked_hint": {
    "level": 1,
    "tier": "Gentle Nudge",
    "hint": "Check docs/deploying/index.rst for existing deployment links.",
    "locked": false
  }
}
```

#### Error Responses
- `400 Bad Request` (Insufficient Balance):
  ```json
  {"error": "Insufficient XP: hint tier 2 costs 25 XP, but current balance is 10 XP."}
  ```
- `400 Bad Request` (Invalid Tier):
  ```json
  {"error": "Invalid hint tier 4. Must be 1, 2, or 3."}
  ```
- `404 Not Found`:
  ```json
  {"error": "Quest 'quest_unknown_999' not found."}
  ```

---

### Endpoint 7: Complete Quest
- **Path**: `/api/quest/complete`
- **Method**: `POST`
- **Description**: Records quest completion, awards authoritative server XP, and resets habit consistency timer. Rejects duplicate completion attempts.

#### Request Body
```json
{
  "quest_id": "quest_pallets_flask_5012_training",
  "stage": "A"
}
```
- `quest_id` (`string`, required): Unique quest ID.
- `stage` (`string`, optional): `"A"` or `"B"`. If omitted, looked up from database.

#### Response (200 OK — Success)
```json
{
  "success": true,
  "quest_id": "quest_pallets_flask_5012_training",
  "stage": "A",
  "awarded_xp": 50,
  "balance": 150,
  "consistency_score": 100.0,
  "stage_b_unlocked": false,
  "already_completed": false,
  "message": "Quest 'quest_pallets_flask_5012_training' completed successfully."
}
```

#### Error Responses
- `400 Bad Request` (Duplicate Completion):
  ```json
  {
    "error": "Quest 'quest_pallets_flask_5012_training' has already been completed by user 'demo_user'.",
    "already_completed": true,
    "quest_id": "quest_pallets_flask_5012_training"
  }
  ```
- `404 Not Found`:
  ```json
  {"error": "Quest 'quest_unknown_999' not found."}
  ```

---

### Endpoint 8: User Profile & Progression Stats
- **Path**: `/api/user/profile`
- **Method**: `GET`
- **Description**: Retrieves authoritative profile statistics, habit consistency, and Stage B unlock progression.

#### Response (200 OK)
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
    },
    "last_eligible_activity_at": "2026-10-18T14:30:00+00:00",
    "created_at": "2026-10-18T12:00:00+00:00"
  }
}
```

#### Error Responses
- `404 Not Found`:
  ```json
  {"error": "User 'demo_user' not found."}
  ```
- `500 Internal Server Error`:
  ```json
  {"error": "An internal server error occurred."}
  ```

---

## 6. Frontend UI State Representations

The frontend (Person 3) must represent the following discrete states for each component:

### 1. Loading States
- **Issue Fetching**: Display skeleton cards for 3–5 items while calling `POST /api/issues` or `POST /api/training/issues`.
- **Quest Generation**: Show an animated RPG briefing loader ("Gemma AI is formulating your quest blueprint...") while calling `POST /api/quest` or `POST /api/training/quest`.
- **Hint Purchase**: Show a spinner inside the specific hint tier button ("Unlocking..."). Disable all other purchase buttons during the call.
- **Quest Completion**: Disable "Complete Quest" button and show a loading spinner.

### 2. Empty States
- **No Issues Found**: If `count === 0`, display a clean empty state: *"No issues matching your criteria were found in this repository. Try another repository or toggle between Open and Closed issues."*
- **No Completed Quests**: In profile view, display: *"You have not completed any quests yet. Start with a Stage A Training Quest below!"*

### 3. Error States
- **Repository URL Error (400)**: Render inline input validation message below the repository input box.
- **Rate Limit (429)**: Display a warning modal: *"GitHub API rate limit reached. Configure a personal access token in backend settings to continue immediately."*
- **AI Service Error (502 / 503)**: Show retry banner: *"Quest generation failed. Check your GEMINI_API_KEY configuration or try again in a few moments."*

### 4. Locked vs. Unlocked Hint States
- **Locked (`locked: true`)**:
  - The text must display `[LOCKED - Unlock this tier using XP to reveal]`.
  - Display an unlock button: `"Unlock for {xp_cost} XP"`.
  - If `profile.earned_xp < hint.xp_cost`, display the button as disabled with text: `"Need {xp_cost} XP (Have {earned_xp})"`.
- **Unlocked (`locked: false`)**:
  - Render the unmasked hint guidance text in an alert card.
  - Display a badge: `"Unlocked"` (or `"Free Re-access"`).
  - Hide the XP purchase button.

### 5. Insufficient XP State
- Triggered when `POST /api/quest/hint/unlock` returns `400` or when user balance is insufficient.
- Render a modal dialog:
  - Title: *"Insufficient XP Balance"*
  - Message: *"Unlocking Tier {tier} requires {cost} XP, but your balance is {balance} XP."*
  - Primary Action: *"Complete Stage A Training Quests (+50 XP each)"* navigating the player to Stage A issues.

### 6. Completed Quest State
- When `already_completed: true` or immediately after successful `POST /api/quest/complete`:
  - Show a celebratory banner: `"Quest Completed! +{awarded_xp} XP Earned"`.
  - Disable the "Complete Quest" button and change label to `"Completed"`.
  - Refresh the header XP balance and consistency score from profile.

### 7. Stage B Locked State
- If `profile.stage_b_unlocked === false`:
  - Display Stage B challenges with a lock overlay.
  - Render a progression checklist:
    - `[x]` Earn at least 200 XP (`{earned_xp} / 200`)
    - `[ ]` Complete at least 3 Stage A Training Quests (`{stage_a_completed_count} / 3`)
  - Keep Stage B issue exploration active, but disable starting Stage B quests until unlocked.

---

## 7. Frontend Screen to API Mapping

| Screen / Component | Needed Backend API | HTTP Method | Actions Performed |
| :--- | :--- | :--- | :--- |
| **Top Navigation Bar** | `/api/user/profile` | `GET` | Fetches XP balance, consistency score, Stage B unlock badge. Polls/refreshes after quest completion or hint purchase. |
| **Repo Explorer / Header** | `/api/issues` | `POST` | Fetches open issues list for Stage B. |
| **Stage A Explorer** | `/api/training/issues` | `POST` | Fetches closed issues with resolution evidence badges. |
| **Stage A Quest View** | `/api/training/quest` | `POST` | Transforms selected closed issue into a Stage A training quest. |
| **Stage B Challenge View**| `/api/quest` | `POST` | Transforms selected open issue into a Stage B challenge (masked hints). |
| **Hint Tier Card** | `/api/quest/hint/unlock` | `POST` | Unlocks hint tier, deducts XP, updates user balance. |
| **Completion Footer** | `/api/quest/complete` | `POST` | Submits quest completion, awards XP, updates consistency. |
| **Profile & Stats Modal** | `/api/user/profile` | `GET` | Displays XP ledger summary, completed quest counts, consistency decay timer. |

---

## 8. Integration Blockers & Missing Components

### Current Blockers:
1. **Frontend Repository Location**:
   - The frontend codebase is **external** to `/Users/evariteshkumarchaudhari/Desktop/projects/gitquest`.
   - **Resolution**: Point the frontend client to `http://localhost:5000` and configure CORS if running on a port other than `3000` or `5173`.
2. **Missing Frontend Components** (to be implemented by Person 3):
   - `ResolutionEvidenceBadge`: Component displaying `verified` (green), `partial` (yellow), or `unavailable` (gray) with tooltip.
   - `LockedHintCard`: Component handling masked hint tiers and atomic unlock button.
   - `StageBProgressionGate`: Component displaying progress towards 200 XP and 3 Stage A quests.
   - `InsufficientXPModal`: Dialog routing players to Stage A when they cannot afford a hint.

---

## 9. Recommended Implementation Order for Full-Stack Integration

1. **Step 1: Verify Backend is Running**
   ```bash
   cd /Users/evariteshkumarchaudhari/Desktop/projects/gitquest
   source .venv/bin/activate
   python app.py
   # Confirms backend is listening on http://127.0.0.1:5000
   ```
2. **Step 2: Connect Top Bar to `/api/user/profile`**
   - Fetch initial user state: `earned_xp`, `consistency_score`, and `stage_b_unlocked`.
3. **Step 3: Implement Stage A Flow**
   - Fetch closed issues via `POST /api/training/issues`.
   - Render `ResolutionEvidenceBadge` based on `issue.resolution_evidence.status`.
   - Generate Stage A quest via `POST /api/training/quest`.
   - Complete quest via `POST /api/quest/complete` and observe `+50 XP` added to profile.
4. **Step 4: Implement Stage B Flow & Hint Protection**
   - Fetch open issues via `POST /api/issues`.
   - Generate Stage B challenge via `POST /api/quest` (verify hints arrive masked with `locked: true`).
   - Call `POST /api/quest/hint/unlock` to reveal hint tier and observe XP deduction.
5. **Step 5: Verify Progression Gate**
   - Verify that Stage B challenges unlock once user completes 3 Stage A quests and has $\ge 200$ XP.

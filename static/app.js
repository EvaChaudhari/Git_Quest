/* =========================================================
   BUG//DUNGEON — GITQUEST FRONTEND CONTROLLER
   Integrated with GitQuest Flask API via docs/INTEGRATION_CONTRACT.md
   static/app.js
   ========================================================= */

(() => {
  "use strict";

  /* ---------------------------------------------------------
     CENTRALIZED API CLIENT
     Handles all network communication with Flask backend
     --------------------------------------------------------- */

  const API_BASE_URL = (() => {
    const meta = document.querySelector('meta[name="gitquest-api-base"]');
    if (meta && meta.content) return meta.content.trim().replace(/\/+$/, "");
    if (typeof window.__GITQUEST_API_URL__ === "string" && window.__GITQUEST_API_URL__.trim()) {
      return window.__GITQUEST_API_URL__.trim().replace(/\/+$/, "");
    }
    return ""; // Default to relative URL on current origin
  })();

  class GitQuestApiClient {
    constructor(baseUrl = API_BASE_URL) {
      this.baseUrl = baseUrl;
    }

    async request(path, options = {}) {
      const url = `${this.baseUrl}${path}`;
      const controller = new AbortController();
      const timeoutMs = options.timeoutMs || 25000;
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

      // Handle custom or external abort signals
      if (options.signal) {
        options.signal.addEventListener("abort", () => controller.abort());
      }

      try {
        const response = await fetch(url, {
          ...options,
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
          }
        });

        clearTimeout(timeoutId);

        const contentType = response.headers.get("content-type") || "";
        let data = null;

        if (contentType.includes("application/json")) {
          try {
            data = await response.json();
          } catch {
            const err = new Error("Invalid JSON response received from GitQuest server.");
            err.status = response.status;
            throw err;
          }
        } else {
          const text = await response.text();
          data = { message: text };
        }

        if (!response.ok) {
          let errorMessage = data?.error || data?.message;
          if (!errorMessage) {
            if (response.status === 400) errorMessage = "Validation error: invalid request parameters.";
            else if (response.status === 401) errorMessage = "Authentication failed. Check backend token configuration.";
            else if (response.status === 403) errorMessage = "Access forbidden. Stage B challenge locked.";
            else if (response.status === 404) errorMessage = "Requested resource, repository, or quest not found.";
            else if (response.status === 409) errorMessage = "Action conflict or duplicate submission.";
            else if (response.status === 429) errorMessage = "GitHub or AI rate limit exceeded. Please wait a moment.";
            else if (response.status === 502) errorMessage = "Upstream model or GitHub gateway failure.";
            else if (response.status === 503) errorMessage = "AI service unconfigured or unavailable. Check API keys.";
            else if (response.status >= 500) errorMessage = "An internal server error occurred on GitQuest backend.";
            else errorMessage = `Request failed with status ${response.status}`;
          }
          const err = new Error(errorMessage);
          err.status = response.status;
          err.data = data;
          throw err;
        }

        return data;
      } catch (error) {
        clearTimeout(timeoutId);
        if (error.name === "AbortError") {
          if (options.signal?.aborted) {
            const abortErr = new Error("Request cancelled.");
            abortErr.name = "AbortError";
            throw abortErr;
          }
          const timeoutErr = new Error("Request timed out. The server took too long to respond.");
          timeoutErr.status = 504;
          throw timeoutErr;
        }
        if (!error.status && error.message && error.message.includes("Failed to fetch")) {
          const netErr = new Error("Network connection failed. Could not reach GitQuest server.");
          netErr.status = 0;
          throw netErr;
        }
        throw error;
      }
    }

    getHealth() {
      return this.request("/health", { method: "GET" });
    }

    getUserProfile() {
      return this.request("/api/user/profile", { method: "GET" });
    }

    getOpenIssues(repoUrl, limit = 10, signal) {
      return this.request("/api/issues", {
        method: "POST",
        body: JSON.stringify({ repo_url: repoUrl, limit }),
        signal
      });
    }

    getTrainingIssues(repoUrl, limit = 10, signal) {
      return this.request("/api/training/issues", {
        method: "POST",
        body: JSON.stringify({ repo_url: repoUrl, limit }),
        signal
      });
    }

    generateTrainingQuest(issue, signal) {
      return this.request("/api/training/quest", {
        method: "POST",
        body: JSON.stringify({ issue }),
        timeoutMs: 60000,
        signal
      });
    }

    generateOpenQuest(issue, signal) {
      return this.request("/api/quest", {
        method: "POST",
        body: JSON.stringify({ issue }),
        timeoutMs: 60000,
        signal
      });
    }

    unlockHint(questId, hintTier) {
      return this.request("/api/quest/hint/unlock", {
        method: "POST",
        body: JSON.stringify({ quest_id: questId, hint_tier: hintTier })
      });
    }

    completeQuest(questId, stage = "A") {
      return this.request("/api/quest/complete", {
        method: "POST",
        body: JSON.stringify({ quest_id: questId, stage })
      });
    }
  }

  const apiClient = new GitQuestApiClient();

  /* ---------------------------------------------------------
     DEVELOPER CLASSES & DOM HELPERS
     --------------------------------------------------------- */

  const $ = (selector, context = document) => context.querySelector(selector);
  const $$ = (selector, context = document) => Array.from(context.querySelectorAll(selector));

  const CLASSES = {
    paladin: { id: "paladin", name: "TypeScript Paladin", short: "TS PALADIN", icon: "🛡️", sub: "Type-Safe Citadel" },
    rogue: { id: "rogue", name: "JavaScript Rogue", short: "JS ROGUE", icon: "🗡️", sub: "Async Shadow" },
    sorcerer: { id: "sorcerer", name: "Python Sorcerer", short: "PY SORCERER", icon: "🐍", sub: "Data Alchemist" },
    artificer: { id: "artificer", name: "Rust Artificer", short: "RS ARTIFICER", icon: "⚙️", sub: "Memory Forge" }
  };

  /* ---------------------------------------------------------
     APPLICATION STATE
     Authoritative state owned by the server
     --------------------------------------------------------- */

  const state = {
    // Repository & Issues
    repositoryUrl: "",
    repository: null,
    learningMode: "A", // "A" = Stage A Training, "B" = Stage B Open Challenges
    issues: [],
    quests: [],
    selectedIssue: null,
    activeQuest: null,

    // Progression & Profile (Server Authoritative)
    userProfile: null,
    completedQuestIds: [],
    purchasedHints: [],

    // UI State & Filters
    activeRegionFilter: null,
    playerClass: "paladin",
    sfxEnabled: true,
    scanned: false,
    currentStep: 0,
    selfVerified: false,
    hintConfirmTier: null,

    // Loading Flags
    loading: false, // Repository scan loading
    generatingQuest: false, // Quest generation loading
    unlockingTier: null, // Hint unlock in-flight tier
    completingQuest: false, // Quest completion in-flight
    loadingProfile: false, // Profile sync in-flight

    // Error States
    error: null, // Repository scan error message
    questError: null, // Quest generation error
    profileError: null // Profile sync error
  };

  // Operation sequence trackers to prevent stale async responses
  let currentScanId = 0;
  let currentQuestGenId = 0;
  let scanAbortController = null;
  let questAbortController = null;

  /* ---------------------------------------------------------
     AUDIO SYNTHESIZER
     Web Audio API procedural sound effects
     --------------------------------------------------------- */

  let audioCtx = null;
  function getAudioContext() {
    if (!audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) audioCtx = new AudioContextClass();
    }
    if (audioCtx && audioCtx.state === "suspended") {
      audioCtx.resume();
    }
    return audioCtx;
  }

  function playSfx(type) {
    if (!state.sfxEnabled) return;
    try {
      const ctx = getAudioContext();
      if (!ctx) return;
      const now = ctx.currentTime;

      if (type === "click" || type === "select") {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(580, now);
        osc.frequency.exponentialRampToValueAtTime(880, now + 0.08);
        gain.gain.setValueAtTime(0.08, now);
        gain.gain.linearRampToValueAtTime(0.001, now + 0.08);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.08);
      } else if (type === "radar" || type === "node") {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(440, now);
        osc.frequency.exponentialRampToValueAtTime(220, now + 0.18);
        gain.gain.setValueAtTime(0.12, now);
        gain.gain.linearRampToValueAtTime(0.001, now + 0.18);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.18);
      } else if (type === "step" || type === "check") {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "triangle";
        osc.frequency.setValueAtTime(520, now);
        osc.frequency.setValueAtTime(659, now + 0.06);
        gain.gain.setValueAtTime(0.1, now);
        gain.gain.linearRampToValueAtTime(0.001, now + 0.15);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.15);
      } else if (type === "complete" || type === "victory") {
        const notes = [523.25, 659.25, 783.99, 1046.5];
        notes.forEach((freq, idx) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = "square";
          osc.frequency.setValueAtTime(freq, now + idx * 0.08);
          gain.gain.setValueAtTime(0.06, now + idx * 0.08);
          gain.gain.linearRampToValueAtTime(0.001, now + idx * 0.08 + 0.14);
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.start(now + idx * 0.08);
          osc.stop(now + idx * 0.08 + 0.15);
        });
      } else if (type === "nyx") {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sawtooth";
        osc.frequency.setValueAtTime(320, now);
        osc.frequency.linearRampToValueAtTime(640, now + 0.12);
        gain.gain.setValueAtTime(0.07, now);
        gain.gain.linearRampToValueAtTime(0.001, now + 0.14);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.14);
      }
    } catch {
      // Audio not permitted or unsupported in environment
    }
  }

  /* ---------------------------------------------------------
     PERSISTENCE (LOCAL PREFERENCES ONLY)
     Authoritative gamification state is owned solely by server
     --------------------------------------------------------- */

  const STORAGE_KEY = "gitquest_ui_preferences_v1";

  function loadPreferences() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (typeof parsed.sfxEnabled === "boolean") state.sfxEnabled = parsed.sfxEnabled;
        if (parsed.playerClass && CLASSES[parsed.playerClass]) state.playerClass = parsed.playerClass;
      }
    } catch (e) {
      console.warn("Could not load UI preferences:", e);
    }
  }

  function savePreferences() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        playerClass: state.playerClass,
        sfxEnabled: state.sfxEnabled
      }));
    } catch (e) {
      console.warn("Could not save UI preferences:", e);
    }
  }

  /* ---------------------------------------------------------
     LOADING & TOAST NOTIFICATIONS
     --------------------------------------------------------- */

  function setLoading(isLoading) {
    state.loading = isLoading;
    const scanBtn = $("#scan-button");
    const repoInput = $("#repo-url");
    const demoBtn = $("#quick-demo-btn");
    const modeBtnA = $("#mode-stage-a-btn");
    const modeBtnB = $("#mode-stage-b-btn");

    if (scanBtn) {
      scanBtn.disabled = isLoading;
      const label = scanBtn.querySelector(".button-label");
      if (label) {
        label.textContent = isLoading ? "⚔ Scanning Realm..." : "⚔ Enter Dungeon";
      }
    }
    if (repoInput) repoInput.disabled = isLoading;
    if (demoBtn) demoBtn.disabled = isLoading;
    if (modeBtnA) modeBtnA.disabled = isLoading;
    if (modeBtnB) modeBtnB.disabled = isLoading;
  }

  function showMessage(text, type = "info") {
    let container = $("#toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${type} mono`;
    toast.textContent = text;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(8px)";
      setTimeout(() => toast.remove(), 300);
    }, 4500);
  }

  /* ---------------------------------------------------------
     STEP 1 & STEP 2 — REPOSITORY SCAN & LEARNING MODE
     --------------------------------------------------------- */

  async function scanRepository(url) {
    if (state.loading) return; // Prevent duplicate concurrent scans

    let rawUrl = (url || $("#repo-url")?.value || "").trim();
    if (!rawUrl) {
      showMessage("Please enter a GitHub repository URL.", "error");
      const input = $("#repo-url");
      if (input) input.focus();
      return;
    }

    // Auto-normalize shorthand forms (e.g. pallets/flask or github.com/pallets/flask)
    if (!rawUrl.startsWith("http://") && !rawUrl.startsWith("https://")) {
      if (rawUrl.startsWith("github.com/")) {
        rawUrl = `https://${rawUrl}`;
      } else if (rawUrl.includes("/") && rawUrl.split("/").length === 2 && !rawUrl.includes(" ")) {
        rawUrl = `https://github.com/${rawUrl}`;
      }
      const input = $("#repo-url");
      if (input) input.value = rawUrl;
    }

    if (!rawUrl.startsWith("https://github.com/") && !rawUrl.startsWith("http://github.com/")) {
      showMessage("Invalid URL. Must be in format https://github.com/owner/repository", "error");
      return;
    }

    // Abort previous in-flight scan and generate unique scan sequence ID
    if (scanAbortController) {
      scanAbortController.abort();
    }
    const currentScanController = new AbortController();
    scanAbortController = currentScanController;
    const scanId = ++currentScanId;

    state.repositoryUrl = rawUrl;
    state.selectedIssue = null;
    state.activeQuest = null;
    state.questError = null;
    state.error = null;
    setLoading(true);
    renderAll();

    try {
      let data;
      if (state.learningMode === "A") {
        data = await apiClient.getTrainingIssues(rawUrl, 10, currentScanController.signal);
      } else {
        data = await apiClient.getOpenIssues(rawUrl, 10, currentScanController.signal);
      }

      // Stale response guard: discard if a newer scan was started
      if (scanId !== currentScanId) return;

      const rawIssues = data?.issues || [];
      state.issues = rawIssues;
      state.quests = normalizeIssues(rawIssues, state.learningMode);
      state.repository = parseRepositoryUrl(rawUrl);
      state.scanned = true;
      state.error = null;

      if (state.quests.length === 0) {
        const modeLabel = state.learningMode === "A" ? "closed training issues with verified evidence" : "open issues";
        showMessage(`Repository scanned, but 0 ${modeLabel} were found.`, "info");
      } else {
        const count = state.quests.length;
        const modeLabel = state.learningMode === "A" ? "Stage A Training" : "Stage B Challenge";
        showMessage(`${count} ${modeLabel} issue${count === 1 ? "" : "s"} retrieved!`, "success");
        // Automatically select first issue
        selectIssue(state.issues[0]);
      }
    } catch (error) {
      if (error.name === "AbortError") return;
      if (scanId !== currentScanId) return;

      console.error("Repository scan failed:", error);
      state.scanned = true;
      state.quests = [];
      state.error = error.message || "Failed to scan repository.";
      showMessage(error.message || "Failed to scan repository.", "error");
    } finally {
      if (scanId === currentScanId) {
        setLoading(false);
        renderAll();
      }
    }
  }

  function parseRepositoryUrl(url) {
    try {
      const parsed = new URL(url);
      const parts = parsed.pathname.split("/").filter(Boolean);
      return {
        owner: parts[0] || "",
        name: (parts[1] || "").replace(/\.git$/, ""),
        url
      };
    } catch {
      return { owner: "", name: "", url };
    }
  }

  /* ---------------------------------------------------------
     ISSUE NORMALIZATION (STEP 1 & 2)
     --------------------------------------------------------- */

  function normalizeIssues(rawIssues, mode) {
    if (!Array.isArray(rawIssues)) return [];

    return rawIssues.map((item, index) => {
      const number = item.number || index + 1;
      const repo = item.repo || (state.repositoryUrl ? state.repositoryUrl.replace(/https?:\/\/github\.com\//, "") : "unknown/repo");
      const questId = `quest_${repo.replace("/", "_")}_${number}${mode === "A" ? "_training" : ""}`;
      const title = item.title || `Issue #${number}`;
      const body = item.body || "No detailed issue description provided.";
      const labels = Array.isArray(item.labels) ? item.labels.map(l => typeof l === "string" ? l : l.name || "") : [];

      // Determine sector landmark
      const textToClassify = `${title} ${body} ${labels.join(" ")}`.toLowerCase();
      let region = "core";
      let regionName = "Main Branch World Tree";
      if (/doc|documentation|guide|manual|archive|legacy|deprecated|tutorial|reference/.test(textToClassify)) {
        region = "archive";
        regionName = "Deprecated Archive";
      } else if (/bug|fix|error|crash|fault|fail|leak|broken|problem|vulnerability|swamp/.test(textToClassify)) {
        region = "swamp";
        regionName = "Bug Swamp";
      } else if (/pr|pull request|first issue|good first|novice|beginner|starter|community/.test(textToClassify)) {
        region = "plaza";
        regionName = "Pull Request Plaza";
      } else if (/feat|feature|add|new|enhancement|forest|gateway|forge/.test(textToClassify)) {
        region = "forest";
        regionName = "Feature Forest";
      }

      // Check authoritative server completion record
      const isCompleted = state.completedQuestIds.includes(questId);
      const xpReward = mode === "A" ? 50 : 100;

      return {
        ...item,
        id: questId,
        quest_id: questId,
        number,
        title,
        body,
        labels,
        stage: mode,
        xp: xpReward,
        xp_reward: xpReward,
        difficulty: mode === "A" ? "Novice" : "Intermediate",
        region,
        region_name: regionName,
        status: isCompleted ? "completed" : "available",
        resolution_evidence: item.resolution_evidence || null,
        url: item.html_url || `https://github.com/${repo}/issues/${number}`
      };
    });
  }

  /* ---------------------------------------------------------
     STEP 3 — SELECT ISSUE & GENERATE QUEST
     --------------------------------------------------------- */

  async function selectIssue(issue) {
    if (!issue) return;
    if (state.generatingQuest) return; // Prevent concurrent quest generation

    // Clear stale quest data immediately to prevent stale UI state
    state.selectedIssue = issue;
    state.activeQuest = null;
    state.questError = null;
    state.currentStep = 0;
    state.selfVerified = false;
    state.hintConfirmTier = null;
    playSfx("select");

    // Check Stage B progression gate
    const isStageBUnlocked = Boolean(state.userProfile?.stage_b_unlocked);
    if (state.learningMode === "B" && !isStageBUnlocked) {
      state.activeQuest = {
        isLockedStageB: true,
        issue
      };
      renderAll();
      return;
    }

    // Reuse cached quest if previously generated for this exact issue
    if (issue.cachedQuest) {
      // Re-verify completion against authoritative list
      if (state.completedQuestIds.includes(issue.cachedQuest.quest_id)) {
        issue.cachedQuest.status = "completed";
      }
      state.activeQuest = issue.cachedQuest;
      renderAll();
      return;
    }

    // Cancel in-flight generation
    if (questAbortController) {
      questAbortController.abort();
    }
    const currentQuestController = new AbortController();
    questAbortController = currentQuestController;
    const questGenId = ++currentQuestGenId;

    state.generatingQuest = true;
    renderSelectedQuest();

    try {
      let data;
      if (state.learningMode === "A") {
        data = await apiClient.generateTrainingQuest(issue, currentQuestController.signal);
      } else {
        data = await apiClient.generateOpenQuest(issue, currentQuestController.signal);
      }

      // Stale response guard: discard if another issue was selected
      if (questGenId !== currentQuestGenId) return;

      const quest = data?.quest;
      if (!quest) {
        throw new Error("Server returned an invalid quest structure.");
      }

      // Attach issue metadata
      if (issue.resolution_evidence && !quest.resolution_evidence) {
        quest.resolution_evidence = issue.resolution_evidence;
      }
      if (!quest.url) {
        quest.url = issue.html_url || issue.url;
      }
      if (!quest.number) {
        quest.number = issue.number;
      }

      // Authoritative hint masking: hints are locked unless server returned unlocked or already purchased
      if (Array.isArray(quest.hints)) {
        quest.hints = quest.hints.map((h, i) => {
          const tierNum = h.level || i + 1;
          const tierCost = h.xp_cost || (tierNum === 1 ? 10 : (tierNum === 2 ? 25 : 50));
          const isPurchased = state.purchasedHints?.some(
            ph => ph.quest_id === quest.quest_id && ph.hint_tier === tierNum
          );
          const isUnlocked = h.locked === false || isPurchased;

          return {
            level: tierNum,
            tier: h.tier || `Tier ${tierNum}`,
            // Never store or display locked hint text on the client before purchase
            hint: isUnlocked ? (h.hint || "") : "",
            locked: !isUnlocked,
            xp_cost: tierCost
          };
        });
      }

      // Normalize objectives/steps
      const steps = quest.steps || quest.objectives || [];
      quest.steps = steps.map((s, idx) => ({
        step: s.step || idx + 1,
        title: s.title || `Step ${idx + 1}`,
        instruction: s.instruction || s.description || ""
      }));

      // Check authoritative completion
      if (state.completedQuestIds.includes(quest.quest_id)) {
        quest.status = "completed";
      }

      issue.cachedQuest = quest;
      state.activeQuest = quest;
      state.questError = null;

      showMessage(`Quest blueprint ready: "${quest.title}" (+${quest.xp} XP)`, "success");
    } catch (error) {
      if (error.name === "AbortError") return;
      if (questGenId !== currentQuestGenId) return;

      console.error("Quest generation failed:", error);
      if (error.status === 403) {
        state.activeQuest = {
          isLockedStageB: true,
          issue
        };
      } else {
        state.activeQuest = {
          isError: true,
          errorMessage: error.message || "Failed to generate quest from AI service.",
          issue
        };
        state.questError = error.message;
      }
      showMessage(error.message || "Failed to generate quest.", "error");
    } finally {
      if (questGenId === currentQuestGenId) {
        state.generatingQuest = false;
        renderAll();
      }
    }
  }

  /* ---------------------------------------------------------
     STEP 4 — PROGRESSIVE HINTS
     Atomic XP deduction owned by backend
     --------------------------------------------------------- */

  async function unlockHintTier(questId, hintTier) {
    if (!state.activeQuest || state.unlockingTier !== null) return;

    const userXp = state.userProfile?.earned_xp ?? 0;
    const targetHint = state.activeQuest.hints?.find(h => h.level === hintTier);
    const tierCost = targetHint?.xp_cost || (hintTier === 1 ? 10 : (hintTier === 2 ? 25 : 50));

    // Solvency validation
    if (userXp < tierCost) {
      showMessage(`Insufficient XP: need ${tierCost} XP, but you have ${userXp} XP.`, "error");
      state.hintConfirmTier = null;
      renderSelectedQuest();
      return;
    }

    state.unlockingTier = hintTier;
    renderSelectedQuest();

    try {
      const res = await apiClient.unlockHint(questId, hintTier);
      playSfx("check");

      // Update unlocked hint text authoritatively from server response
      if (targetHint) {
        targetHint.locked = false;
        targetHint.hint = res.hint || res.unlocked_hint?.hint || targetHint.hint;
      }

      // Record in local purchasedHints list
      if (!state.purchasedHints.some(ph => ph.quest_id === questId && ph.hint_tier === hintTier)) {
        state.purchasedHints.push({ quest_id: questId, hint_tier: hintTier });
      }

      // Update authoritative balance from server response
      if (typeof res.balance === "number" && state.userProfile) {
        state.userProfile.earned_xp = res.balance;
      }

      state.hintConfirmTier = null;
      showMessage(
        res.already_purchased
          ? `Hint re-accessed (Free).`
          : `Hint unlocked! (-${res.xp_deducted} XP). Balance: ${res.balance} XP.`,
        "success"
      );

      // Reconcile authoritative profile with server
      await fetchUserProfile();
    } catch (error) {
      console.error("Hint unlock error:", error);
      showMessage(error.message || "Could not unlock hint.", "error");
      // Re-sync profile to reconcile balance after error
      await fetchUserProfile();
    } finally {
      state.unlockingTier = null;
      renderSelectedQuest();
      updateStats();
    }
  }

  /* ---------------------------------------------------------
     STEP 5 — QUEST COMPLETION & REWARDS
     Authoritative completion reward awarded by server
     --------------------------------------------------------- */

  async function submitQuestCompletion() {
    if (!state.activeQuest || state.completingQuest) return;
    if (!state.selfVerified) {
      showMessage("Please confirm the self-verification declaration before completing.", "info");
      return;
    }

    const quest = state.activeQuest;
    state.completingQuest = true;
    renderSelectedQuest();

    try {
      const stage = quest.stage || state.learningMode;
      const res = await apiClient.completeQuest(quest.quest_id, stage);

      playSfx("complete");
      playSfx("victory");

      quest.status = "completed";
      if (!state.completedQuestIds.includes(quest.quest_id)) {
        state.completedQuestIds.push(quest.quest_id);
      }

      // Update authoritative profile fields from server response
      if (state.userProfile) {
        state.userProfile.earned_xp = res.balance;
        state.userProfile.consistency_score = res.consistency_score;
        state.userProfile.stage_b_unlocked = res.stage_b_unlocked;
        state.userProfile.total_completed_count = (state.userProfile.total_completed_count || 0) + 1;
        if (stage === "A") {
          state.userProfile.stage_a_completed_count = (state.userProfile.stage_a_completed_count || 0) + 1;
        }
      }

      showMessage(`🎉 Quest Cleared! +${res.awarded_xp} XP awarded. Balance: ${res.balance} XP.`, "success");

      // Check loot milestone unlock
      const newlyUnlockedLoot = LOOT_ITEMS.find(l => l.threshold === (state.userProfile?.total_completed_count || 1));
      if (newlyUnlockedLoot) {
        setTimeout(() => {
          playSfx("victory");
          showMessage(`⚔️ DUNGEON LOOT UNLOCKED: [${newlyUnlockedLoot.name}] (${newlyUnlockedLoot.rarity})!`, "success");
        }, 700);
      }

      // Reconcile full profile with server
      await fetchUserProfile();
    } catch (error) {
      console.error("Quest completion error:", error);

      // Handle duplicate completion (HTTP 409 or 400 with already_completed)
      if (error.status === 409 || error.data?.already_completed) {
        quest.status = "completed";
        if (!state.completedQuestIds.includes(quest.quest_id)) {
          state.completedQuestIds.push(quest.quest_id);
        }
        showMessage("This quest was already completed on the server.", "info");
        await fetchUserProfile();
      } else {
        showMessage(error.message || "Failed to record quest completion.", "error");
      }
    } finally {
      state.completingQuest = false;
      renderAll();
    }
  }

  /* ---------------------------------------------------------
     STEP 6 — PROFILE & PROGRESSION
     Central source of truth for gamification metrics
     --------------------------------------------------------- */

  async function fetchUserProfile() {
    state.loadingProfile = true;
    try {
      const data = await apiClient.getUserProfile();
      if (data?.profile) {
        state.userProfile = data.profile;
        if (Array.isArray(data.profile.completed_quest_ids)) {
          state.completedQuestIds = data.profile.completed_quest_ids;
        }
        if (Array.isArray(data.profile.purchased_hints)) {
          state.purchasedHints = data.profile.purchased_hints;
        }
        state.profileError = null;

        // Reconcile active quest status if marked completed on server
        if (state.activeQuest && state.completedQuestIds.includes(state.activeQuest.quest_id)) {
          state.activeQuest.status = "completed";
        }
      }
    } catch (error) {
      console.warn("Could not retrieve user profile from backend:", error);
      state.profileError = error.message;
    } finally {
      state.loadingProfile = false;
      updateStats();
      updateLearningModeUI();
    }
  }

  function updateLearningModeUI() {
    const btnA = $("#mode-stage-a-btn");
    const btnB = $("#mode-stage-b-btn");
    const modeBIcon = $("#mode-b-icon");
    const modeBTitle = $("#mode-b-title");
    const lockBanner = $("#stage-b-lock-banner");
    const hintText = $("#repo-field-hint");

    if (btnA) btnA.classList.toggle("active", state.learningMode === "A");
    if (btnB) btnB.classList.toggle("active", state.learningMode === "B");

    const isStageBUnlocked = Boolean(state.userProfile?.stage_b_unlocked);

    if (modeBIcon) {
      modeBIcon.textContent = isStageBUnlocked ? "⚔️" : "🔒";
    }
    if (modeBTitle) {
      modeBTitle.textContent = isStageBUnlocked ? "Stage B: Open Challenges (Unlocked)" : "Stage B: Open Challenges (Locked)";
    }

    if (lockBanner) {
      const showLockBanner = state.learningMode === "B" && !isStageBUnlocked;
      lockBanner.hidden = !showLockBanner;
      if (showLockBanner) {
        const xpVal = state.userProfile?.earned_xp ?? 0;
        const qCount = state.userProfile?.stage_a_completed_count ?? 0;
        const xpEl = $("#lock-xp-metric");
        const qEl = $("#lock-quests-metric");
        if (xpEl) xpEl.textContent = `XP: ${xpVal} / 200`;
        if (qEl) qEl.textContent = `Stage A Quests: ${qCount} / 3`;
      }
    }

    if (hintText) {
      hintText.textContent = state.learningMode === "A"
        ? "Paste any public repository to retrieve Stage A closed issues with resolution evidence."
        : "Paste any public repository to retrieve Stage B live open issues.";
    }
  }

  /* ---------------------------------------------------------
     RENDERING FUNCTIONS
     --------------------------------------------------------- */

  function renderAll() {
    renderQuestList();
    renderSelectedQuest();
    updateStats();
    updateWorldState();
    updateLearningModeUI();
  }

  function renderQuestList() {
    const container = $("#issues-list");
    if (!container) return;

    if (state.loading) {
      container.innerHTML = `
        <div class="empty-state dungeon-panel">
          <div class="nyx-loading" style="font-size:14px; margin-bottom:10px;">
            ⚔ SCANNING REPOSITORY VIA GITQUEST SERVER...
          </div>
          <p class="muted">Retrieving issues from GitHub and verifying resolution evidence.</p>
        </div>
      `;
      return;
    }

    if (state.error) {
      container.innerHTML = `
        <div class="error-state dungeon-panel">
          <div class="error-icon">!</div>
          <h3>Repository Scan Failed</h3>
          <p>${escapeHtml(state.error)}</p>
          <p class="error-help">Make sure the repository is public and formatted like <code>https://github.com/owner/repo</code>.</p>
          <div class="error-actions" style="margin-top:16px;">
            <button type="button" class="button button-primary button-sm" id="retry-scan-btn">
              ↻ Retry Scan
            </button>
          </div>
        </div>
      `;
      const retryBtn = container.querySelector("#retry-scan-btn");
      if (retryBtn) {
        retryBtn.addEventListener("click", () => {
          scanRepository(state.repositoryUrl);
        });
      }
      return;
    }

    if (!state.scanned) {
      container.innerHTML = `
        <div class="empty-state dungeon-panel">
          <div class="empty-dungeon-art" aria-hidden="true">
            <span class="empty-torch">🔥</span>
            <div class="empty-gate"><div class="gate-arch">⌁</div></div>
            <span class="empty-torch">🔥</span>
          </div>
          <h3>Your next adventure awaits</h3>
          <p>Scan a repository to reveal ${state.learningMode === "A" ? "Stage A training quests" : "Stage B open challenges"}.</p>
          <span class="empty-code mono">AWAITING_REPOSITORY_INPUT_</span>
        </div>
      `;
      return;
    }

    if (state.quests.length === 0) {
      container.innerHTML = `
        <div class="empty-state dungeon-panel">
          <div class="empty-dungeon-art" aria-hidden="true">
            <span class="empty-torch">🔥</span>
            <div class="empty-gate"><div class="gate-arch">◇</div></div>
            <span class="empty-torch">🔥</span>
          </div>
          <h3>No Quests Found</h3>
          <p>This repository did not return any ${state.learningMode === "A" ? "closed training issues with evidence" : "open issues"}.</p>
          <span class="empty-code mono">0_ANOMALIES_DETECTED</span>
        </div>
      `;
      return;
    }

    const visibleQuests = state.activeRegionFilter
      ? state.quests.filter(q => q.region === state.activeRegionFilter)
      : state.quests;

    if (visibleQuests.length === 0) {
      container.innerHTML = `
        <div class="empty-state dungeon-panel">
          <h3>No Quests in this Sector</h3>
          <p>There are no issues assigned to ${escapeHtml(state.activeRegionFilter.toUpperCase())}.</p>
          <button type="button" class="button button-ghost button-sm" id="clear-sector-filter" style="margin-top:10px;">View All Sectors</button>
        </div>
      `;
      const clr = container.querySelector("#clear-sector-filter");
      if (clr) {
        clr.addEventListener("click", () => {
          state.activeRegionFilter = null;
          $$(".region-node").forEach(n => n.classList.remove("active"));
          renderQuestList();
        });
      }
      return;
    }

    container.innerHTML = visibleQuests.map((quest) => {
      const selected = state.selectedIssue?.number === quest.number;
      const completed = quest.status === "completed" || state.completedQuestIds.includes(quest.quest_id);
      const isStageA = quest.stage === "A";

      // Evidence badge for Stage A
      let evidenceBadgeHtml = "";
      if (isStageA && quest.resolution_evidence) {
        const evStatus = quest.resolution_evidence.status || "unavailable";
        if (evStatus === "verified") {
          evidenceBadgeHtml = `<span class="evidence-badge verified">🟢 Verified Fix</span>`;
        } else if (evStatus === "partial") {
          evidenceBadgeHtml = `<span class="evidence-badge partial">🟡 Partial Evidence</span>`;
        } else {
          evidenceBadgeHtml = `<span class="evidence-badge unavailable">⚪ No Patch on Record</span>`;
        }
      }

      return `
        <article
          class="issue-card quest-card ${selected ? "selected" : ""} ${completed ? "cleared completed" : ""}"
          data-issue-number="${escapeHtml(String(quest.number))}"
          tabindex="0"
          role="button"
          aria-pressed="${selected}"
        >
          <div class="issue-top quest-card-top">
            <span class="issue-number quest-number mono">#${escapeHtml(quest.number)}</span>
            <span class="stage-tag">${isStageA ? "STAGE A: TRAINING" : "STAGE B: CHALLENGE"}</span>
            ${evidenceBadgeHtml}
            <span class="issue-label quest-difficulty">+${quest.xp} XP</span>
          </div>

          <h3 class="issue-title">${escapeHtml(quest.title)}</h3>

          <p class="issue-body quest-description">
            ${escapeHtml(truncate(stripMarkdown(quest.body), 140))}
          </p>

          <div class="issue-footer quest-card-bottom">
            <div class="labels">
              <span class="sector-chip sector-${escapeHtml(quest.region || "core")}">${escapeHtml(quest.region_name || "Sector")}</span>
              ${quest.labels && quest.labels.length
                ? quest.labels.slice(0, 2).map(l => `<span class="label-chip">${escapeHtml(l)}</span>`).join("")
                : ""
              }
            </div>
            <span class="select-quest mono">
              ${completed ? "CLEARED ✓" : (selected ? "INVESTIGATING ⚔" : "SELECT QUEST →")}
            </span>
          </div>
        </article>
      `;
    }).join("");

    container.querySelectorAll(".quest-card").forEach((card) => {
      const num = Number(card.dataset.issueNumber);
      const targetIssue = state.issues.find(i => i.number === num);
      if (targetIssue) {
        card.addEventListener("click", () => selectIssue(targetIssue));
        card.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            selectIssue(targetIssue);
          }
        });
      }
    });
  }

  function renderSelectedQuest() {
    const briefingText = $("#briefing-text");
    const companionDialogue = $("#companion-dialogue");
    const explainButton = $("#explain-button");
    const hintButton = $("#hint-button");
    const investigationSlot = $("#investigation-slot");
    const bossAlertBanner = $("#boss-alert-banner");

    if (!state.selectedIssue) {
      if (bossAlertBanner) bossAlertBanner.hidden = true;
      if (briefingText) briefingText.textContent = "Your companion will brief you once an issue is selected.";
      if (companionDialogue) companionDialogue.textContent = "“A good investigator studies the clues before attacking the boss.”";
      if (explainButton) explainButton.disabled = true;
      if (hintButton) hintButton.disabled = true;
      if (investigationSlot) investigationSlot.innerHTML = "";
      return;
    }

    const issue = state.selectedIssue;

    if (explainButton) explainButton.disabled = false;
    if (hintButton) hintButton.disabled = false;

    // Loading state during AI quest generation
    if (state.generatingQuest) {
      if (briefingText) {
        briefingText.innerHTML = `<strong>Generating Quest #${issue.number}...</strong><br><span class="muted">${escapeHtml(issue.title)}</span>`;
      }
      if (companionDialogue) {
        companionDialogue.innerHTML = `<em>“Gemma AI is formulating your quest blueprint from repository telemetry...”</em>`;
      }
      if (investigationSlot) {
        investigationSlot.innerHTML = `
          <div class="dungeon-panel" style="padding: 24px; text-align: center;">
            <div class="nyx-loading" style="font-size: 13px; margin-bottom: 12px;">
              ⚡ TRANSMITTING TO GEMMA AI SERVICE...
            </div>
            <p class="muted" style="font-size: 12px;">Synthesizing objectives, technical directives, and progressive hint structures.</p>
          </div>
        `;
      }
      return;
    }

    // Stage B locked state
    if (state.activeQuest?.isLockedStageB) {
      if (briefingText) {
        briefingText.innerHTML = `<strong>Stage B Challenge Locked</strong><br><span class="muted">Issue #${issue.number}: ${escapeHtml(issue.title)}</span>`;
      }
      if (investigationSlot) {
        const userXp = state.userProfile?.earned_xp ?? 0;
        const qCount = state.userProfile?.stage_a_completed_count ?? 0;
        investigationSlot.innerHTML = `
          <div class="stage-b-locked-card" style="margin-top: 10px;">
            <div class="lock-icon">🔒</div>
            <div class="lock-details">
              <strong>STAGE B REQUIREMENT NOT MET</strong>
              <p>Stage B challenges require real software problem-solving on live issues. You must satisfy the backend progression gate first.</p>
              <div class="lock-metrics" style="margin: 10px 0;">
                <span class="lock-badge">XP: ${userXp} / 200</span>
                <span class="lock-badge">Completed Stage A Quests: ${qCount} / 3</span>
              </div>
              <button type="button" class="button button-primary button-sm" id="unlock-route-stage-a">
                ⚔ Complete Stage A Quests (+50 XP each)
              </button>
            </div>
          </div>
        `;
        const rtBtn = investigationSlot.querySelector("#unlock-route-stage-a");
        if (rtBtn) {
          rtBtn.addEventListener("click", () => {
            state.learningMode = "A";
            updateLearningModeUI();
            if (state.repositoryUrl) scanRepository(state.repositoryUrl);
          });
        }
      }
      return;
    }

    // Error state during quest generation
    if (state.activeQuest?.isError) {
      if (briefingText) briefingText.innerHTML = `<span style="color:var(--red);">Quest Generation Error</span>`;
      if (investigationSlot) {
        investigationSlot.innerHTML = `
          <div class="error-state dungeon-panel" style="padding: 20px;">
            <div class="error-icon">!</div>
            <h4>Quest Generation Failed</h4>
            <p style="font-size: 13px; margin: 8px 0;">${escapeHtml(state.activeQuest.errorMessage)}</p>
            <div class="error-actions" style="margin-top:14px;">
              <button type="button" class="button button-primary button-sm" id="retry-quest-gen-btn">
                ↻ Retry Quest Generation
              </button>
            </div>
          </div>
        `;
        const retryBtn = investigationSlot.querySelector("#retry-quest-gen-btn");
        if (retryBtn) retryBtn.addEventListener("click", () => selectIssue(issue));
      }
      return;
    }

    const quest = state.activeQuest;
    if (!quest) return;

    // Boss banner check
    if (bossAlertBanner) {
      const isBoss = /boss|merge|conflict|critical|security|fatal/i.test(quest.title + " " + (quest.category || ""));
      bossAlertBanner.hidden = !isBoss;
    }

    // Briefing text
    if (briefingText) {
      briefingText.innerHTML = `
        <strong>${escapeHtml(quest.title)}</strong>
        ${quest.tagline ? `<p style="margin: 6px 0; color: #d6cce7; font-style: italic;">“${escapeHtml(quest.tagline)}”</p>` : ""}
        ${quest.explanation ? `<p style="margin: 4px 0; font-size: 11px;"><strong>DIRECTIVE:</strong> ${escapeHtml(quest.explanation)}</p>` : ""}
      `;
    }

    if (companionDialogue) {
      companionDialogue.innerHTML = `“Quest <strong>#${escapeHtml(quest.number || issue.number)}</strong> active (${escapeHtml(String(quest.difficulty).toUpperCase())} · +${quest.xp} XP). Consult NYX for hints or an explanation.”`;
    }

    // Render detailed investigation dossier in investigationSlot
    if (investigationSlot) {
      const isCompleted = quest.status === "completed" || state.completedQuestIds.includes(quest.quest_id);
      const isStageA = (quest.stage || state.learningMode) === "A";
      const evidence = quest.resolution_evidence || issue.resolution_evidence;
      const steps = quest.steps || [];
      const checklist = quest.verification_checklist || [];
      const hints = quest.hints || [];

      // Evidence Block
      let evidenceBlock = "";
      if (isStageA) {
        const evStatus = evidence?.status || quest.resolution_status || "unavailable";
        const summaryText = evidence?.summary || quest.resolution_explanation || "No resolution summary on record.";
        const sources = evidence?.evidence_sources || quest.evidence_sources || [];

        evidenceBlock = `
          <div class="grounded-evidence-box">
            <div class="evidence-box-header">
              <span class="evidence-legend mono">GROUNDED REPOSITORY EVIDENCE (Server-Verified)</span>
              <span class="evidence-badge ${evStatus}">
                ${evStatus === "verified" ? "🟢 Verified Resolution" : (evStatus === "partial" ? "🟡 Partial Evidence" : "⚪ Resolution Unavailable")}
              </span>
            </div>
            <p class="evidence-summary">${escapeHtml(summaryText)}</p>
            ${sources && sources.length ? `
              <div class="evidence-sources">
                <span class="mono" style="font-size:10px; color:var(--muted);">VERIFIED COMMIT / PR SOURCES:</span>
                ${sources.map(src => `<a href="${escapeHtml(src)}" target="_blank" rel="noopener noreferrer" class="evidence-source-link">${escapeHtml(src)} ↗</a>`).join("")}
              </div>
            ` : ""}
            <p class="mono muted" style="font-size:10px; margin-top:8px;">Note: GitQuest never presents AI-generated text as verified repository fixes.</p>
          </div>
        `;
      }

      investigationSlot.innerHTML = `
        <!-- Quest Header & GitHub Link -->
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; flex-wrap:wrap; gap:8px;">
          <div>
            <span class="stage-tag">${isStageA ? "STAGE A: TRAINING QUEST" : "STAGE B: OPEN CHALLENGE"}</span>
            <span class="label-chip mono" style="color:var(--gold);">+${quest.xp} XP REWARD</span>
          </div>
          ${quest.url ? `
            <a href="${escapeHtml(quest.url)}" target="_blank" rel="noopener noreferrer" class="button button-ghost button-sm mono" style="font-size:11px;">
              🔗 View Issue #${quest.number || issue.number} on GitHub ↗
            </a>
          ` : ""}
        </div>

        ${evidenceBlock}

        <!-- Objectives / Steps -->
        <div class="steps" style="margin-top:16px;">
          <div class="steps-title mono">
            OBJECTIVES (${steps.length} STEPS)
          </div>

          ${steps.map((st, idx) => `
            <label class="step-item ${idx <= state.currentStep ? "current" : ""}">
              <input type="checkbox" data-step-idx="${idx}" ${idx < state.currentStep || isCompleted ? "checked" : ""}>
              <span>
                <strong>Step ${st.step || idx + 1}: ${escapeHtml(st.title)}</strong><br>
                <span style="font-size:12px; color:var(--text);">${escapeHtml(st.instruction)}</span>
              </span>
            </label>
          `).join("")}
        </div>

        <!-- Verification Checklist -->
        ${checklist.length ? `
          <div class="verification-container" style="margin-top: 14px;">
            <div class="steps-title mono" style="color: var(--green); margin-bottom: 6px;">VERIFICATION CHECKLIST</div>
            ${checklist.map((v) => `
              <label class="step-item" style="margin-top: 5px;">
                <input type="checkbox" ${isCompleted ? "checked disabled" : ""}>
                <span style="color: #bbf7d0; font-size: 11px;">${escapeHtml(v)}</span>
              </label>
            `).join("")}
          </div>
        ` : ""}

        <!-- Progressive Hints Section (Step 4) -->
        <div class="hints-section" style="margin-top: 20px;">
          <div class="steps-title mono">
            PROGRESSIVE GUIDANCE / HINTS (${hints.length} TIERS)
          </div>

          <div class="hints-container">
            ${hints.map((hint) => {
              const isLocked = hint.locked !== false;
              const tierCost = hint.xp_cost || (hint.level === 1 ? 10 : (hint.level === 2 ? 25 : 50));
              const tierName = hint.tier || `Tier ${hint.level}`;
              const userXp = state.userProfile?.earned_xp ?? 0;
              const canAfford = userXp >= tierCost;
              const isConfirming = state.hintConfirmTier === hint.level;
              const isUnlockingThis = state.unlockingTier === hint.level;

              if (!isLocked) {
                return `
                  <div class="hint-tier-card unlocked">
                    <div class="hint-tier-header">
                      <span class="hint-tier-name">💡 ${escapeHtml(tierName)}</span>
                      <span class="evidence-badge verified" style="font-size:10px;">UNLOCKED ✓</span>
                    </div>
                    <div class="hint-body-text">${formatMarkdownLite(hint.hint)}</div>
                  </div>
                `;
              }

              return `
                <div class="hint-tier-card locked" id="hint-tier-box-${hint.level}">
                  <div class="hint-tier-header">
                    <span class="hint-tier-name">🔒 ${escapeHtml(tierName)}</span>
                    <span class="hint-tier-cost">${tierCost} XP</span>
                  </div>
                  <div class="hint-masked-text">🔒 Guidance Locked — Confirm unlock below to reveal with ${tierCost} XP.</div>
                  ${isConfirming ? `
                    <div class="hint-confirm-box">
                      <span>Spend ${tierCost} XP to reveal ${escapeHtml(tierName)}?</span>
                      <div class="hint-confirm-actions">
                        <button type="button" class="button button-primary button-sm btn-confirm-unlock" data-tier="${hint.level}" ${state.unlockingTier ? "disabled" : ""}>
                          ${isUnlockingThis ? "Unlocking..." : "Confirm Unlock"}
                        </button>
                        <button type="button" class="button button-ghost button-sm btn-cancel-unlock" ${state.unlockingTier ? "disabled" : ""}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  ` : `
                    <button
                      type="button"
                      class="button button-ghost button-sm btn-prompt-unlock"
                      data-tier="${hint.level}"
                      ${!canAfford || state.unlockingTier ? "disabled" : ""}
                    >
                      ${isUnlockingThis
                        ? "Unlocking..."
                        : (canAfford ? `Unlock for ${tierCost} XP` : `Need ${tierCost} XP (Have ${userXp} XP)`)}
                    </button>
                  `}
                </div>
              `;
            }).join("")}
          </div>
        </div>

        <!-- Quest Completion Section (Step 5) -->
        <div class="quest-completion-box">
          <div class="steps-title mono" style="color:var(--gold); margin-bottom:8px;">QUEST COMPLETION &amp; REWARD</div>
          ${isCompleted ? `
            <div class="quest-completed-banner">
              <span>⚔️</span>
              <strong>Quest Cleared! Reward was awarded by the server.</strong>
            </div>
          ` : `
            <label class="completion-verify-label">
              <input type="checkbox" id="self-verify-checkbox" ${state.selfVerified ? "checked" : ""} ${state.completingQuest ? "disabled" : ""}>
              <span><strong>Self-Verification Declaration:</strong> I have reviewed the objectives, investigated the code, and verified the solution methodology.</span>
            </label>
            <p class="mono muted" style="font-size:10px; margin-top:4px; margin-bottom:8px;">
              ℹ️ Note: Completion is a user-confirmed learning activity. No local XP is awarded until confirmed by the GitQuest server.
            </p>
            <button
              type="button"
              class="button button-primary complete-button"
              id="submit-quest-completion-btn"
              ${!state.selfVerified || state.completingQuest ? "disabled" : ""}
            >
              ${state.completingQuest ? "Recording with GitQuest Server..." : `Complete Quest (+${quest.xp} XP) ✓`}
            </button>
          `}
        </div>
      `;

      // Wire Objective step checkboxes
      investigationSlot.querySelectorAll('input[type="checkbox"][data-step-idx]').forEach((cb) => {
        cb.addEventListener("change", (e) => {
          const idx = Number(e.target.dataset.stepIdx);
          state.currentStep = e.target.checked ? Math.min(idx + 1, steps.length - 1) : Math.max(idx, 0);
          playSfx("step");
          renderSelectedQuest();
        });
      });

      // Wire Hint Confirmation & Unlock buttons
      investigationSlot.querySelectorAll(".btn-prompt-unlock").forEach((btn) => {
        btn.addEventListener("click", () => {
          if (state.unlockingTier) return;
          state.hintConfirmTier = Number(btn.dataset.tier);
          playSfx("click");
          renderSelectedQuest();
        });
      });

      investigationSlot.querySelectorAll(".btn-cancel-unlock").forEach((btn) => {
        btn.addEventListener("click", () => {
          if (state.unlockingTier) return;
          state.hintConfirmTier = null;
          playSfx("click");
          renderSelectedQuest();
        });
      });

      investigationSlot.querySelectorAll(".btn-confirm-unlock").forEach((btn) => {
        btn.addEventListener("click", () => {
          if (state.unlockingTier) return;
          const tier = Number(btn.dataset.tier);
          unlockHintTier(quest.quest_id, tier);
        });
      });

      // Wire Self-verification Checkbox
      const verifyCheck = investigationSlot.querySelector("#self-verify-checkbox");
      if (verifyCheck) {
        verifyCheck.addEventListener("change", (e) => {
          state.selfVerified = e.target.checked;
          const compBtn = investigationSlot.querySelector("#submit-quest-completion-btn");
          if (compBtn) compBtn.disabled = !state.selfVerified || state.completingQuest;
        });
      }

      // Wire Quest Completion Submit Button
      const compBtn = investigationSlot.querySelector("#submit-quest-completion-btn");
      if (compBtn) {
        compBtn.addEventListener("click", () => {
          submitQuestCompletion();
        });
      }
    }
  }

  /* ---------------------------------------------------------
     STATS / HUD & LOOT UPDATES (STEP 6)
     --------------------------------------------------------- */

  const LOOT_ITEMS = [
    { id: "dagger", threshold: 1, name: "Console.log Dagger", rarity: "Common", desc: "The first incantation every developer cast. Still works." },
    { id: "shield", threshold: 2, name: "Pending PR Shield", rarity: "Rare", desc: "Awaiting review. +12 Defense while pending. No one has approved it yet." },
    { id: "branch", threshold: 3, name: "Crystallized Branch", rarity: "Epic", desc: "A crystallised git branch. Grants the ability to revert one mistake." },
    { id: "crown", threshold: 5, name: "Crown of Force Push", rarity: "Legendary", desc: "May force-push to production. Embroidered with commit history." }
  ];

  function updateStats() {
    const prof = state.userProfile;
    const xp = prof ? prof.earned_xp : 0;
    const completed = prof ? prof.total_completed_count : state.completedQuestIds.length;
    const stageACount = prof ? prof.stage_a_completed_count : 0;
    const consistency = prof ? prof.consistency_score : 100.0;
    const stageBUnlocked = prof ? Boolean(prof.stage_b_unlocked) : false;

    // HUD Topbar stats
    $$(".xp-val, #xp-value").forEach(el => el.textContent = prof ? xp : "--");
    $$(".completed-val, #completed-count").forEach(el => el.textContent = prof ? completed : "--");

    const consistencyVal = $("#consistency-val");
    if (consistencyVal) consistencyVal.textContent = prof ? consistency.toFixed(1) : "--";

    const stageBStatIcon = $("#stage-b-hud-icon");
    const stageBStatText = $("#stage-b-hud-text");
    if (stageBStatIcon) stageBStatIcon.textContent = stageBUnlocked ? "🔓" : "🔒";
    if (stageBStatText) stageBStatText.textContent = stageBUnlocked ? "STAGE B UNLOCKED" : "STAGE B LOCKED";

    const questCountEl = $("#quest-count");
    if (questCountEl) {
      questCountEl.textContent = `${state.quests.length} QUESTS FOUND`;
    }

    // Profile panel stats
    const profXp = $("#profile-xp-value");
    if (profXp) profXp.textContent = prof ? xp : "--";

    const profCompleted = $("#profile-completed-count");
    if (profCompleted) profCompleted.textContent = prof ? completed : "--";

    const profStageA = $("#profile-stage-a-count");
    if (profStageA) profStageA.textContent = prof ? stageACount : "--";

    const profCons = $("#profile-consistency-score");
    if (profCons) profCons.textContent = prof ? `${consistency.toFixed(1)}%` : "--%";

    const profStageBStatus = $("#profile-stage-b-status");
    if (profStageBStatus) {
      profStageBStatus.textContent = stageBUnlocked ? "UNLOCKED" : "LOCKED";
      profStageBStatus.className = `stat-number ${stageBUnlocked ? "stage-status-unlocked" : "stage-status-locked"}`;
    }

    const progXpVal = $("#prog-xp-val");
    if (progXpVal) progXpVal.textContent = prof ? `${xp} / 200` : "-- / 200";

    const progQuestsVal = $("#prog-quests-val");
    if (progQuestsVal) progQuestsVal.textContent = prof ? `${stageACount} / 3` : "-- / 3";

    // XP Progress & Levels
    const level = Math.floor(xp / 500) + 1;
    const levelFormatted = `LVL 0${level}`;
    $$(".level-badge, #level-badge, #profile-level-badge").forEach(el => el.textContent = levelFormatted);

    const levelTitles = ["ROOKIE", "APPRENTICE", "BUG HUNTER", "CODE SORCERER", "DUNGEON MASTER"];
    const currentTitle = levelTitles[Math.min(level - 1, levelTitles.length - 1)];
    $$("#level-name, #profile-level-name").forEach(el => el.textContent = currentTitle);

    const nextLevel = $("#next-level");
    if (nextLevel) {
      const needed = 500 - (xp % 500);
      nextLevel.textContent = `${needed} XP TO LEVEL ${level + 1}`;
    }

    const progress = ((xp % 500) / 500) * 100;
    $$("#xp-progress, .progress-fill").forEach(el => el.style.width = `${progress}%`);

    // Class selection
    const currentClass = CLASSES[state.playerClass] || CLASSES.paladin;
    const topClassIcon = $("#topbar-class-icon");
    const topClassName = $("#topbar-class-name");
    if (topClassIcon) topClassIcon.textContent = currentClass.icon;
    if (topClassName) topClassName.textContent = currentClass.short;

    const profClassIcon = $("#profile-class-icon");
    const profClassName = $("#profile-class-name");
    const profClassSub = $("#profile-class-sub");
    if (profClassIcon) profClassIcon.textContent = currentClass.icon;
    if (profClassName) profClassName.textContent = currentClass.name;
    if (profClassSub) profClassSub.textContent = currentClass.sub;

    $$(".class-card").forEach(card => {
      card.classList.toggle("active", card.dataset.class === state.playerClass);
    });

    // Loot slots
    let unlockedLoot = 0;
    LOOT_ITEMS.forEach(item => {
      const isUnlocked = completed >= item.threshold;
      if (isUnlocked) unlockedLoot++;
      const slot = $(`[data-loot-id="${item.id}"]`);
      if (slot) {
        slot.classList.toggle("empty", !isUnlocked);
        slot.title = isUnlocked
          ? `[UNLOCKED] ${item.name} (${item.rarity}): ${item.desc}`
          : `[LOCKED] ${item.name}: Clear ${item.threshold} quest${item.threshold > 1 ? "s" : ""} to unlock`;
      }
    });

    const lootCountEl = $("#loot-count");
    if (lootCountEl) {
      lootCountEl.textContent = `${unlockedLoot}/4 UNLOCKED`;
    }
  }

  function updateWorldState() {
    const world = $("#world-map");
    if (world) {
      world.classList.toggle("locked", !state.scanned);
    }

    const coords = $("#map-coordinates");
    if (coords) {
      coords.textContent = state.repository
        ? `${state.repository.owner.toUpperCase()} / ${state.repository.name.toUpperCase()}`
        : "SECTOR 00 · UNINITIALIZED";
    }

    const regionMsg = $("#region-message");
    if (regionMsg) {
      if (!state.scanned) {
        regionMsg.textContent = "Scan a repository or select any dungeon sector above to view active quests.";
      } else if (state.activeRegionFilter) {
        const activeNode = $(`[data-region="${state.activeRegionFilter}"]`);
        const lore = activeNode?.dataset?.lore || "";
        regionMsg.innerHTML = `<strong>${state.activeRegionFilter.toUpperCase()}:</strong> ${lore || "Active sector highlighted."}`;
      } else {
        regionMsg.textContent = `Realm active: ${state.quests.length} quest${state.quests.length === 1 ? "" : "s"} in repository.`;
      }
    }

    const regionCounts = { forest: 0, swamp: 0, plaza: 0, core: 0, archive: 0 };
    state.quests.forEach((q) => {
      const reg = q.region || "core";
      if (regionCounts[reg] !== undefined) {
        regionCounts[reg] += 1;
      }
    });

    $$(".region-node").forEach((node) => {
      const reg = node.dataset.region;
      const count = regionCounts[reg] || 0;
      const stateSpan = node.querySelector(".node-state");
      if (stateSpan) {
        stateSpan.innerHTML = state.scanned
          ? `<strong class="node-count">${count}</strong> ${count > 0 ? "ACTIVE" : "CLEAR"}`
          : `<strong class="node-count">0</strong> QUESTS`;
      }
    });
  }

  /* ---------------------------------------------------------
     TEXT & MARKDOWN UTILS (XSS PREVENTION)
     --------------------------------------------------------- */

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function stripMarkdown(text) {
    return String(text || "")
      .replace(/```[\s\S]*?```/g, "")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/\*([^*]+)\*/g, "$1")
      .replace(/__([^_]+)__/g, "$1")
      .replace(/_([^_]+)_/g, "$1")
      .replace(/^#{1,6}\s+/gm, "")
      .replace(/^\s*[-*+]\s+/gm, "")
      .replace(/^\s*\d+\.\s+/gm, "")
      .trim();
  }

  function formatMarkdownLite(text) {
    // Escape HTML first to prevent arbitrary HTML execution
    let html = escapeHtml(String(text || ""));
    html = html.replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>");
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    html = html.replace(/\n/g, "<br>");
    return html;
  }

  function truncate(text, length) {
    const val = String(text || "");
    return val.length <= length ? val : val.slice(0, length).trimEnd() + "…";
  }

  /* ---------------------------------------------------------
     EVENT BINDINGS & INITIALIZATION
     --------------------------------------------------------- */

  function init() {
    loadPreferences();

    // 1. Initial profile fetch from server
    fetchUserProfile();

    // 2. Form submission
    const form = $("#repo-form");
    if (form) {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        scanRepository();
      });
    }

    const scanBtn = $("#scan-button");
    if (scanBtn) {
      scanBtn.addEventListener("click", (e) => {
        e.preventDefault();
        scanRepository();
      });
    }

    // 3. Learning mode selector buttons
    const btnModeA = $("#mode-stage-a-btn");
    const btnModeB = $("#mode-stage-b-btn");
    const switchToA = $("#switch-to-stage-a-btn");

    if (btnModeA) {
      btnModeA.addEventListener("click", () => {
        if (state.loading) return;
        playSfx("select");
        state.learningMode = "A";
        state.selectedIssue = null;
        state.activeQuest = null;
        state.questError = null;
        updateLearningModeUI();
        if (state.repositoryUrl) scanRepository(state.repositoryUrl);
      });
    }

    if (btnModeB) {
      btnModeB.addEventListener("click", () => {
        if (state.loading) return;
        playSfx("select");
        state.learningMode = "B";
        state.selectedIssue = null;
        state.activeQuest = null;
        state.questError = null;
        updateLearningModeUI();
        if (state.repositoryUrl) scanRepository(state.repositoryUrl);
      });
    }

    if (switchToA) {
      switchToA.addEventListener("click", () => {
        if (state.loading) return;
        playSfx("select");
        state.learningMode = "A";
        state.selectedIssue = null;
        state.activeQuest = null;
        state.questError = null;
        updateLearningModeUI();
        if (state.repositoryUrl) scanRepository(state.repositoryUrl);
      });
    }

    // 4. Sample repo button (Pallets/Flask)
    const demoBtn = $("#quick-demo-btn");
    if (demoBtn) {
      demoBtn.addEventListener("click", () => {
        if (state.loading) return;
        playSfx("radar");
        const repoInput = $("#repo-url");
        if (repoInput) repoInput.value = "https://github.com/pallets/flask";
        scanRepository("https://github.com/pallets/flask");
      });
    }

    // 5. Developer class selection
    $$(".class-card").forEach((card) => {
      card.addEventListener("click", () => {
        const clsId = card.dataset.class;
        if (CLASSES[clsId]) {
          state.playerClass = clsId;
          playSfx("select");
          savePreferences();
          updateStats();
          showMessage(`Class aligned: ${CLASSES[clsId].name}!`, "info");
        }
      });
    });

    // 6. Region node filtering
    $$(".region-node").forEach((node) => {
      node.addEventListener("click", () => {
        const regionId = node.dataset.region;
        playSfx("node");
        if (state.activeRegionFilter === regionId) {
          state.activeRegionFilter = null;
          $$(".region-node").forEach(n => n.classList.remove("active"));
          const rf = $("#quest-filter");
          if (rf) rf.textContent = "ALL REGIONS";
        } else {
          state.activeRegionFilter = regionId;
          $$(".region-node").forEach(n => n.classList.remove("active"));
          node.classList.add("active");
          const rf = $("#quest-filter");
          if (rf) rf.textContent = node.querySelector(".node-title")?.textContent || regionId.toUpperCase();
        }
        renderQuestList();
      });

      node.addEventListener("mouseenter", () => {
        const lore = node.dataset.lore;
        const regionMsg = $("#region-message");
        const title = node.querySelector(".node-title")?.textContent || "";
        if (lore && regionMsg) {
          regionMsg.innerHTML = `<strong>${title}:</strong> ${lore}`;
        }
      });

      node.addEventListener("mouseleave", () => {
        updateWorldState();
      });
    });

    // 7. SFX toggle
    const sfxBtn = $("#sfx-toggle");
    if (sfxBtn) {
      sfxBtn.classList.toggle("muted", !state.sfxEnabled);
      sfxBtn.textContent = state.sfxEnabled ? "🔊 SFX: ON" : "🔇 SFX: OFF";
      sfxBtn.addEventListener("click", () => {
        state.sfxEnabled = !state.sfxEnabled;
        sfxBtn.classList.toggle("muted", !state.sfxEnabled);
        sfxBtn.textContent = state.sfxEnabled ? "🔊 SFX: ON" : "🔇 SFX: OFF";
        if (state.sfxEnabled) playSfx("click");
        savePreferences();
      });
    }

    // 8. Explain & Hint buttons in NYX panel
    const expBtn = $("#explain-button");
    if (expBtn) {
      expBtn.addEventListener("click", () => {
        if (!state.activeQuest) return;
        playSfx("nyx");
        const compDial = $("#companion-dialogue");
        if (compDial) {
          compDial.innerHTML = `<strong>NYX DEBRIEF:</strong> ${formatMarkdownLite(state.activeQuest.explanation || state.activeQuest.body)}`;
        }
      });
    }

    const hntBtn = $("#hint-button");
    if (hntBtn) {
      hntBtn.addEventListener("click", () => {
        playSfx("nyx");
        const hintsBox = $(".hints-section");
        if (hintsBox) {
          hintsBox.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      });
    }

    // 9. NPC Dialogues & Modal
    const NPC_DATA = {
      nyx: {
        name: "NYX",
        role: "AI COMPANION · TACTICAL ANALYST",
        avatar: "🧙‍♀️",
        speech: `<p>“I study syntax shadows and inspect bytecode anomalies. In the GitVerse, bugs are not mere errors — they are corrupted bosses waiting for a worthy investigator.</p><p>Consult me anytime during your quest for progressive hints or issue deconstruction!”</p>`
      },
      merge_conflict: {
        name: "THE MERGE CONFLICT",
        role: "ANCIENT ANTAGONIST · FINAL BOSS",
        avatar: "⚔️",
        speech: `<p><code>&lt;&lt;&lt;&lt;&lt;&lt;&lt; HEAD: You thought this was resolved.<br>=======<br>&gt;&gt;&gt;&gt;&gt;&gt;&gt; main: I have festered since Year 100.</code></p><p>“I am not evil — just unresolved. A PR opened eons ago that gained sentience. I do not wish to destroy the GitVerse... I just want to be merged.”</p>`
      },
      aria: {
        name: "ARIA",
        role: "DEPLOYER GUIDE · SHIP CAPTAIN",
        avatar: "🏹",
        speech: `<p>“Ship captain of the GitVerse! I keep our deployment pipelines green and ship artifacts to edge sectors. Chaos stresses me out, but we handle it anyway.</p><p>Be careful when venturing into the Bug Swamp — uncaught exceptions lurk in the murk!”</p>`
      },
      linus: {
        name: "LINUS",
        role: "LEGENDARY NPC · ANCIENT COMMITTER",
        avatar: "👁️",
        speech: `<p>“Fellow developer, I've been watching your commit graph. Every PR you merged, every late-night deploy — they weren't just work. They were training.</p><p>In the GitVerse, your code has weight. Your consistency has power. Those 3,000 commits? They forged a warrior.”</p>`
      },
      gemma: {
        name: "GEMMA",
        role: "HEALER NPC · CODE REVIEWER",
        avatar: "✨",
        speech: `<p>“Meticulous, kind, never harsh. I review every PR without exception now to prevent anomalies.</p><p>Write clean diffs and take your time; quality code heals the realm.”</p>`
      }
    };

    const modal = $("#npc-dialogue-modal");
    const modalAvatar = $("#modal-npc-avatar");
    const modalName = $("#modal-npc-name");
    const modalRole = $("#modal-npc-role");
    const modalSpeech = $("#modal-npc-speech");
    const closeModal = () => { if (modal) modal.hidden = true; };

    $$("[data-npc]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const npcKey = btn.dataset.npc;
        const npc = NPC_DATA[npcKey];
        if (npc && modal) {
          playSfx("nyx");
          if (modalAvatar) modalAvatar.textContent = npc.avatar;
          if (modalName) modalName.textContent = npc.name;
          if (modalRole) modalRole.textContent = npc.role;
          if (modalSpeech) modalSpeech.innerHTML = npc.speech;
          modal.hidden = false;
        }
      });
    });

    const closeBtn = $("#modal-close-btn");
    const backdrop = $("#npc-modal-close-backdrop");
    if (closeBtn) closeBtn.addEventListener("click", closeModal);
    if (backdrop) backdrop.addEventListener("click", closeModal);
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && modal && !modal.hidden) closeModal();
    });

    // 10. Linus Wisdom Button
    const LINUS_WISDOMS = [
      "“Fellow developer, every PR you merged, every bug you squashed — they were training. In the GitVerse, your consistency has power.”",
      "“Talk is cheap. Show me the code.”",
      "“That streak? It's not just a number on a graph. It's a legendary buff that fuels your spells.”",
      "“Bad programmers worry about the code. Good programmers worry about data structures and their relationships.”",
      "“A git commit is a promise to the future. Make your messages worthy of an epic chronicle.”"
    ];
    let wisdomIndex = 0;
    const wisdomBtn = $("#wisdom-btn");
    const ancientQuote = $("#ancient-quote");
    if (wisdomBtn && ancientQuote) {
      wisdomBtn.addEventListener("click", () => {
        playSfx("check");
        wisdomIndex = (wisdomIndex + 1) % LINUS_WISDOMS.length;
        ancientQuote.innerHTML = `<em>${LINUS_WISDOMS[wisdomIndex]}</em>`;
      });
    }

    // 11. Initial render
    renderAll();

    // Query parameter auto-scan: ?repo=https://github.com/owner/repo
    try {
      const params = new URLSearchParams(window.location.search);
      const repo = params.get("repo");
      if (repo) {
        const input = $("#repo-url");
        if (input) input.value = repo;
        scanRepository(repo);
      }
    } catch {
      // Ignore URL param issues
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Expose API client and state globally for testing and manual debugging
  window.GitQuest = {
    apiClient,
    state,
    scanRepository,
    selectIssue,
    unlockHintTier,
    submitQuestCompletion,
    fetchUserProfile,
    renderAll
  };
})();
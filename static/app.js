/* =========================================================
   BUG DUNGEON — FRONTEND CONTROLLER
   static/app.js
   ========================================================= */

(() => {
  "use strict";

  /* ---------------------------------------------------------
     STATE
     --------------------------------------------------------- */

  const CLASSES = {
    paladin: { id: "paladin", name: "TypeScript Paladin", short: "TS PALADIN", icon: '<svg class="svg-icon"><use href="#icon-shield"></use></svg>', sub: "Type-Safe Citadel" },
    rogue: { id: "rogue", name: "JavaScript Rogue", short: "JS ROGUE", icon: '<svg class="svg-icon"><use href="#icon-rogue"></use></svg>', sub: "Async Shadow" },
    sorcerer: { id: "sorcerer", name: "Python Sorcerer", short: "PY SORCERER", icon: '<svg class="svg-icon"><use href="#icon-sorcerer"></use></svg>', sub: "Data Alchemist" },
    artificer: { id: "artificer", name: "Rust Artificer", short: "RS ARTIFICER", icon: '<svg class="svg-icon"><use href="#icon-artificer"></use></svg>', sub: "Memory Forge" }
  };

  const state = {
    repositoryUrl: "",
    repository: null,
    quests: [],
    selectedQuest: null,
    currentStep: 0,
    xp: 0,
    completed: 0,
    badges: [],
    completedQuestIds: [],
    activeRegionFilter: null,
    playerClass: "paladin",
    sfxEnabled: true,
    scanned: false,
    loading: false
  };

  /* ---------------------------------------------------------
     PERSISTENCE & 8-BIT AUDIO SYNTHESIZER
     --------------------------------------------------------- */

  const STORAGE_KEY = "bug_dungeon_player_v1";

  function loadPlayerState() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (typeof parsed.xp === "number") state.xp = parsed.xp;
        if (typeof parsed.completed === "number") state.completed = parsed.completed;
        if (Array.isArray(parsed.badges)) state.badges = parsed.badges;
        if (Array.isArray(parsed.completedQuestIds)) state.completedQuestIds = parsed.completedQuestIds;
        if (typeof parsed.sfxEnabled === "boolean") state.sfxEnabled = parsed.sfxEnabled;
        if (parsed.playerClass && CLASSES[parsed.playerClass]) state.playerClass = parsed.playerClass;
      }
    } catch (e) {
      console.warn("Could not load player profile from storage", e);
    }
  }

  function savePlayerState() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        xp: state.xp,
        completed: state.completed,
        badges: state.badges,
        completedQuestIds: state.completedQuestIds || [],
        playerClass: state.playerClass,
        sfxEnabled: state.sfxEnabled
      }));
    } catch (e) {
      console.warn("Could not save player profile to storage", e);
    }
  }

  let audioCtx = null;
  function getAudioContext() {
    if (!audioCtx) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (AudioContextClass) {
        audioCtx = new AudioContextClass();
      }
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
      } else if (type === "transmission" || type === "nyx") {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sawtooth";
        osc.frequency.setValueAtTime(320, now);
        osc.frequency.exponentialRampToValueAtTime(640, now + 0.05);
        osc.frequency.exponentialRampToValueAtTime(480, now + 0.1);
        gain.gain.setValueAtTime(0.05, now);
        gain.gain.linearRampToValueAtTime(0.001, now + 0.12);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now);
        osc.stop(now + 0.12);
      }
    } catch (e) {
      // Audio policy catch
    }
  }

  /* ---------------------------------------------------------
     DOM HELPERS
     --------------------------------------------------------- */

  const $ = (selector) => document.querySelector(selector);

  const $$ = (selector) => Array.from(document.querySelectorAll(selector));

  function escapeHtml(value) {
    if (value === null || value === undefined) return "";

    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function getRepositoryUrl() {
    const input =
      $("#repository-url") ||
      $("#repo-url") ||
      $('input[type="url"]') ||
      $('input[placeholder*="github" i]');

    return input ? input.value.trim() : "";
  }

  function setRepositoryUrl(value) {
    const input =
      $("#repository-url") ||
      $("#repo-url") ||
      $('input[type="url"]') ||
      $('input[placeholder*="github" i]');

    if (input) {
      input.value = value || "";
    }
  }

  /* ---------------------------------------------------------
     NOTIFICATIONS
     --------------------------------------------------------- */

  function showMessage(message, type = "info") {
    let container = $("#toast-container");

    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.style.position = "fixed";
      container.style.right = "24px";
      container.style.bottom = "24px";
      container.style.zIndex = "9999";
      container.style.display = "flex";
      container.style.flexDirection = "column";
      container.style.gap = "10px";
      document.body.appendChild(container);
    }

    const toast = document.createElement("div");

    toast.className = `toast toast-${type}`;
    toast.innerHTML = message;

    toast.style.padding = "12px 16px";
    toast.style.border = "1px solid rgba(255,255,255,.15)";
    toast.style.borderRadius = "10px";
    toast.style.background = "rgba(18, 12, 31, .96)";
    toast.style.color = "#fff";
    toast.style.boxShadow = "0 10px 35px rgba(0,0,0,.35)";
    toast.style.maxWidth = "380px";
    toast.style.fontSize = "14px";

    if (type === "error") {
      toast.style.borderColor = "rgba(255, 100, 130, .55)";
    }

    if (type === "success") {
      toast.style.borderColor = "rgba(100, 255, 180, .55)";
    }

    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(8px)";
      toast.style.transition = "all .25s ease";

      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }

  /* ---------------------------------------------------------
     LOADING
     --------------------------------------------------------- */

  function setLoading(isLoading) {
    state.loading = isLoading;

    const buttons = $$(
      'button[type="submit"], button[data-action="scan"], #scan-repository, #scan-btn'
    );

    buttons.forEach((button) => {
      button.disabled = isLoading;

      if (isLoading) {
        button.dataset.originalText = button.textContent;
        button.textContent = "Scanning...";
      } else if (button.dataset.originalText) {
        button.textContent = button.dataset.originalText;
        delete button.dataset.originalText;
      }
    });
  }

  /* ---------------------------------------------------------
     API
     --------------------------------------------------------- */

  async function apiRequest(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      }
    });

    const contentType = response.headers.get("content-type") || "";

    let data;

    if (contentType.includes("application/json")) {
      data = await response.json();
    } else {
      const text = await response.text();
      data = {
        message: text
      };
    }

    if (!response.ok) {
      const errorMessage =
        data?.error ||
        data?.message ||
        `Request failed with status ${response.status}`;

      throw new Error(errorMessage);
    }

    return data;
  }

  /* ---------------------------------------------------------
     REPOSITORY SCAN
     --------------------------------------------------------- */

  async function scanRepository(url) {
    const repositoryUrl = (url || getRepositoryUrl()).trim();

    if (!repositoryUrl) {
      showMessage("Please enter a GitHub repository URL.", "error");
      return;
    }

    if (
      !repositoryUrl.startsWith("https://github.com/") &&
      !repositoryUrl.startsWith("http://github.com/")
    ) {
      showMessage("Please enter a valid GitHub repository URL.", "error");
      return;
    }

    state.repositoryUrl = repositoryUrl;

    setLoading(true);

    try {
      /*
       * Backend contract:
       *
       * POST /api/quests
       *
       * {
       *   "repository_url": "https://github.com/user/repo"
       * }
       *
       * The backend should return an object containing an
       * issues/quests array.
       */

      const data = await apiRequest("/api/quests", {
        method: "POST",
        body: JSON.stringify({
          repository_url: repositoryUrl,
          repo_url: repositoryUrl,
          url: repositoryUrl
        })
      });

      const quests =
        data?.quests ||
        data?.issues ||
        data?.data?.quests ||
        data?.data?.issues ||
        [];

      state.quests = normalizeQuests(quests);

      state.repository =
        data?.repository ||
        data?.repo ||
        parseRepositoryUrl(repositoryUrl);

      state.scanned = true;

      if (state.quests.length === 0) {
        showMessage(
          "Repository scanned, but no quests/issues were found.",
          "info"
        );
      } else {
        showMessage(
          `${state.quests.length} quest${state.quests.length === 1 ? "" : "s"} discovered!`,
          "success"
        );
      }

      renderAll();
    } catch (error) {
      console.error("Repository scan failed:", error);

      showMessage(
        error.message ||
        "Repository scan failed. Check that the repository is public and the backend is running.",
        "error"
      );

      showScanError(error.message);
    } finally {
      setLoading(false);
    }
  }

  function parseRepositoryUrl(url) {
    try {
      const parsed = new URL(url);

      const parts = parsed.pathname
        .split("/")
        .filter(Boolean);

      return {
        owner: parts[0] || "",
        name: (parts[1] || "").replace(/\.git$/, ""),
        url
      };
    } catch {
      return {
        owner: "",
        name: "",
        url
      };
    }
  }

  /* ---------------------------------------------------------
     QUEST NORMALIZATION
     --------------------------------------------------------- */

  function normalizeQuests(items) {
    if (!items) return [];

    let list = items;
    if (!Array.isArray(list)) {
      if (typeof list === "object" && (list.quest_id || list.id || list.quest_title || list.title)) {
        list = [list];
      } else {
        return [];
      }
    }

    return list.map((item, index) => {
      // Tags / Labels
      let labels = [];
      if (Array.isArray(item.tags)) {
        labels = item.tags.map((t) => (typeof t === "string" ? t : t?.name || "")).filter(Boolean);
      } else if (Array.isArray(item.labels)) {
        labels = item.labels.map((l) => (typeof l === "string" ? l : l?.name || "")).filter(Boolean);
      }

      const questId = item.quest_id || item.id || `quest-${index}`;
      const title = item.quest_title || item.title || item.name || `Quest ${index + 1}`;
      const tagline = item.tagline || "";
      const category = item.category || "Dungeon Quest";
      const estimatedTime = item.estimated_time_minutes || item.estimated_time || null;

      // Briefing details
      let loreIntro = "";
      let techSummary = "";
      if (item.briefing && typeof item.briefing === "object") {
        loreIntro = item.briefing.lore_intro || "";
        techSummary = item.briefing.technical_summary || "";
      } else if (typeof item.briefing === "string") {
        techSummary = item.briefing;
      }

      const body =
        techSummary ||
        item.body ||
        item.description ||
        tagline ||
        loreIntro ||
        "No description provided.";

      // Quest number extraction
      let number = item.number ?? item.issue_number;
      if (!number && questId) {
        const numMatch = String(questId).match(/\d+$/);
        number = numMatch ? numMatch[0] : String(questId).replace(/^quest_/, "");
      }
      if (!number) number = index + 1;

      const rawDiff = String(item.difficulty || "").toLowerCase();
      let difficulty = item.difficulty;
      if (!difficulty) {
        difficulty = inferDifficulty(item, labels);
      }

      const xp = Number(item.xp_reward ?? item.xp ?? calculateXp(difficulty));

      // Objectives -> Steps mapping
      let steps = [];
      if (Array.isArray(item.objectives) && item.objectives.length) {
        steps = item.objectives.map((obj, i) => ({
          id: obj.step || i + 1,
          title: obj.title || `Objective ${i + 1}`,
          description: obj.instruction || obj.description || "",
          instruction: obj.instruction || obj.description || ""
        }));
      } else if (Array.isArray(item.steps) && item.steps.length) {
        steps = item.steps.map((st, i) => ({
          id: st.id || st.step || i + 1,
          title: st.title || `Step ${i + 1}`,
          description: st.instruction || st.description || "",
          instruction: st.instruction || st.description || ""
        }));
      } else {
        steps = createDefaultSteps(item, title);
      }

      // Hints
      let rawHints = [];
      if (Array.isArray(item.hints)) {
        rawHints = item.hints;
      }

      const formattedHints = rawHints.map((h, i) => {
        if (typeof h === "string") return h;
        if (typeof h === "object" && h !== null) {
          const tierStr = h.tier ? `[${h.tier}] ` : "";
          const costStr = h.xp_cost ? ` (Cost: ${h.xp_cost} XP)` : "";
          return `${tierStr}${h.hint || ""}${costStr}`;
        }
        return `Hint ${i + 1} for ${title}`;
      });

      // Verification checklist
      const verificationChecklist = Array.isArray(item.verification_checklist)
        ? item.verification_checklist
        : (Array.isArray(item.checklist) ? item.checklist : []);

      // Sector landmark auto-assignment
      let region = item.region || "";
      let regionName = item.region_name || "";
      const textToClassify = [
        title,
        category,
        tagline,
        techSummary,
        body,
        ...labels
      ].join(" ").toLowerCase();

      if (!region) {
        if (/doc|documentation|guide|manual|archive|legacy|deprecated|discovery|tutorial|reference/.test(textToClassify)) {
          region = "archive";
          regionName = "Deprecated Archive";
        } else if (/bug|fix|error|crash|fault|fail|leak|broken|problem|vulnerability|swamp/.test(textToClassify)) {
          region = "swamp";
          regionName = "Bug Swamp";
        } else if (/pr|pull request|first issue|good first|novice|beginner|starter|plaza|community/.test(textToClassify)) {
          region = "plaza";
          regionName = "Pull Request Plaza";
        } else if (/core|architecture|refactor|tree|root|engine|perf|performance|context|realm|system/.test(textToClassify)) {
          region = "core";
          regionName = "Main Branch World Tree";
        } else if (/feat|feature|add|new|enhancement|forest|gateway|forge|stream/.test(textToClassify)) {
          region = "forest";
          regionName = "Feature Forest";
        } else {
          const fallbackRegions = [
            { id: "forest", name: "Feature Forest" },
            { id: "core", name: "Main Branch World Tree" },
            { id: "plaza", name: "Pull Request Plaza" },
            { id: "swamp", name: "Bug Swamp" },
            { id: "archive", name: "Deprecated Archive" }
          ];
          const choice = fallbackRegions[index % fallbackRegions.length];
          region = choice.id;
          regionName = choice.name;
        }
      }

      const isCompleted = state.completedQuestIds?.includes(questId) || item.status === "completed";

      return {
        ...item,
        id: questId,
        quest_id: questId,
        quest_title: title,
        title,
        tagline,
        category,
        estimated_time_minutes: estimatedTime,
        number,
        body,
        description: body,
        lore_intro: loreIntro,
        technical_summary: techSummary,
        briefing: item.briefing,
        labels,
        tags: labels,
        region,
        region_name: regionName,
        difficulty,
        xp,
        xp_reward: xp,
        status: isCompleted ? "completed" : (item.status || "available"),
        raw_hints: rawHints,
        hints: formattedHints.length ? formattedHints : [
          `Analyze the objectives for "${title}".`,
          `Locate the relevant source files mentioned in the directive.`,
          `Check syntax and verify against the checklist before completing.`
        ],
        steps,
        objectives: steps,
        verification_checklist: verificationChecklist,
        url: item.html_url || item.url || ""
      };
    });
  }

  function inferDifficulty(item, labels = []) {
    const text = [
      item.title,
      item.body,
      ...labels
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    if (
      text.includes("critical") ||
      text.includes("security") ||
      text.includes("complex") ||
      text.includes("architecture")
    ) {
      return "hard";
    }

    if (
      text.includes("medium") ||
      text.includes("feature") ||
      text.includes("refactor")
    ) {
      return "medium";
    }

    return "easy";
  }

  function calculateXp(difficulty) {
    switch (String(difficulty).toLowerCase()) {
      case "hard":
      case "legendary":
        return 300;

      case "medium":
        return 200;

      default:
        return 100;
    }
  }

  function createDefaultSteps(issue, title) {
    return [
      {
        title: "Read the quest",
        description:
          issue.body ||
          `Study the issue "${title}" and understand what is being requested.`
      },
      {
        title: "Locate the source",
        description:
          "Find the relevant file, function, component, or module responsible for the behavior."
      },
      {
        title: "Investigate the cause",
        description:
          "Trace the existing behavior and determine why the issue occurs."
      },
      {
        title: "Plan the fix",
        description:
          "Choose a small, focused change that addresses the root cause."
      },
      {
        title: "Verify the solution",
        description:
          "Run the appropriate tests or manually verify that the expected behavior works."
      }
    ];
  }

  /* ---------------------------------------------------------
     RENDERING
     --------------------------------------------------------- */

  function renderAll() {
    renderQuestList();
    renderSelectedQuest();
    updateStats();
    updateWorldState();
  }

  function findQuestContainer() {
    return (
      $("#issues-list") ||
      $("#quest-list") ||
      $("#quests") ||
      $(".issues-list") ||
      $(".quest-list") ||
      $('[data-region="quests"]')
    );
  }
  function renderQuestList() {
    const container = findQuestContainer();

    if (!container) return;

    if (!state.scanned) {
      container.innerHTML = `
                <div class="empty-state dungeon-panel">
                  <div class="empty-dungeon-art" aria-hidden="true">
                    <span class="empty-torch"><svg class="svg-icon"><use href="#icon-flame"></use></svg></span>
                    <div class="empty-gate"><svg class="svg-icon"><use href="#icon-gate"></use></svg></div>
                    <span class="empty-torch"><svg class="svg-icon"><use href="#icon-flame"></use></svg></span>
                  </div>
                  <h3>Your next adventure awaits</h3>
                  <p>Scan a repository to reveal open issues, clues, and quests.</p>
                  <span class="empty-code mono">AWAITING_REPOSITORY_INPUT_</span>
                </div>
            `;
      return;
    }

    if (state.quests.length === 0) {
      container.innerHTML = `
                <div class="empty-state dungeon-panel">
                  <div class="empty-dungeon-art" aria-hidden="true">
                    <span class="empty-torch"><svg class="svg-icon"><use href="#icon-flame"></use></svg></span>
                    <div class="empty-gate"><svg class="svg-icon"><use href="#icon-gate"></use></svg></div>
                    <span class="empty-torch"><svg class="svg-icon"><use href="#icon-flame"></use></svg></span>
                  </div>
                  <h3>No quests found</h3>
                  <p>This repository did not return any open issues.</p>
                  <span class="empty-code mono">0_ANOMALIES_DETECTED</span>
                </div>
            `;
      return;
    }

    const visibleQuests = state.activeRegionFilter
      ? state.quests.filter((q) => q.region === state.activeRegionFilter)
      : state.quests;

    if (visibleQuests.length === 0) {
      container.innerHTML = `
                <div class="empty-state dungeon-panel">
                  <div class="empty-dungeon-art" aria-hidden="true">
                    <span class="empty-torch"><svg class="svg-icon"><use href="#icon-flame"></use></svg></span>
                    <div class="empty-gate"><svg class="svg-icon"><use href="#icon-gate"></use></svg></div>
                    <span class="empty-torch"><svg class="svg-icon"><use href="#icon-flame"></use></svg></span>
                  </div>
                  <h3>No quests in this sector</h3>
                  <p>There are no open quests assigned to this region.</p>
                  <span class="empty-code mono">SECTOR_CLEAR</span>
                </div>
            `;
      return;
    }

    container.innerHTML = visibleQuests
      .map((quest) => {
        const selected = state.selectedQuest?.id === quest.id;
        const completed = quest.status === "completed";
        const difficultyLower = String(quest.difficulty || "medium").toLowerCase();
        const isGood = difficultyLower === "easy" || difficultyLower === "novice";

        return `
                    <article
                        class="issue-card quest-card ${selected ? "selected" : ""} ${completed ? "cleared completed" : ""}"
                        data-quest-id="${escapeHtml(String(quest.id))}"
                        tabindex="0"
                        role="button"
                    >
                        <div class="issue-top quest-card-top">
                            <span class="issue-number quest-number mono">#${escapeHtml(quest.number)}</span>
                            <span class="issue-label quest-difficulty ${isGood ? "good" : ""} difficulty-${escapeHtml(difficultyLower)}">
                                ${escapeHtml(quest.category ? quest.category + " · " : "")}${escapeHtml(String(quest.difficulty || "MEDIUM").toUpperCase())} · +${quest.xp} XP
                            </span>
                        </div>

                        <h3 class="issue-title">${escapeHtml(quest.title)}</h3>

                        <p class="issue-body quest-description">
                            ${quest.tagline
                              ? `<strong>${escapeHtml(quest.tagline)}</strong><br><span class="muted">${escapeHtml(truncate(quest.technical_summary || quest.body, 130))}</span>`
                              : `${escapeHtml(truncate(stripMarkdown(quest.body), 160))}`
                            }
                        </p>

                        <div class="issue-footer quest-card-bottom">
                            <div class="labels">
                                <span class="sector-chip sector-${escapeHtml(quest.region || "core")}">${escapeHtml(quest.region_name || quest.region || "Sector")}</span>
                                ${quest.labels && quest.labels.length
                                  ? quest.labels.slice(0, 2).map((l) => `<span class="label-chip">${escapeHtml(l)}</span>`).join("")
                                  : ""
                                }
                                ${quest.estimated_time_minutes
                                  ? `<span class="label-chip mono" style="color:#6de8ef;border-color:rgba(109,232,239,0.3);"><svg class="svg-icon svg-tiny"><use href="#icon-clock"></use></svg>${escapeHtml(quest.estimated_time_minutes)}m</span>`
                                  : ""
                                }
                            </div>
                            <span class="select-quest mono">
                                ${completed ? '<svg class="svg-icon svg-tiny" style="color:var(--emerald);"><use href="#icon-check"></use></svg> CLEARED' : (selected ? '<svg class="svg-icon svg-tiny" style="color:var(--gold);"><use href="#icon-sword"></use></svg> INVESTIGATING' : "SELECT QUEST &rarr;")}
                            </span>
                        </div>
                    </article>
                `;
      })
      .join("");

    $$(".quest-card, .issue-card").forEach((card) => {
      const questId = card.dataset.questId;

      card.addEventListener("click", () => {
        selectQuestById(questId);
      });

      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectQuestById(questId);
        }
      });
    });
  }

  function selectQuestById(id) {
    const quest = state.quests.find((q) => String(q.id) === String(id));
    if (!quest) return;
    state.selectedQuest = quest;
    state.currentStep = 0;
    playSfx("select");
    renderAll();
    const detail = $(".briefing-panel") || $("#quest-detail") || $("#quest-panel") || $(".quest-detail");
    if (detail) detail.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function renderSelectedQuest() {
    const quest = state.selectedQuest;

    // 1. Update briefing panel elements in index.html if present
    const briefingText = $("#briefing-text");
    const companionDialogue = $("#companion-dialogue");
    const explainButton = $("#explain-button");
    const hintButton = $("#hint-button");
    const investigationSlot = $("#investigation-slot");
    const bossAlertBanner = $("#boss-alert-banner");

    if (!quest) {
      if (bossAlertBanner) bossAlertBanner.hidden = true;
      if (briefingText) {
        briefingText.textContent = "Your companion will brief you once a quest is selected.";
      }
      if (companionDialogue) {
        companionDialogue.textContent = "“A good investigator studies the clues before attacking the boss.”";
      }
      if (explainButton) explainButton.disabled = true;
      if (hintButton) hintButton.disabled = true;
      if (investigationSlot) investigationSlot.innerHTML = "";
    } else {
      if (bossAlertBanner) {
        const isBoss = (quest.region === "swamp") || /boss|merge|conflict|critical|security|fatal/i.test(quest.title + " " + (quest.category || ""));
        bossAlertBanner.hidden = !isBoss;
      }
      if (briefingText) {
        if (quest.lore_intro || quest.technical_summary) {
          briefingText.innerHTML = `
            <strong>${escapeHtml(quest.title)}</strong>
            ${quest.lore_intro ? `<p style="margin: 6px 0; color: #d6cce7; font-style: italic;">“${escapeHtml(quest.lore_intro)}”</p>` : ""}
            ${quest.technical_summary ? `<p style="margin: 4px 0; font-size: 11px;"><strong>DIRECTIVE:</strong> ${escapeHtml(quest.technical_summary)}</p>` : ""}
          `;
        } else {
          briefingText.innerHTML = `<strong>Quest #${escapeHtml(quest.number)}:</strong> ${escapeHtml(quest.title)} <br><span class="muted">${escapeHtml(truncate(stripMarkdown(quest.body), 130))}</span>`;
        }
      }

      if (companionDialogue && !companionDialogue.dataset.hasCustomMessage) {
        const loreQuote = quest.lore_intro || quest.tagline;
        companionDialogue.innerHTML = loreQuote
          ? `“NYX: ${escapeHtml(loreQuote)}”`
          : `“Quest <strong>#${escapeHtml(quest.number)}</strong> active (${escapeHtml(quest.difficulty.toUpperCase())} · +${quest.xp} XP). Consult NYX for hints or an explanation.”`;
      }
      if (explainButton) explainButton.disabled = false;
      if (hintButton) hintButton.disabled = false;

      const steps = quest.steps || [];

      if (investigationSlot) {
        const isAllDone = quest.status === "completed";
        const hasChecklist = quest.verification_checklist && quest.verification_checklist.length > 0;

        investigationSlot.innerHTML = `
          <div class="steps">
            <div class="steps-title mono">
              OBJECTIVES (${isAllDone ? steps.length : state.currentStep + 1}/${steps.length})
            </div>

            ${steps.map((step, index) => {
              const isDone = index < state.currentStep || isAllDone;
              const isCurrent = index === state.currentStep && !isAllDone;

              return `
                <label class="step-item ${isDone ? "done" : ""} ${isCurrent ? "current" : ""}">
                  <input
                    type="checkbox"
                    ${isDone ? "checked" : ""}
                    data-step-index="${index}"
                    ${isAllDone ? "disabled" : ""}
                  >
                  <span>
                    <strong>${escapeHtml(step.title || `Step ${index + 1}`)}:</strong>
                    ${escapeHtml(step.description || step.instruction || "")}
                  </span>
                </label>
              `;
            }).join("")}

            ${hasChecklist ? `
              <div class="verification-container" style="margin-top: 12px; padding: 10px 12px; border: 1px dashed rgba(114, 245, 189, 0.35); border-radius: 8px; background: rgba(114, 245, 189, 0.04);">
                <div class="steps-title mono" style="color: var(--green); margin-bottom: 6px;">VERIFICATION CHECKLIST</div>
                ${quest.verification_checklist.map((v, vi) => `
                  <label class="step-item" style="margin-top: 5px;">
                    <input type="checkbox" class="verify-check" data-verify-index="${vi}" ${isAllDone ? "checked disabled" : ""}>
                    <span style="color: #bbf7d0; font-size: 11px;">${escapeHtml(v)}</span>
                  </label>
                `).join("")}
              </div>
            ` : ""}

            <button
              type="button"
              class="button button-primary complete-button"
              id="complete-quest"
              ${isAllDone ? "disabled" : ""}
            >
              ${isAllDone ? '<svg class="svg-icon svg-tiny" style="color:var(--emerald);"><use href="#icon-check"></use></svg> Quest Cleared' : (state.currentStep >= steps.length - 1 ? '<svg class="svg-icon svg-tiny"><use href="#icon-sword"></use></svg> Complete Quest' : "Advance Objective &rarr;")}
            </button>
          </div>
        `;

        investigationSlot.querySelectorAll('input[type="checkbox"][data-step-index]').forEach((checkbox) => {
          checkbox.addEventListener("change", (e) => {
            const stepIdx = Number(e.target.dataset.stepIndex);
            if (e.target.checked) {
              state.currentStep = Math.min(stepIdx + 1, steps.length - 1);
            } else {
              state.currentStep = Math.max(stepIdx, 0);
            }
            renderSelectedQuest();
            renderQuestList();
            updateStats();
          });
        });

        const completeBtn = investigationSlot.querySelector("#complete-quest");
        if (completeBtn) {
          completeBtn.addEventListener("click", () => {
            if (state.currentStep < steps.length - 1) {
              state.currentStep += 1;
              renderSelectedQuest();
              renderQuestList();
              updateStats();
            } else {
              completeQuest();
            }
          });
        }
      }
    }

    // 2. Generic container support (#quest-detail / #quest-panel)
    const container =
      $("#quest-detail") ||
      $("#quest-panel") ||
      $(".quest-detail") ||
      $('[data-region="quest-detail"]');

    if (!container) return;

    if (!state.selectedQuest) {
      container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon"><svg class="svg-icon" style="width: 44px; height: 44px; fill: var(--purple);"><use href="#icon-sword"></use></svg></div>
                    <h3>Select a quest</h3>
                    <p>Choose an issue from the dungeon map to begin your investigation.</p>
                </div>
            `;
      return;
    }

    const steps = quest.steps || [];

    container.innerHTML = `
            <div class="quest-detail-header">
                <div>
                    <span class="eyebrow">ACTIVE QUEST</span>
                    <h2>${escapeHtml(quest.title)}</h2>
                </div>

                <div class="quest-xp">
                    +${quest.xp} XP
                </div>
            </div>

            <div class="quest-description">
                ${formatMarkdownLite(quest.body)}
            </div>

            ${quest.url
        ? `
                        <a
                            class="github-link"
                            href="${escapeHtml(quest.url)}"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            Open GitHub issue ↗
                        </a>
                    `
        : ""
      }

            <div class="investigation-section">
                <div class="section-heading">
                    <span>INVESTIGATION</span>
                    <span>
                        ${Math.min(
        state.currentStep + 1,
        steps.length
      )}/${steps.length}
                    </span>
                </div>

                <div class="investigation-steps">
                    ${steps
        .map((step, index) => {
          const isCurrent =
            index === state.currentStep;

          const isComplete =
            index < state.currentStep ||
            quest.status === "completed";

          return `
                                <button
                                    type="button"
                                    class="investigation-step ${isCurrent ? "current" : ""
            } ${isComplete ? "complete" : ""}"
                                    data-step-index="${index}"
                                >
                                    <span class="step-number">
                                        ${isComplete
              ? '<svg class="svg-icon svg-tiny"><use href="#icon-check"></use></svg>'
              : index + 1
            }
                                    </span>

                                    <span class="step-content">
                                        <strong>
                                            ${escapeHtml(
              step.title ||
              `Step ${index + 1}`
            )}
                                        </strong>

                                        <small>
                                            ${escapeHtml(
              step.description ||
              ""
            )}
                                        </small>
                                    </span>
                                </button>
                            `;
        })
        .join("")}
                </div>
            </div>

            <div class="quest-actions">
                ${state.currentStep > 0
        ? `
                            <button
                                type="button"
                                class="secondary-button"
                                id="previous-step"
                            >
                                ← Previous
                            </button>
                        `
        : ""
      }

                ${state.currentStep < steps.length - 1
        ? `
                            <button
                                type="button"
                                class="primary-button"
                                id="next-step"
                            >
                                Continue →
                            </button>
                        `
        : `
                            <button
                                type="button"
                                class="primary-button"
                                id="complete-quest-generic"
                            >
                                <svg class="svg-icon svg-tiny"><use href="#icon-check"></use></svg> Complete quest
                            </button>
                        `
      }

                <button
                    type="button"
                    class="secondary-button"
                    id="request-hint"
                >
                    Ask NYX for a hint
                </button>
            </div>

            <div id="nyx-response" class="nyx-response" hidden></div>
        `;

    $$(".investigation-step").forEach((button) => {
      button.addEventListener("click", () => {
        state.currentStep = Number(
          button.dataset.stepIndex
        );

        renderSelectedQuest();
        renderQuestList();
        updateStats();
      });
    });

    const previousButton = $("#previous-step");
    if (previousButton) {
      previousButton.addEventListener("click", () => {
        if (state.currentStep > 0) {
          state.currentStep -= 1;
          renderSelectedQuest();
          renderQuestList();
          updateStats();
        }
      });
    }

    const nextButton = $("#next-step");
    if (nextButton) {
      nextButton.addEventListener("click", () => {
        if (state.currentStep < steps.length - 1) {
          state.currentStep += 1;
          renderSelectedQuest();
          renderQuestList();
          updateStats();
        }
      });
    }

    const completeGenericBtn = $("#complete-quest-generic");
    if (completeGenericBtn) {
      completeGenericBtn.addEventListener("click", () => {
        completeQuest();
      });
    }

    const hintButtonGeneric = $("#request-hint");
    if (hintButtonGeneric) {
      hintButtonGeneric.addEventListener("click", () => {
        requestHint();
      });
    }
  }

  /* ---------------------------------------------------------
     QUEST ACTIONS
     --------------------------------------------------------- */

  function selectQuest(index) {
    const quest = state.quests[index];

    if (!quest) return;

    state.selectedQuest = quest;

    state.currentStep = 0;

    renderAll();

    const detail =
      $("#quest-detail") ||
      $("#quest-panel") ||
      $(".quest-detail");

    if (detail) {
      detail.scrollIntoView({
        behavior: "smooth",
        block: "nearest"
      });
    }
  }

  function completeQuest() {
    if (!state.selectedQuest) return;

    const quest = state.selectedQuest;

    if (quest.status === "completed") {
      return;
    }

    quest.status = "completed";

    state.completed += 1;
    state.xp += Number(quest.xp) || 0;

    unlockBadges();

    if (!state.completedQuestIds) state.completedQuestIds = [];
    state.completedQuestIds.push(quest.quest_id || quest.id);
    savePlayerState();

    playSfx("complete");

    showMessage(
      `Quest complete! +${quest.xp} XP`,
      "success"
    );

    // Check loot drops milestone
    const newlyUnlockedLoot = LOOT_ITEMS.find((l) => l.threshold === state.completed);
    if (newlyUnlockedLoot) {
      setTimeout(() => {
        playSfx("victory");
        showMessage(`<svg class="svg-icon btn-icon-svg"><use href="#icon-sword"></use></svg> DUNGEON LOOT UNLOCKED: [${newlyUnlockedLoot.name}] (${newlyUnlockedLoot.rarity})!`, "success");
      }, 700);
    }

    renderAll();
  }

  /* ---------------------------------------------------------
     BADGES
     --------------------------------------------------------- */

  function unlockBadges() {
    const badgesToUnlock = [];

    if (
      state.completed >= 1 &&
      !state.badges.includes("FIRST_BLOOD")
    ) {
      badgesToUnlock.push("FIRST_BLOOD");
    }

    if (
      state.completed >= 3 &&
      !state.badges.includes("DUNGEON_CRAWLER")
    ) {
      badgesToUnlock.push("DUNGEON_CRAWLER");
    }

    if (
      state.completed >= 5 &&
      !state.badges.includes("BUG_HUNTER")
    ) {
      badgesToUnlock.push("BUG_HUNTER");
    }

    badgesToUnlock.forEach((badge) => {
      state.badges.push(badge);

      const names = {
        FIRST_BLOOD: "First Blood",
        DUNGEON_CRAWLER: "Dungeon Crawler",
        BUG_HUNTER: "Bug Hunter"
      };

      showMessage(
        `Badge unlocked: ${names[badge]}`,
        "success"
      );
    });
  }

  /* ---------------------------------------------------------
     NYX HINTS
     --------------------------------------------------------- */

  async function requestHint() {
    if (!state.selectedQuest) {
      showMessage(
        "Select a quest before asking NYX for help.",
        "info"
      );
      return;
    }

    const quest = state.selectedQuest;

    const companionStatus = $("#companion-status");
    if (companionStatus) {
      companionStatus.textContent = "NYX is analyzing the quest matrix...";
    }

    const responseContainer = $("#nyx-response");
    if (responseContainer) {
      responseContainer.hidden = false;
      responseContainer.innerHTML = `
                <div class="nyx-loading">
                    NYX is analyzing the dungeon...
                </div>
            `;
    }

    try {
      const currentStep =
        quest.steps?.[state.currentStep] || null;

      const data = await apiRequest("/api/hint", {
        method: "POST",
        body: JSON.stringify({
          repository_url: state.repositoryUrl,
          quest,
          issue: quest,
          step: currentStep,
          step_index: state.currentStep
        })
      });

      const hint =
        data?.hint ||
        data?.message ||
        data?.response ||
        "NYX has no additional hint right now.";

      if (companionStatus) {
        companionStatus.textContent = "Tactical transmission received.";
      }

      displayNyxMessage(hint);
    } catch (error) {
      console.error("Hint request failed:", error);

      const localHint = getLocalHint(
        quest,
        state.currentStep
      );

      if (companionStatus) {
        companionStatus.textContent = "Local offline heuristic used.";
      }

      displayNyxMessage(localHint);
    }
  }

  function getLocalHint(quest, stepIndex) {
    if (Array.isArray(quest.raw_hints) && quest.raw_hints.length) {
      const h = quest.raw_hints[stepIndex] || quest.raw_hints[0];
      if (typeof h === "object" && h !== null) {
        const tier = h.tier ? `Tier: ${h.tier}` : `Level ${h.level || 1}`;
        const cost = h.xp_cost ? ` *(XP Cost: ${h.xp_cost} XP)*` : "";
        return `**[NYX TACTICAL GUIDANCE (${tier})]:**\n\n${h.hint || ""}\n\n${cost}`.trim();
      }
      return String(h);
    }

    if (Array.isArray(quest.hints) && quest.hints.length) {
      return (
        quest.hints[stepIndex] ||
        quest.hints[0]
      );
    }

    const step = quest.steps?.[stepIndex];

    if (!step) {
      return "Inspect the quest objectives and verify the required file locations.";
    }

    const hints = [
      "Review the technical summary and objective instruction carefully.",
      "Locate the source files mentioned in the objective instructions.",
      "Trace the implementation and ensure documentation/code formatting meets standards.",
      "Double check the verification checklist before completing the quest."
    ];

    return hints[
      Math.min(stepIndex, hints.length - 1)
    ];
  }

  /* ---------------------------------------------------------
     NYX EXPLANATION
     --------------------------------------------------------- */

  async function requestExplanation() {
    if (!state.selectedQuest) {
      showMessage(
        "Select a quest first.",
        "info"
      );
      return;
    }

    const quest = state.selectedQuest;

    const companionStatus = $("#companion-status");
    if (companionStatus) {
      companionStatus.textContent = "NYX is deciphering anomaly...";
    }

    try {
      const data = await apiRequest("/api/explain", {
        method: "POST",
        body: JSON.stringify({
          repository_url: state.repositoryUrl,
          quest,
          issue: quest
        })
      });

      const explanation =
        data?.explanation ||
        data?.message ||
        data?.response;

      if (explanation) {
        if (companionStatus) {
          companionStatus.textContent = "Dossier decrypted.";
        }

        displayNyxMessage(explanation);
      }
    } catch (error) {
      console.error("Explanation request failed:", error);

      if (companionStatus) {
        companionStatus.textContent = "Local dossier assembled.";
      }

      const lore = quest.lore_intro ? `**Sector Transmission:** *"${quest.lore_intro}"*\n\n` : "";
      const tech = quest.technical_summary ? `**Technical Directive:** ${quest.technical_summary}\n\n` : `**Summary:** ${stripMarkdown(quest.body)}\n\n`;
      const cat = quest.category ? `**Category:** \`${quest.category}\` (Threat: \`${String(quest.difficulty).toUpperCase()}\`)\n\n` : "";
      const tag = quest.tagline ? `**Mission:** ${quest.tagline}` : "";

      displayNyxMessage(
        `**NYX ARCHIVE REPORT // QUEST: ${quest.title}**\n\n` +
        lore +
        cat +
        tech +
        tag
      );
    }
  }

  function displayNyxMessage(message) {
    const companionDialogue = $("#companion-dialogue");
    if (companionDialogue) {
      companionDialogue.dataset.hasCustomMessage = "true";
      companionDialogue.innerHTML = formatMarkdownLite(message);
    }

    const container = $("#nyx-response");
    if (container) {
      container.hidden = false;
      container.innerHTML = `
            <div class="nyx-header">
                <span class="nyx-avatar">N</span>
                <strong>NYX</strong>
            </div>

            <div class="nyx-message">
                ${formatMarkdownLite(message)}
            </div>
        `;
    }
  }

  /* ---------------------------------------------------------
     ERROR DISPLAY
     --------------------------------------------------------- */

  function showScanError(message) {
    const container = findQuestContainer();

    if (!container) return;

    container.innerHTML = `
            <div class="error-state">
                <div class="error-icon">!</div>

                <h3>Repository scan failed</h3>

                <p>
                    ${escapeHtml(
      message ||
      "The server could not retrieve the repository."
    )}
                </p>

                <p class="error-help">
                    Make sure your Flask backend is running and that
                    <code>/api/quests</code> is available.
                </p>
            </div>
        `;
  }

  /* ---------------------------------------------------------
     STATS / HUD & LOOT
     --------------------------------------------------------- */

  const LOOT_ITEMS = [
    { id: "dagger", threshold: 1, name: "Console.log Dagger", rarity: "Common", desc: "The first incantation every developer ever cast. Still works." },
    { id: "shield", threshold: 2, name: "Pending PR Shield", rarity: "Rare", desc: "Awaiting review. +12 Defense while pending. No one has approved it yet." },
    { id: "branch", threshold: 3, name: "Crystallized Branch", rarity: "Epic", desc: "A crystallised git branch. Grants the ability to revert one mistake per run." },
    { id: "crown", threshold: 5, name: "Crown of Force Push", rarity: "Legendary", desc: "He who holds this may force-push to production. Embroidered with commit history." }
  ];

  function updateStats() {
    $$(".xp-val, #xp, #xp-value, #profile-xp-value, [data-stat='xp']").forEach((el) => {
      el.textContent = state.xp;
    });

    $$(".completed-val, #completed, #completed-value, #completed-count, #profile-completed-count, [data-stat='completed']").forEach((el) => {
      el.textContent = state.completed;
    });

    const questCountElements = [
      $("#quest-count"),
      $('[data-stat="quests"]')
    ];
    questCountElements.forEach((element) => {
      if (element) {
        element.textContent = `${state.quests.length} QUESTS FOUND`;
      }
    });

    const badgeCountElements = [
      $("#badge-count"),
      $('[data-stat="badges"]')
    ];
    badgeCountElements.forEach((element) => {
      if (element) {
        element.textContent = state.badges.length;
      }
    });

    const level = Math.floor(state.xp / 500) + 1;
    const levelFormatted = `LVL 0${level}`;

    $$("#level, #level-value, [data-stat='level']").forEach((el) => {
      el.textContent = level;
    });
    $$(".level-badge, #level-badge, #profile-level-badge").forEach((el) => {
      el.textContent = levelFormatted;
    });

    const levelTitles = ["ROOKIE", "APPRENTICE", "BUG HUNTER", "CODE SORCERER", "DUNGEON MASTER"];
    const currentTitle = levelTitles[Math.min(level - 1, levelTitles.length - 1)];
    $$("#level-name, #profile-level-name, .level-name-display").forEach((el) => {
      el.textContent = currentTitle;
    });

    const nextLevel = $("#next-level");
    if (nextLevel) {
      const needed = 500 - (state.xp % 500);
      nextLevel.textContent = `${needed} XP TO LEVEL ${level + 1}`;
    }

    const stepCount = $("#step-count");
    if (stepCount) {
      const total = state.selectedQuest?.steps?.length || 5;
      const current = state.selectedQuest
        ? (state.selectedQuest.status === "completed" ? total : state.currentStep + 1)
        : 0;
      stepCount.textContent = `${current}/${total}`;
    }

    const progress = ((state.xp % 500) / 500) * 100;
    $$("#xp-progress, .xp-progress, .xp-bar-fill, .progress-fill").forEach((element) => {
      element.style.width = `${progress}%`;
    });

    // Update Developer Class Displays
    const currentClass = CLASSES[state.playerClass] || CLASSES.paladin;
    const topbarClassIcon = $("#topbar-class-icon");
    const topbarClassName = $("#topbar-class-name");
    if (topbarClassIcon) topbarClassIcon.innerHTML = currentClass.icon;
    if (topbarClassName) topbarClassName.textContent = currentClass.short;

    const profileClassIcon = $("#profile-class-icon");
    const profileClassName = $("#profile-class-name");
    const profileClassSub = $("#profile-class-sub");
    if (profileClassIcon) profileClassIcon.innerHTML = currentClass.icon;
    if (profileClassName) profileClassName.textContent = currentClass.name;
    if (profileClassSub) profileClassSub.textContent = currentClass.sub;

    $$(".class-card").forEach((card) => {
      card.classList.toggle("active", card.dataset.class === state.playerClass);
    });

    // Update Dungeon Loot Drops
    let unlockedLoot = 0;
    LOOT_ITEMS.forEach((item) => {
      const isUnlocked = state.completed >= item.threshold;
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

    // Update Achievement / Badge HUD
    const achName = $("#achievement-name");
    const achDesc = $("#achievement-description");
    if (achName && achDesc) {
      if (state.completed >= 5) {
        achName.textContent = "Bug Hunter";
        achDesc.textContent = "Elite exterminator — 5 quests conquered.";
      } else if (state.completed >= 3) {
        achName.textContent = "Dungeon Crawler";
        achDesc.textContent = "Delved deep and conquered 3 dungeon quests.";
      } else if (state.completed >= 1) {
        achName.textContent = "First Blood";
        achDesc.textContent = "Slew your first bug in the dungeon.";
      } else {
        achName.textContent = "Unranked investigator";
        achDesc.textContent = "Complete your first investigation to earn a badge.";
      }
    }
  }

  function updateWorldState() {
    const world =
      $("#world-map") ||
      $(".world-map") ||
      $('[data-region="world"]');

    if (world) {
      if (!state.scanned) {
        world.classList.add("locked");
      } else {
        world.classList.remove("locked");
      }
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
        regionMsg.textContent = `Debugging realm active: ${state.quests.length} open quest${state.quests.length === 1 ? "" : "s"} discovered in repository.`;
      }
    }

    const regionCounts = { forest: 0, swamp: 0, plaza: 0, core: 0, archive: 0 };
    const regionKeys = Object.keys(regionCounts);

    state.quests.forEach((q, idx) => {
      const reg = q.region || regionKeys[idx % regionKeys.length];
      if (regionCounts[reg] !== undefined) {
        regionCounts[reg] += 1;
      }
    });

    $$(".region-node").forEach((node) => {
      const reg = node.dataset.region;
      const count = regionCounts[reg] || 0;
      const stateSpan = node.querySelector(".node-state");
      if (stateSpan) {
        if (!state.scanned) {
          stateSpan.innerHTML = `<strong class="node-count">0</strong> QUESTS`;
        } else {
          stateSpan.innerHTML = `<strong class="node-count">${count}</strong> ${count > 0 ? "ACTIVE" : "CLEAR"}`;
        }
      }
    });
  }

  /* ---------------------------------------------------------
     SEARCH / FILTER
     --------------------------------------------------------- */

  function filterQuests(searchTerm) {
    const term = String(searchTerm || "")
      .trim()
      .toLowerCase();

    $$(".quest-card, .issue-card").forEach((card) => {
      if (!term) {
        card.style.display = "";
        return;
      }

      const text = card.textContent.toLowerCase();

      card.style.display =
        text.includes(term)
          ? ""
          : "none";
    });
  }

  /* ---------------------------------------------------------
     MARKDOWN-LITE
     --------------------------------------------------------- */

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
    let html = escapeHtml(String(text || ""));

    html = html.replace(
      /```([\s\S]*?)```/g,
      "<pre><code>$1</code></pre>"
    );

    html = html.replace(
      /`([^`]+)`/g,
      "<code>$1</code>"
    );

    html = html.replace(
      /\*\*([^*]+)\*\*/g,
      "<strong>$1</strong>"
    );

    html = html.replace(
      /\*([^*]+)\*/g,
      "<em>$1</em>"
    );

    html = html.replace(
      /^### (.+)$/gm,
      "<h4>$1</h4>"
    );

    html = html.replace(
      /^## (.+)$/gm,
      "<h3>$1</h3>"
    );

    html = html.replace(
      /^# (.+)$/gm,
      "<h2>$1</h2>"
    );

    html = html.replace(
      /\n/g,
      "<br>"
    );

    return html;
  }

  function truncate(text, length) {
    const value = String(text || "");

    if (value.length <= length) {
      return value;
    }

    return value.slice(0, length).trimEnd() + "…";
  }

  /* ---------------------------------------------------------
     EVENT BINDING
     --------------------------------------------------------- */

  function bindScanButtons() {
    const selectors = [
      "#scan-button",
      "#scan-repository",
      "#scan-btn",
      '[data-action="scan"]'
    ];

    selectors.forEach((selector) => {
      $$(selector).forEach((button) => {
        button.addEventListener("click", (event) => {
          event.preventDefault();
          scanRepository();
        });
      });
    });

    $$("form").forEach((form) => {
      const hasRepositoryInput =
        form.querySelector(
          'input[type="url"], input[name*="repo" i], input[placeholder*="github" i]'
        );

      if (!hasRepositoryInput) return;

      form.addEventListener("submit", (event) => {
        event.preventDefault();
        scanRepository(
          hasRepositoryInput.value
        );
      });
    });
  }

  function bindSearch() {
    const searchInputs = $$(
      '#quest-search, [data-action="search"], input[placeholder*="search" i]'
    );

    searchInputs.forEach((input) => {
      input.addEventListener("input", () => {
        filterQuests(input.value);
      });
    });
  }

  function bindExplanationButtons() {
    $$(
      '#explain-button, #explain-quest, [data-action="explain"]'
    ).forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        requestExplanation();
      });
    });

    $$(
      '#hint-button, #request-hint, [data-action="hint"]'
    ).forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        requestHint();
      });
    });

    // Bind region map nodes to filter by region using state.activeRegionFilter
    $$(".region-node").forEach((node) => {
      node.addEventListener("click", () => {
        const regionId = node.dataset.region;
        playSfx("node");
        if (state.activeRegionFilter === regionId) {
          state.activeRegionFilter = null;
          $$(".region-node").forEach((n) => n.classList.remove("active"));
          const rf = $("#quest-filter");
          if (rf) rf.textContent = "ALL REGIONS";
        } else {
          state.activeRegionFilter = regionId;
          $$(".region-node").forEach((n) => n.classList.remove("active"));
          node.classList.add("active");
          const rf = $("#quest-filter");
          if (rf) rf.textContent = node.querySelector(".node-title")?.textContent || regionId.toUpperCase();
        }
        renderQuestList();
      });
    });
  }

  /* ---------------------------------------------------------
     INITIALIZATION
     --------------------------------------------------------- */

  function init() {
    loadPlayerState();

    bindScanButtons();
    bindSearch();
    bindExplanationButtons();

    // Wire #quick-demo-btn to load 5 quests across all 5 sectors
    const demoBtn = $("#quick-demo-btn");
    if (demoBtn) {
      demoBtn.addEventListener("click", () => {
        playSfx("radar");
        setRepositoryUrl("https://github.com/pallets/flask");
        state.repository = { owner: "pallets", name: "flask" };
        BugDungeon.loadQuests([
          {
            quest_id: "quest_demo_forest",
            issue_number: 1042,
            quest_title: "The Wild Async Flora",
            tagline: "Tame the runaway asynchronous execution threads in the Feature Forest.",
            difficulty: "Intermediate",
            region: "forest",
            region_name: "Feature Forest",
            category: "Feature Expansion",
            xp_reward: 250,
            estimated_time_minutes: 20,
            tags: ["Python", "AsyncIO", "Enhancement"],
            briefing: {
              lore_intro: "Deep within the wild branches of the Feature Forest, uncached async streams are duplicating API calls.",
              technical_summary: "Implement debounce cache and async context locks on high-frequency dispatchers."
            },
            objectives: [
              { step: 1, title: "Recon", instruction: "Trace async event loop handlers in flask/sansio/app.py." },
              { step: 2, title: "Locking", instruction: "Wrap concurrent task dispatchers with asyncio.Lock." },
              { step: 3, title: "Benchmark", instruction: "Verify request throughput does not degrade under 500 req/sec." }
            ],
            hints: [{ level: 1, tier: "Gentle Nudge", hint: "Check functools.lru_cache or aiocache for async helpers.", xp_cost: 10 }],
            verification_checklist: ["No duplicate task dispatches", "Zero memory leak under load"]
          },
          {
            quest_id: "quest_demo_core",
            issue_number: 2088,
            quest_title: "Root Architecture Convergence",
            tagline: "Stabilize the core trunk of the codebase before the merge window collapses.",
            difficulty: "Master",
            region: "core",
            region_name: "Main Branch World Tree",
            category: "Core Architecture",
            xp_reward: 450,
            estimated_time_minutes: 40,
            tags: ["Architecture", "Refactor", "Core"],
            briefing: {
              lore_intro: "The World Tree anchors every dependency. A circular import is choking the root.",
              technical_summary: "Decouple the application context factory from the blueprint registries to eliminate circular references."
            },
            objectives: [
              { step: 1, title: "Analyze Imports", instruction: "Map the dependency graph between app.py and blueprints.py." },
              { step: 2, title: "Extract Factory", instruction: "Move context initialization to a standalone factory module." },
              { step: 3, title: "Verify Tree", instruction: "Run full pytest suite to ensure backwards compatibility." }
            ],
            hints: [{ level: 1, tier: "Architectural Clue", hint: "Use lazy imports or dependency injection in create_app().", xp_cost: 20 }],
            verification_checklist: ["Zero circular import warnings", "Passes pytest tests/test_app.py"]
          },
          {
            quest_id: "quest_demo_plaza",
            issue_number: 3105,
            quest_title: "The Stalled PR of Year 100",
            tagline: "Review a crucial community contribution that has waited 47 days for approvals.",
            difficulty: "Novice",
            region: "plaza",
            region_name: "PR Plaza",
            category: "Code Review",
            xp_reward: 150,
            estimated_time_minutes: 15,
            tags: ["Good First Issue", "Community", "Review"],
            briefing: {
              lore_intro: "Gemma has flagged this PR for missing regression coverage. Guide the contributor to green checks.",
              technical_summary: "Add unit tests for edge-case HTTP 429 Retry-After response header parsing."
            },
            objectives: [
              { step: 1, title: "Review Diff", instruction: "Inspect the PR diff in tests/test_responses.py." },
              { step: 2, title: "Add Cases", instruction: "Include test assertions for decimal seconds and HTTP dates." }
            ],
            hints: [{ level: 1, tier: "Reviewer Tip", hint: "See RFC 7231 section 7.1.3 for date formatting specs.", xp_cost: 10 }],
            verification_checklist: ["Unit tests cover malformed headers", "Gemma approves the diff"]
          },
          {
            quest_id: "quest_demo_swamp",
            issue_number: 4099,
            quest_title: "The Null Pointer Hydra",
            tagline: "An ancient Merge Conflict beast lurks beneath the murky stack traces.",
            difficulty: "Expert",
            region: "swamp",
            region_name: "Bug Swamp",
            category: "Bug Bounty",
            xp_reward: 500,
            estimated_time_minutes: 45,
            tags: ["Bug", "Critical", "Crash"],
            briefing: {
              lore_intro: "<<<<<<< HEAD: Uncaught TypeError: undefined has no properties. >>>>>>> main. The Merge Conflict stirs!",
              technical_summary: "Implement defensive null-coalescing guards across request parsing routines to prevent unhandled 500 crashes."
            },
            objectives: [
              { step: 1, title: "Trap Exception", instruction: "Reproduce the crash with malformed JSON payloads in request.get_json()." },
              { step: 2, title: "Slay the Bug", instruction: "Replace unchecked property accesses with safe .get() defaults." },
              { step: 3, title: "Sanitize Swamp", instruction: "Ensure proper 400 Bad Request error response is returned." }
            ],
            hints: [{ level: 1, tier: "Boss Weakness", hint: "Check werkzeug.exceptions.BadRequest handling.", xp_cost: 25 }],
            verification_checklist: ["Crash no longer produces 500 internal server error", "Malformed JSON returns clean 400"]
          },
          {
            quest_id: "quest_demo_archive",
            issue_number: 5012,
            quest_title: "The Legacy Fortran Scroll",
            tagline: "Decipher ancient comments written in Year 12 that still somehow compile.",
            difficulty: "Novice",
            region: "archive",
            region_name: "Deprecated Archive",
            category: "Documentation",
            xp_reward: 175,
            estimated_time_minutes: 20,
            tags: ["Docs", "Archive", "Cleanup"],
            briefing: {
              lore_intro: "A dusty corridor in the archive contains undocumented routines with arcane parameters.",
              technical_summary: "Convert legacy docstrings in flask/helpers.py to standard Sphinx Google-format documentation."
            },
            objectives: [
              { step: 1, title: "Decipher", instruction: "Read undocumented parameters in send_from_directory()." },
              { step: 2, title: "Inscribe", instruction: "Write comprehensive type signatures and example snippets." }
            ],
            hints: [{ level: 1, tier: "Archive Scribe", hint: "Follow the Google Python Style Guide docstring format.", xp_cost: 10 }],
            verification_checklist: ["Sphinx build succeeds with zero docstring warnings"]
          }
        ]);
        showMessage('<svg class="svg-icon"><use href="#icon-lightning"></use></svg> Loaded 5-sector demo! Explore the Overworld Map sectors.', 'success');
      });
    }

    // Wire Developer Class Cards
    $$(".class-card").forEach((card) => {
      card.addEventListener("click", () => {
        const clsId = card.dataset.class;
        if (CLASSES[clsId]) {
          state.playerClass = clsId;
          playSfx("select");
          savePlayerState();
          updateStats();
          const cls = CLASSES[clsId];
          showMessage(`Class aligned: ${cls.name} (${cls.sub})!`, "info");
        }
      });
    });

    // Wire NPC Cards & Dialogue Modal
    const NPC_DATA = {
      nyx: {
        name: "NYX",
        role: "AI COMPANION · TACTICAL ANALYST",
        avatar: '<svg class="svg-icon"><use href="#icon-nyx"></use></svg>',
        speech: `<p>“I study the syntax shadows and decompile bytecode anomalies. In the GitVerse, bugs are not mere errors — they are corrupted bosses waiting for a worthy investigator.</p><p>Consult me anytime during your quest for tactical hints or issue deconstruction!”</p>`
      },
      merge_conflict: {
        name: "THE MERGE CONFLICT",
        role: "ANCIENT ANTAGONIST · FINAL BOSS",
        avatar: '<svg class="svg-icon"><use href="#icon-merge-conflict"></use></svg>',
        speech: `<p><code>&lt;&lt;&lt;&lt;&lt;&lt;&lt; HEAD: You thought this was resolved.<br>=======<br>&gt;&gt;&gt;&gt;&gt;&gt;&gt; main: I have festered since Year 100.</code></p><p>“I am not evil — just unresolved. A PR opened eons ago that gained sentience. I do not wish to destroy the GitVerse... I just want to be merged.”</p>`
      },
      aria: {
        name: "ARIA",
        role: "DEPLOYER GUIDE · SHIP CAPTAIN",
        avatar: '<svg class="svg-icon"><use href="#icon-aria"></use></svg>',
        speech: `<p>“Ship captain of the GitVerse! I keep our deployment pipelines green and ship artifacts to edge sectors. Chaos stresses me out, but we handle it anyway.</p><p>Be careful when venturing into the Bug Swamp — uncaught exceptions lurk in the murk!”</p>`
      },
      linus: {
        name: "LINUS",
        role: "LEGENDARY NPC · ANCIENT COMMITTER",
        avatar: '<svg class="svg-icon"><use href="#icon-linus"></use></svg>',
        speech: `<p>“Fellow developer, I've been watching your commit graph. Every PR you merged, every late-night deploy — they weren't just work. They were training.</p><p>In the GitVerse, your code has weight. Your consistency has power. Those 3,000 commits? They forged a warrior.”</p>`
      },
      gemma: {
        name: "GEMMA",
        role: "HEALER NPC · CODE REVIEWER",
        avatar: '<svg class="svg-icon"><use href="#icon-gemma"></use></svg>',
        speech: `<p>“Meticulous, kind, never harsh. I was supposed to review the original Schism PR in Year 100, but I was busy. That is my deepest regret — and the reason I review every PR without exception now.</p><p>Write clean diffs and take your time; quality code heals the realm.”</p>`
      }
    };

    const modal = $("#npc-dialogue-modal");
    const modalAvatar = $("#modal-npc-avatar");
    const modalName = $("#modal-npc-name");
    const modalRole = $("#modal-npc-role");
    const modalSpeech = $("#modal-npc-speech");
    const closeModal = () => {
      if (modal) modal.hidden = true;
    };

    $$("[data-npc]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const npcKey = btn.dataset.npc;
        const npc = NPC_DATA[npcKey];
        if (npc && modal) {
          playSfx("nyx");
          if (modalAvatar) modalAvatar.innerHTML = npc.avatar;
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

    // Wire Linus Wisdom Button
    const LINUS_WISDOMS = [
      "“Fellow developer, every PR you merged, every bug you squashed — they were training. In the GitVerse, your consistency has power.”",
      "“Talk is cheap. Show me the code.”",
      "“That 47-day streak? It's not just a number on a graph. It's a legendary buff that fuels your spells.”",
      "“Bad programmers worry about the code. Good programmers worry about data structures and their relationships.”",
      "“A git commit is a promise to the future. Make your messages worthy of an epic chronicle.”",
      "“He who holds the Crown of Force Push may override production, but true masters never need it.”"
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

    // Wire Loot Slots Hover & Click
    $$(".loot-slot").forEach((slot) => {
      const showDetail = () => {
        const lootId = slot.dataset.lootId;
        const item = LOOT_ITEMS.find((l) => l.id === lootId);
        const detailEl = $("#loot-detail");
        if (item && detailEl) {
          const unlocked = state.completed >= item.threshold;
          detailEl.innerHTML = unlocked
            ? `<strong style="color:var(--gold);">${item.name}</strong> [${item.rarity}] &middot; ${item.desc}`
            : `<span style="color:var(--muted);">${item.name} (LOCKED) &middot; Requires ${item.threshold} completed quest${item.threshold > 1 ? "s" : ""}.</span>`;
        }
      };
      slot.addEventListener("mouseenter", showDetail);
      slot.addEventListener("click", () => {
        playSfx("select");
        showDetail();
      });
    });

    // Wire Region Node Hover Lore Tooltips
    $$(".region-node").forEach((node) => {
      node.addEventListener("mouseenter", () => {
        const lore = node.dataset.lore;
        const regionMsg = $("#region-message");
        const nodeTitle = node.querySelector(".node-title")?.textContent || "";
        if (lore && regionMsg) {
          regionMsg.innerHTML = `<strong>${nodeTitle}:</strong> ${lore}`;
        }
      });
      node.addEventListener("mouseleave", () => {
        updateWorldState();
      });
    });

    // Wire #sfx-toggle
    const sfxBtn = $("#sfx-toggle");
    if (sfxBtn) {
      const updateSfxBtn = () => {
        sfxBtn.classList.toggle("muted", !state.sfxEnabled);
        sfxBtn.innerHTML = state.sfxEnabled
          ? `<svg class="svg-icon"><use href="#icon-volume-on"></use></svg> SFX: ON`
          : `<svg class="svg-icon"><use href="#icon-volume-off"></use></svg> SFX: OFF`;
      };
      updateSfxBtn();
      sfxBtn.addEventListener("click", () => {
        state.sfxEnabled = !state.sfxEnabled;
        updateSfxBtn();
        if (state.sfxEnabled) playSfx("click");
        savePlayerState();
      });
    }

    renderAll();

    /*
     * Allow the page to receive a repository URL through
     * ?repo=https://github.com/user/repository
     */

    try {
      const params = new URLSearchParams(window.location.search);
      const repo = params.get("repo");
      if (repo) {
        setRepositoryUrl(repo);
      }
    } catch {
      // Ignore malformed URL parameters.
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener(
      "DOMContentLoaded",
      init
    );
  } else {
    init();
  }

  function loadQuests(questsData) {
    state.quests = normalizeQuests(questsData);
    state.scanned = true;
    if (state.quests.length > 0) {
      state.selectedQuest = state.quests[0];
      state.currentStep = 0;
    }
    renderAll();
  }

  /* ---------------------------------------------------------
     PUBLIC API
     --------------------------------------------------------- */

  window.BugDungeon = {
    state,
    loadQuests,
    scanRepository,
    selectQuest,
    selectQuestById,
    completeQuest,
    requestHint,
    requestExplanation,
    filterQuests
  };
})();
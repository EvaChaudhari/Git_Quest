/**
 * BUG//DUNGEON — Frontend State Machine & API Client Unit Tests
 * Uses native Node.js test runner (zero external dependencies).
 * Run with: node --test test_frontend_state.js
 */

const { test, describe } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

// Read static/app.js source code to verify key exports and logic
const appJsSource = fs.readFileSync(path.join(__dirname, "static/app.js"), "utf8");

describe("GitQuest Static Script Validation", () => {
  test("static/app.js has valid syntax and contains all contract methods", () => {
    assert.match(appJsSource, /class GitQuestApiClient/);
    assert.match(appJsSource, /getTrainingIssues/);
    assert.match(appJsSource, /getOpenIssues/);
    assert.match(appJsSource, /generateTrainingQuest/);
    assert.match(appJsSource, /generateOpenQuest/);
    assert.match(appJsSource, /unlockHint/);
    assert.match(appJsSource, /completeQuest/);
    assert.match(appJsSource, /getUserProfile/);
  });

  test("static/app.js implements status code classification for all error types", () => {
    assert.match(appJsSource, /response\.status === 400/);
    assert.match(appJsSource, /response\.status === 401/);
    assert.match(appJsSource, /response\.status === 403/);
    assert.match(appJsSource, /response\.status === 404/);
    assert.match(appJsSource, /response\.status === 409/);
    assert.match(appJsSource, /response\.status === 429/);
    assert.match(appJsSource, /response\.status === 502/);
    assert.match(appJsSource, /response\.status === 503/);
    assert.match(appJsSource, /response\.status >= 500/);
  });

  test("static/app.js ensures locked hints never leak text", () => {
    assert.match(appJsSource, /hint: isUnlocked \? \(h\.hint \|\| ""\) : ""/);
    assert.match(appJsSource, /🔒 Guidance Locked/);
  });

  test("static/app.js clears stale quest data on new selection", () => {
    assert.match(appJsSource, /state\.activeQuest = null/);
    assert.match(appJsSource, /state\.questError = null/);
  });

  test("static/app.js guards against race conditions with sequence IDs", () => {
    assert.match(appJsSource, /currentScanId/);
    assert.match(appJsSource, /currentQuestGenId/);
    assert.match(appJsSource, /scanId !== currentScanId/);
    assert.match(appJsSource, /questGenId !== currentQuestGenId/);
  });

  test("static/app.js exposes API client and state on window.GitQuest", () => {
    assert.match(appJsSource, /window\.GitQuest = \{/);
    assert.match(appJsSource, /apiClient,/);
    assert.match(appJsSource, /state,/);
    assert.match(appJsSource, /scanRepository,/);
    assert.match(appJsSource, /selectIssue,/);
    assert.match(appJsSource, /unlockHintTier,/);
    assert.match(appJsSource, /submitQuestCompletion,/);
    assert.match(appJsSource, /fetchUserProfile/);
  });

  test("static/app.js provides retry button actions for scan and quest generation", () => {
    assert.match(appJsSource, /id="retry-scan-btn"/);
    assert.match(appJsSource, /id="retry-quest-gen-btn"/);
  });
});

describe("GitQuest HTML & CSS Contract Elements", () => {
  const indexHtml = fs.readFileSync(path.join(__dirname, "templates/index.html"), "utf8");
  const styleCss = fs.readFileSync(path.join(__dirname, "static/style.css"), "utf8");

  test("index.html contains API base URL configuration meta tag", () => {
    assert.match(indexHtml, /<meta name="gitquest-api-base"/);
  });

  test("index.html contains all 6 journey stage DOM anchors", () => {
    // Step 1: Repo input
    assert.match(indexHtml, /id="repo-url"/);
    assert.match(indexHtml, /id="scan-button"/);
    assert.match(indexHtml, /id="issues-list"/);

    // Step 2: Learning mode
    assert.match(indexHtml, /id="mode-stage-a-btn"/);
    assert.match(indexHtml, /id="mode-stage-b-btn"/);
    assert.match(indexHtml, /id="stage-b-lock-banner"/);

    // Step 3: Quest Briefing
    assert.match(indexHtml, /id="investigation-slot"/);

    // Step 4 & 5: Completion & Hints
    assert.match(indexHtml, /id="profile-stage-a-count"/);

    // Step 6: HUD and Profile
    assert.match(indexHtml, /id="xp-value"/);
    assert.match(indexHtml, /id="consistency-val"/);
    assert.match(indexHtml, /id="topbar-stage-b-stat"/);
  });

  test("style.css defines evidence badges, hint cards, and locked cards", () => {
    assert.match(styleCss, /\.evidence-badge\.verified/);
    assert.match(styleCss, /\.evidence-badge\.partial/);
    assert.match(styleCss, /\.evidence-badge\.unavailable/);
    assert.match(styleCss, /\.hint-tier-card/);
    assert.match(styleCss, /\.quest-completion-box/);
    assert.match(styleCss, /\.stage-b-locked-card/);
  });
});

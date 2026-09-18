let config = null;
let session = null;

const STORAGE_KEY = "se_tutor_session";

const $ = (id) => document.getElementById(id);

function showError(el, msg) {
  el.textContent = msg;
  el.classList.toggle("hidden", !msg);
}

function renderMarkdownLite(text) {
  return text
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function renderMessages(messages) {
  const box = $("messages");
  box.innerHTML = "";
  for (const msg of messages) {
    const div = document.createElement("div");
    const isTutor = msg.role === "assistant";
    div.className = `msg ${isTutor ? "tutor" : "student"}`;
    div.innerHTML = `<span class="label">${isTutor ? "Tutor" : "Student"}</span>${renderMarkdownLite(msg.content)}`;
    box.appendChild(div);
  }
  box.scrollTop = box.scrollHeight;
}

function saveToBrowser(data) {
  const payload = {
    ...data,
    saved_at: new Date().toISOString(),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  refreshResumePanel();
}

function loadFromBrowser() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function clearBrowserSave() {
  localStorage.removeItem(STORAGE_KEY);
  refreshResumePanel();
}

function formatTranscript(data) {
  const lines = [
    `SE Tutor transcript`,
    `Topic: ${data.topic_name}`,
    `Model: ${data.provider}`,
    `Phase: ${data.phase_label || data.phase}`,
    `Saved: ${data.saved_at || new Date().toISOString()}`,
    "",
  ];
  for (const msg of data.messages || []) {
    const who = msg.role === "assistant" ? "Tutor" : "Student";
    lines.push(`[${who}]`, msg.content, "");
  }
  return lines.join("\n");
}

function downloadTranscript(data = session) {
  if (!data?.messages?.length) return;
  const blob = new Blob([formatTranscript(data)], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `se-tutor-${data.topic_id || "chat"}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

function setComposerEnabled(enabled) {
  $("input").disabled = !enabled;
  $("send-btn").disabled = !enabled;
  $("simulate-btn").disabled = !enabled;
  $("composer").classList.toggle("disabled", !enabled);
}

function onTopicSelectionPage() {
  return !$("view-chat").classList.contains("hidden") && !$("setup").classList.contains("hidden");
}

function updateBackToTopicsButton() {
  const show = !onTopicSelectionPage();
  $("back-topics-btn").classList.toggle("hidden", !show);
}

function showChatView() {
  $("view-topics").classList.add("hidden");
  $("view-chat").classList.remove("hidden");
  $("nav-chat").classList.add("active");
  $("nav-topics").classList.remove("active");
}

function showChatScreen() {
  showChatView();
  $("setup").classList.add("hidden");
  $("chat-screen").classList.remove("hidden");
  updateBackToTopicsButton();
}

function showSetupScreen() {
  $("chat-screen").classList.add("hidden");
  $("setup").classList.remove("hidden");
  session = null;
  setComposerEnabled(true);
  $("ended-banner").classList.add("hidden");
  $("complete-banner").classList.add("hidden");
  $("ended-banner").textContent =
    "Session ended — download your transcript or reset to start fresh.";
  updateBackToTopicsButton();
  refreshResumePanel();
}

function backToTopicSelection() {
  showChatView();
  showSetupScreen();
  showError($("chat-error"), "");
  showError($("setup-error"), "");
}

window.updateBackToTopicsButton = updateBackToTopicsButton;
window.backToTopicSelection = backToTopicSelection;

function updateSessionUI(data) {
  session = data;
  $("topic-badge").textContent = data.topic_name;
  $("phase-badge").textContent = data.phase_label;
  $("phase-badge").className = "badge phase";
  if (data.status === "complete") $("phase-badge").classList.add("complete");
  if (data.status === "ended") $("phase-badge").classList.add("ended-state");
  $("model-badge").textContent = data.provider.toUpperCase();
  $("personality-live").value = data.personality;
  renderMessages(data.messages);

  const ended = data.status === "ended";
  const complete = data.status === "complete";

  setComposerEnabled(!ended);
  $("input").placeholder = complete
    ? "Any last doubts? Say \"no doubts\" when you're done…"
    : "Type your reply as the student…";

  $("complete-banner").classList.toggle("hidden", !complete);
  if (complete) {
    $("complete-banner").textContent =
      "Wrap-up — say what you can do now and what’s still fuzzy. Ask for a model example if you want one, jump back if something is vague, or say \"no doubts\" to close.";
  }

  $("ended-banner").classList.toggle("hidden", !ended);
  $("end-btn").disabled = ended;

  renderLessonNav(data);
  renderScenarioPicker(data);

  saveToBrowser(data);
}

function renderLessonNav(data) {
  const bar = $("lesson-nav");
  if (!bar) return;
  if (data.status === "ended" || !data.nav) {
    bar.hidden = true;
    bar.innerHTML = "";
    return;
  }
  bar.hidden = false;
  bar.innerHTML = "";
  for (const item of data.nav) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "nav-phase" + (item.current ? " current" : "");
    btn.textContent = item.label;
    btn.disabled = !item.unlocked || data.status === "ended";
    btn.addEventListener("click", () => navigatePhase(item.id));
    bar.appendChild(btn);
  }
}

function renderScenarioPicker(data) {
  const box = $("scenario-picker");
  if (!box) return;
  const show = data.awaiting_scenario && data.status !== "ended";
  box.classList.toggle("hidden", !show);
  box.innerHTML = "";
  if (!show) return;

  const label = document.createElement("p");
  label.className = "picker-label";
  label.textContent = "Pick a practice scenario:";
  box.appendChild(label);

  for (const option of data.practice_options || []) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "scenario-chip";
    btn.textContent = option;
    btn.addEventListener("click", () => chooseScenario(option));
    box.appendChild(btn);
  }
}

async function navigatePhase(phase) {
  if (!session?.session_id || session.ended) return;
  if (phase === session.phase) return;
  showError($("chat-error"), "");
  try {
    const res = await fetch("/api/session/navigate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: session.session_id, phase }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Could not move");
    }
    updateSessionUI(await res.json());
  } catch (e) {
    showError($("chat-error"), e.message);
  }
}

async function chooseScenario(scenario) {
  if (!session?.session_id || session.ended) return;
  showError($("chat-error"), "");
  setComposerEnabled(false);
  try {
    const res = await fetch("/api/session/scenario", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: session.session_id, scenario }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Could not set scenario");
    }
    updateSessionUI(await res.json());
  } catch (e) {
    showError($("chat-error"), e.message);
    setComposerEnabled(!session?.ended);
  }
}

function refreshResumePanel() {
  const saved = loadFromBrowser();
  const panel = $("resume-panel");
  if (!saved?.messages?.length) {
    panel.classList.add("hidden");
    return;
  }

  const when = saved.saved_at ? new Date(saved.saved_at).toLocaleString() : "recently";
  const status = saved.status || (saved.ended ? "ended" : "active");
  $("resume-summary").textContent =
    `${saved.topic_name} · ${saved.messages.length} messages · ${status} · saved ${when}`;
  panel.classList.remove("hidden");
}

async function reloadTopicsDropdown() {
  const res = await fetch("/api/config");
  const data = await res.json();
  if (config) config.topics = data.topics;
  const selected = $("topic").value;
  $("topic").innerHTML = data.topics
    .map((t) => {
      const tag = t.builtin === false ? "" : "";
      return `<option value="${t.id}">${t.number}. ${t.name}${t.builtin === false ? " (custom)" : ""}</option>`;
    })
    .join("");
  if (selected && data.topics.some((t) => t.id === selected)) {
    $("topic").value = selected;
  }
}

window.reloadTopicsDropdown = reloadTopicsDropdown;

async function loadConfig() {
  const res = await fetch("/api/config");
  config = await res.json();

  $("provider").innerHTML = config.providers
    .map((p) => `<option value="${p.id}">${p.label}</option>`)
    .join("");

  $("topic").innerHTML = config.topics
    .map((t) => `<option value="${t.id}">${t.number}. ${t.name}</option>`)
    .join("");

  const personalityOptions = config.personalities
    .map((p) => `<option value="${p.id}">${p.label}</option>`)
    .join("");

  $("personality").innerHTML = personalityOptions;
  $("personality-live").innerHTML = personalityOptions;
  $("personality").value = config.default_personality;

  refreshResumePanel();
  await tryAutoResume();
}

async function tryAutoResume() {
  const saved = loadFromBrowser();
  if (!saved?.session_id || saved.status === "ended" || saved.ended) return;

  try {
    const res = await fetch(`/api/session/${saved.session_id}`);
    if (!res.ok) return;
    const data = await res.json();
    showChatScreen();
    updateSessionUI(data);
  } catch {
    // Server may be down — user can use resume button or view transcript
  }
}

async function startSession() {
  showError($("setup-error"), "");
  $("start-btn").disabled = true;

  try {
    const res = await fetch("/api/session/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic_id: $("topic").value,
        provider: $("provider").value,
        personality: $("personality").value,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed to start");
    }

    showChatScreen();
    updateSessionUI(await res.json());
  } catch (e) {
    showError($("setup-error"), e.message);
  } finally {
    $("start-btn").disabled = false;
  }
}

async function resumeSession() {
  const saved = loadFromBrowser();
  if (!saved?.session_id) return;

  showError($("setup-error"), "");
  try {
    const res = await fetch(`/api/session/${saved.session_id}`);
    if (!res.ok) {
      throw new Error("Server session expired (server was restarted). View saved transcript or start fresh.");
    }
    showChatScreen();
    updateSessionUI(await res.json());
  } catch (e) {
    showError($("setup-error"), e.message);
  }
}

function viewSavedTranscript() {
  const saved = loadFromBrowser();
  if (!saved) return;
  showChatScreen();
  session = saved;
  $("topic-badge").textContent = saved.topic_name || "Saved chat";
  $("phase-badge").textContent = saved.phase_label || saved.phase || "saved";
  $("model-badge").textContent = (saved.provider || "").toUpperCase();
  renderMessages(saved.messages);
  setComposerEnabled(false);
  if ($("lesson-nav")) {
    $("lesson-nav").hidden = true;
    $("lesson-nav").innerHTML = "";
  }
  $("scenario-picker").classList.add("hidden");
  $("ended-banner").classList.remove("hidden");
  $("ended-banner").textContent =
    "Viewing saved transcript only — server session may be gone. Reset to start a new chat.";
}

async function sendMessage(text) {
  if (!session || !text.trim() || session.ended) return;

  showError($("chat-error"), "");
  setComposerEnabled(false);

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: session.session_id, message: text.trim() }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Send failed");
    }

    updateSessionUI(await res.json());
    $("input").value = "";
  } catch (e) {
    showError($("chat-error"), e.message);
    setComposerEnabled(!session?.ended);
  }
}

async function simulateStudent() {
  if (!session || session.ended) return;

  showError($("chat-error"), "");
  setComposerEnabled(false);

  try {
    const res = await fetch("/api/simulate-student", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: session.session_id }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Simulate failed");
    }

    updateSessionUI(await res.json());
  } catch (e) {
    showError($("chat-error"), e.message);
    setComposerEnabled(!session?.ended);
  }
}

async function endSession() {
  if (!session || session.ended) return;
  if (!confirm("End this session? You can still download the transcript.")) return;

  showError($("chat-error"), "");
  try {
    const res = await fetch("/api/session/end", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: session.session_id }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Could not end session");
    }
    updateSessionUI(await res.json());
  } catch (e) {
    showError($("chat-error"), e.message);
  }
}

async function resetSession() {
  if (!confirm("Reset session? This clears the chat on the server and in this browser.")) return;

  if (session?.session_id) {
    try {
      await fetch("/api/session/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: session.session_id }),
      });
    } catch {
      // Best-effort — local clear still happens
    }
  }

  clearBrowserSave();
  showSetupScreen();
  showError($("chat-error"), "");
}

async function changePersonality(personality) {
  if (!session?.session_id) return;

  const res = await fetch("/api/session/personality", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: session.session_id, personality }),
  });

  if (res.ok) {
    session.personality = personality;
    saveToBrowser(session);
  }
}

$("back-topics-btn").addEventListener("click", backToTopicSelection);

$("start-btn").addEventListener("click", startSession);
$("resume-btn").addEventListener("click", resumeSession);
$("view-transcript-btn").addEventListener("click", viewSavedTranscript);
$("clear-saved-btn").addEventListener("click", () => {
  if (confirm("Clear saved transcript from this browser?")) {
    clearBrowserSave();
  }
});

$("send-btn").addEventListener("click", () => sendMessage($("input").value));
$("simulate-btn").addEventListener("click", simulateStudent);
$("download-btn").addEventListener("click", () => downloadTranscript());
$("end-btn").addEventListener("click", endSession);
$("reset-btn").addEventListener("click", resetSession);

$("input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage($("input").value);
  }
});

$("personality-live").addEventListener("change", (e) => {
  changePersonality(e.target.value);
});

loadConfig();

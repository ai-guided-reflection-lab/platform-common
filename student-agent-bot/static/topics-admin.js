(() => {
  const byId = (id) => document.getElementById(id);
  let currentDraftId = null;

  function showMsg(node, msg, isError = true) {
    if (!node) return;
    node.textContent = msg || "";
    node.classList.toggle("hidden", !msg);
    node.classList.toggle("error", isError);
    node.classList.toggle("success", !isError && !!msg);
  }

  function switchView(view) {
    byId("view-chat").classList.toggle("hidden", view !== "chat");
    byId("view-topics").classList.toggle("hidden", view !== "topics");
    byId("nav-chat").classList.toggle("active", view === "chat");
    byId("nav-topics").classList.toggle("active", view === "topics");
    if (view === "topics") loadCustomTopics();
    if (window.updateBackToTopicsButton) window.updateBackToTopicsButton();
  }

  function renderOptions(options) {
    const box = byId("tf-options");
    if (!box) return;
    const values = options && options.length ? options : ["", "", ""];
    while (values.length < 3) values.push("");
    box.innerHTML = "";
    values.slice(0, 3).forEach((opt, i) => {
      box.innerHTML += `
        <div class="question-row">
          <label>Option ${i + 1}</label>
          <input class="tf-opt" value="${escapeAttr(opt)}" required />
        </div>`;
    });
  }

  function renderStages(stages) {
    const box = byId("tf-stages");
    box.innerHTML = "";
    stages.forEach((s, idx) => {
      box.innerHTML += `
        <div class="stage-row">
          <input class="tf-stage-label" data-i="${idx}" value="${escapeAttr(s.label)}" required />
          <input class="tf-stage-focus" data-i="${idx}" value="${escapeAttr(s.focus)}" required />
        </div>`;
    });
  }

  function escapeAttr(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function fillDraftForm(draft) {
    currentDraftId = draft.id;
    byId("tf-name").value = draft.name;
    byId("tf-id-display").textContent = draft.id;
    byId("tf-r1-title").value = draft.resource.title;
    byId("tf-r1-url").value = draft.resource.url;
    byId("tf-r2-title").value = draft.alt_resource.title;
    byId("tf-r2-url").value = draft.alt_resource.url;
    byId("tf-practice-label").value = draft.practice_label;
    byId("tf-practice-prompt").value = draft.practice_prompt;
    byId("tf-final").value = draft.final_example;
    renderOptions(draft.practice_options);
    renderStages(draft.practice_stages);
    byId("topic-form").classList.remove("hidden");
    showMsg(byId("topic-form-error"), "");
    showMsg(byId("topic-form-success"), "", false);
  }

  function hideDraftForm() {
    byId("topic-form").classList.add("hidden");
    currentDraftId = null;
  }

  async function loadCustomTopics() {
    const res = await fetch("/api/topics/manage");
    const data = await res.json();
    const custom = data.topics.filter((t) => !t.builtin);
    const list = byId("custom-topic-list");
    list.innerHTML = "";
    byId("no-custom-topics").classList.toggle("hidden", custom.length > 0);

    for (const topic of custom) {
      const li = document.createElement("li");
      li.innerHTML = `<span><strong>${topic.name}</strong> <span class="muted-text">(${topic.id})</span></span>`;
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn ghost";
      btn.textContent = "Delete";
      btn.onclick = () => deleteTopic(topic.id);
      li.appendChild(btn);
      list.appendChild(li);
    }
  }

  async function deleteTopic(id) {
    if (!confirm(`Delete custom topic "${id}"?`)) return;
    const res = await fetch(`/api/topics/${id}`, { method: "DELETE" });
    if (!res.ok) {
      const err = await res.json();
      alert(err.detail || "Delete failed");
      return;
    }
    if (window.reloadTopicsDropdown) await window.reloadTopicsDropdown();
    loadCustomTopics();
  }

  async function generateDraft() {
    const name = byId("gen-topic-name").value.trim();
    if (!name) return;

    const btn = byId("generate-topic-btn");
    const status = byId("generate-status");
    btn.disabled = true;
    showMsg(byId("generate-error"), "");
    status.textContent = "Searching beginner tutorials and drafting lesson…";
    status.classList.remove("hidden");
    status.classList.add("loading");

    try {
      const res = await fetch("/api/topics/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          provider: byId("gen-provider").value,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Generate failed");
      }
      const data = await res.json();
      fillDraftForm(data.draft);
      status.textContent = "Draft ready — review the links and fields below.";
      status.classList.remove("loading");
    } catch (e) {
      status.classList.add("hidden");
      showMsg(byId("generate-error"), e.message);
    } finally {
      btn.disabled = false;
    }
  }

  function collectFormData() {
    const options = [...document.querySelectorAll(".tf-opt")].map((input) => input.value.trim()).filter(Boolean);
    const stages = [...document.querySelectorAll(".tf-stage-label")].map((labelEl, idx) => {
      const focusEl = document.querySelector(`.tf-stage-focus[data-i="${idx}"]`);
      return { label: labelEl.value.trim(), focus: focusEl.value.trim() };
    });

    return {
      id: currentDraftId,
      name: byId("tf-name").value.trim(),
      resource: {
        title: byId("tf-r1-title").value.trim(),
        url: byId("tf-r1-url").value.trim(),
      },
      alt_resource: {
        title: byId("tf-r2-title").value.trim(),
        url: byId("tf-r2-url").value.trim(),
      },
      practice_label: byId("tf-practice-label").value.trim() || options[0] || "",
      practice_prompt: byId("tf-practice-prompt").value.trim(),
      practice_options: options,
      practice_stages: stages,
      final_example: byId("tf-final").value.trim(),
    };
  }

  async function submitTopicForm(e) {
    e.preventDefault();
    showMsg(byId("topic-form-error"), "");
    showMsg(byId("topic-form-success"), "", false);

    try {
      const res = await fetch("/api/topics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(collectFormData()),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Save failed");
      }
      showMsg(byId("topic-form-success"), "Topic saved!", false);
      hideDraftForm();
      byId("gen-topic-name").value = "";
      byId("generate-status").classList.add("hidden");
      if (window.reloadTopicsDropdown) await window.reloadTopicsDropdown();
      loadCustomTopics();
    } catch (err) {
      showMsg(byId("topic-form-error"), err.message);
    }
  }

  async function uploadTopicJson() {
    const file = byId("topic-upload").files[0];
    if (!file) return;

    showMsg(byId("upload-error"), "");
    showMsg(byId("upload-success"), "", false);

    const form = new FormData();
    form.append("file", file);

    try {
      const res = await fetch("/api/topics/upload", { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Upload failed");
      }
      const data = await res.json();
      showMsg(byId("upload-success"), `Uploaded ${data.count} topic(s).`, false);
      byId("topic-upload").value = "";
      if (window.reloadTopicsDropdown) await window.reloadTopicsDropdown();
      loadCustomTopics();
    } catch (err) {
      showMsg(byId("upload-error"), err.message);
    }
  }

  byId("nav-chat").addEventListener("click", () => switchView("chat"));
  byId("nav-topics").addEventListener("click", () => switchView("topics"));
  byId("generate-topic-btn").addEventListener("click", generateDraft);
  byId("topic-form").addEventListener("submit", submitTopicForm);
  byId("discard-draft-btn").addEventListener("click", hideDraftForm);
  byId("upload-btn").addEventListener("click", uploadTopicJson);

  byId("gen-topic-name").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      generateDraft();
    }
  });
})();

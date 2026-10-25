import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, TOOLS, date } from "./api";
import { SocraticConfig, ReflectionConfig, defaults } from "./ToolConfig";
import { Notice } from "./ui";
import LessonPreview from "./LessonPreview";
import ActivityRail from "./ActivityRail";
import ActivityIcon from "./ActivityIcon";
import { loadCourseContext } from "./courseContext";

const initial = {
  course_id: "",
  title: "",
  instructions: "",
  due: "",
  tool: "",
  config: {},
};
const ACTIVITY_TYPES = [
  "socratic",
  "reflections",
  "self-directed-learning",
  "debate",
  "aiducate",
];
const configFor = (tool) =>
  structuredClone(
    defaults[tool] ||
      (tool === "debate"
        ? { scenario: "", minimum_messages: 3 }
        : { prompt: "" }),
  );
function restoreDraft(item) {
  if (!item) return initial;
  const d = item.due_at ? new Date(item.due_at) : null;
  return {
    ...item,
    due: d
      ? new Date(d.getTime() - d.getTimezoneOffset() * 60000)
          .toISOString()
          .slice(0, 16)
      : "",
  };
}
const sdlReviewKey = (draft, selected) => JSON.stringify([
  draft.course_id, draft.title, [...selected].map(String).sort(),
  draft.config.prompt || "", draft.config.starting_point || "", draft.config.ending_point || "",
]);
const hasSdlReview = item => item?.tool === "self-directed-learning" && !!item.config?.learning_plan?.diagnostic_quiz?.length;
const restoredStage = item => item && (item.status !== "draft" || (hasSdlReview(item) &&
  (!item.config.learning_plan.review_input_key || item.config.learning_plan.review_input_key === sdlReviewKey(item, item.config.document_ids || [])))) ? 3 : 1;
export default function CreateActivity({
  initialActivity = null,
  initialContext = null,
}) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [draft, setDraft] = useState(() => restoreDraft(initialActivity));
  const [initializing, setInitializing] = useState(!initialActivity);
  const [courses, setCourses] = useState(
    initialContext ? [initialContext] : [],
  );
  const [files, setFiles] = useState([]);
  const [selected, setSelected] = useState(
    initialActivity?.config.document_ids || [],
  );
  const [search, setSearch] = useState("");
  const [stage, setStage] = useState(() => restoredStage(initialActivity));
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [pendingKeyword, setPendingKeyword] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const fileInput = useRef(null);
  const chatConfigs = useRef({});
  const settingsRef = useRef(null);
  const reviewRef = useRef(null);
  const feedbackRef = useRef(null);
  useEffect(() => {
    if (initialActivity && initialContext && initialActivity.id === id) return;
    // Saving a new draft already loaded this item; do not overwrite later chat selections.
    if (id && draft.id === id && courses.length) return;
    let active = true;
    setInitializing(true);
    const load = async () => {
      const item = id ? await api(`/platform/assignments/${id}`) : null;
      const context = await loadCourseContext(item?.course_id);
      if (!active) return;
      if (item && String(item.course_id) !== String(context.course_id))
        throw Error("Open this activity from its Canvas course.");
      setCourses([context]);
      if (!item) {
        setDraft((d) => ({ ...d, course_id: context.course_id }));
        return;
      }
      const d = item.due_at ? new Date(item.due_at) : null;
      setDraft({
        ...item,
        due: d
          ? new Date(d.getTime() - d.getTimezoneOffset() * 60000)
              .toISOString()
              .slice(0, 16)
          : "",
      });
      setSelected(item.config.document_ids || []);
      setStage(restoredStage(item));
    };
    load()
      .catch((e) => active && setError(e.message))
      .finally(() => active && setInitializing(false));
    return () => {
      active = false;
    };
  }, [id]);
  useEffect(() => {
    let active = true;
    setFiles([]);
    if (!draft.course_id) {
      setLoadingFiles(false);
      return;
    }
    setLoadingFiles(true);
    api(`/platform/courses/${draft.course_id}/documents`)
      .then((data) => {
        if (active) setFiles(data.files);
      })
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoadingFiles(false));
    return () => {
      active = false;
    };
  }, [draft.course_id]);
  const change = (key, value) => {
    const keepReview = hasSdlReview(draft) && ["title", "instructions", "due"].includes(key) &&
      (!draft.config.learning_plan.review_input_key || draft.config.learning_plan.review_input_key === sdlReviewKey(draft, selected));
    setDraft((d) => {
      const next = {...d, [key]: value};
      return keepReview ? {...next, config:{...d.config, learning_plan:{...d.config.learning_plan, review_input_key:sdlReviewKey(next,selected)}}} : next;
    });
    setStage(keepReview ? 3 : 1);
  };
  const setConfig = (value) => {
    setDraft((d) => ({ ...d, config: value }));
    setStage(2);
  };
  const chooseTool = (key) => {
    setPendingKeyword(false);
    chatConfigs.current[draft.tool] = draft.config;
    setDraft((d) => ({
      ...d,
      tool: key,
      config:
        d.tool === key
          ? d.config
          : structuredClone(chatConfigs.current[key] || configFor(key)),
    }));
    setStage(2);
    setNotice("");
  };
  const ready = !!draft.title.trim() && !!draft.course_id && !!draft.tool;
  const connected = draft.tool !== "aiducate";
  const frozen = draft.status && draft.status !== "draft";
  useEffect(() => {
    if (!draft.tool || busy || frozen) return;
    const clear = (event) => {
      const target = event.target;
      if (
        !(target instanceof Element) ||
        target.closest(
          ".activity-rail, .activity-settings, .activity-review, input, textarea, select, button, a, label",
        )
      )
        return;
      chatConfigs.current[draft.tool] = draft.config;
      setDraft((d) => ({ ...d, tool: "", config: {} }));
      setStage(1);
      setNotice("");
    };
    document.addEventListener("pointerdown", clear);
    return () => document.removeEventListener("pointerdown", clear);
  }, [draft.tool, draft.config, busy, frozen]);
  const run = async (fn) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const save = async (publish, quiet = false) => {
    const config =
      draft.tool === "debate"
        ? {
            document_ids: selected,
            scenario: draft.config.scenario || draft.title,
            opening_prompt: draft.config.opening_prompt || "",
            minimum_messages: draft.config.minimum_messages || 3,
          }
        : draft.tool === "self-directed-learning"
          ? {
              document_ids: selected,
              prompt: draft.config.prompt || "",
              custom_questions: [],
              starting_point: draft.config.starting_point || "",
              ending_point: draft.config.ending_point || "",
              learning_plan: draft.config.learning_plan || {},
            }
          : { ...draft.config, document_ids: selected };
    const payload = {
      course_id: draft.course_id,
      title: draft.title,
      instructions: draft.instructions,
      due_at: draft.due ? new Date(draft.due).toISOString() : null,
      tool: draft.tool,
      audience: "course",
      config,
    };
    const saved = await api(
      `/platform/assignments${draft.id ? `/${draft.id}` : ""}`,
      { method: draft.id ? "PUT" : "POST", body: payload },
    );
    setDraft((d) => ({ ...d, ...saved }));
    if (publish) {
      await api(`/platform/assignments/${saved.id}/publish`, {
        method: "POST",
      });
      navigate("/professor");
    } else if (!quiet) {
      navigate("/professor", { state: { notice: "Draft saved." } });
    }
    return saved;
  };
  const review = () =>
    run(async () => {
      if (draft.tool === "self-directed-learning") {
        if (!draft.config.starting_point?.trim() || !draft.config.ending_point?.trim())
          throw new Error("Define the starting point and ending point before reviewing SDL.");
        const saved = await save(false, true);
        const reviewKey = sdlReviewKey(draft, selected);
        const prepared = draft.config.learning_plan?.review_input_key === reviewKey
          ? {learning_plan: draft.config.learning_plan}
          : await api(`/platform/assignments/${saved.id}/prepare-sdl`, {method: "POST"});
        setDraft((d) => ({
          ...d,
          ...saved,
          config: { ...saved.config, learning_plan: {...prepared.learning_plan, review_input_key: reviewKey} },
        }));
      }
      setStage(3);
      setNotice(
        "Review the activity below, then select Publish activity to confirm.",
      );
      requestAnimationFrame(() =>
        reviewRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        }),
      );
    });
  const saveReview = async () => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await save(false, true);
      setNotice("Review changes saved.");
    } finally {
      setBusy(false);
    }
  };
  const confirmKeywords = () =>
    run(async () => {
      if (!draft.title.trim())
        throw new Error("Enter an activity title before confirming keywords.");
      if (pendingKeyword)
        throw new Error("Press + to add the keyword before confirming.");
      const saved = await save(false, true);
      const prepared = await api(
        `/platform/assignments/${saved.id}/keywords/confirm`,
        { method: "POST" },
      );
      setDraft((current) => ({
        ...current,
        ...saved,
        keyword_preparation: prepared,
      }));
      setNotice(
        "Keywords confirmed. Course materials are prepared; publish when ready.",
      );
    });
  const upload = async (event) => {
    const uploads = [...event.target.files];
    event.target.value = "";
    if (!uploads.length) return;
    setUploading(true);
    setBusy(true);
    setError("");
    setUploadError("");
    setNotice("");
    try {
      const body = new FormData();
      uploads.forEach((f) => body.append("files", f));
      const result = await api(
        `/platform/courses/${draft.course_id}/documents/upload`,
        { method: "POST", body },
      );
      const data = await api(`/platform/courses/${draft.course_id}/documents`);
      setFiles(data.files);
      const savedIds = new Set(data.files.map((file) => String(file.file_id)));
      if (!Array.isArray(result.files) || result.files.some((file) => !savedIds.has(String(file.file_id || file.id)))) {
        throw new Error("The upload request finished, but the document is not in this course's library. Please retry or contact the administrator.");
      }
      const uploadedIds = new Set(result.files.map((file) => String(file.file_id || file.id)));
      setSelected((current) => [
        ...new Set([
          ...current,
          ...data.files
            .filter((file) => uploadedIds.has(String(file.file_id)) && file.document_id)
            .map((file) => file.document_id),
        ]),
      ]);
      setStage(1);
      setNotice("Documents uploaded and ready to select.");
    } catch (e) {
      setUploadError(e.message);
    } finally {
      setUploading(false);
      setBusy(false);
    }
  };
  const deleteDocument = (file) => {
    if (
      !window.confirm(
        `Delete ${file.filename} from this course? Published assignments keep their saved copy.`,
      )
    )
      return;
    run(async () => {
      await api(
        `/courses/${draft.course_id}/documents/${file.file_id}`,
        { method: "DELETE" },
      );
      setFiles((current) =>
        current.filter((item) => item.file_id !== file.file_id),
      );
      if (file.document_id)
        setSelected((current) =>
          current.filter((documentId) => documentId !== file.document_id),
        );
      setDraft((current) => ({
        ...current,
        keyword_preparation: null,
      }));
      setStage(1);
      setNotice(`${file.filename} was deleted.`);
    });
  };
  if (initializing)
    return (
      <>
        <Link className="back" to="/professor">
          ← All assignments
        </Link>
        <p role="status">
          {id ? "Loading saved activity…" : "Opening activity creation…"}
        </p>
      </>
    );
  const publishActivity = () => {
    const missing = [];
    if (!draft.title.trim()) missing.push("Enter an activity title.");
    if (!draft.course_id)
      missing.push(
        "The Canvas course context is missing. Reopen the tool from your course.",
      );
    if (!draft.tool) missing.push("Select an activity type.");
    if (draft.tool === "socratic" && pendingKeyword)
      missing.push("Press + to add the typed keyword before continuing.");
    if (
      ["socratic", "self-directed-learning"].includes(draft.tool) &&
      !selected.length
    )
      missing.push(
        "Select at least one indexed course document or upload course materials.",
      );
    if (
      draft.tool === "debate" &&
      (draft.config.scenario || draft.title).trim().length < 10
    )
      missing.push("Enter a Debate scenario of at least 10 characters.");
    if (draft.tool === "reflections") {
      if (draft.config.module_type === "milestone_based") {
        if (!draft.config.milestone_prompt?.trim())
          missing.push("Enter the milestone reflection prompt.");
        if (!draft.config.historical_data?.trim())
          missing.push("Upload the historical CSV for milestone reflections.");
      } else if (!(draft.config.sub_topics || []).some((topic) => topic.trim()))
        missing.push("Add at least one reflection sub-topic.");
    }
    if (draft.tool === "aiducate")
      missing.push(
        "AIducate needs a backend connection before publishing. You can save a draft.",
      );
    if (missing.length) {
      setError(missing.join(" "));
      setNotice("");
      requestAnimationFrame(() => {
        feedbackRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
        feedbackRef.current?.focus({ preventScroll: true });
      });
      return;
    }
    if (stage === 3) run(() => save(true));
    else review();
  };
  const course = courses.find((c) => c.course_id === draft.course_id);
  return (
    <>
      <Link className="back" to="/professor">
        ← All assignments
      </Link>
      <div className="page-heading">
        <div>
          <p className="context">Professor studio</p>
          <h1>Assignment Configuration</h1>
          <p>
            Confirm the Canvas assignment details, add materials, choose an
            activity, then review and publish.
          </p>
        </div>
      </div>
      <div ref={feedbackRef} tabIndex={-1}>
        <Notice error={error} />
        <Notice>{notice}</Notice>
      </div>
      <fieldset className="editor-fieldset" disabled={busy || frozen}>
        <section className="panel">
          <h2>Activity details</h2>
          <div className="activity-title-date-row">
            <label>
              Assignment title
              <input
                maxLength={200}
                value={draft.title}
                onChange={(e) => change("title", e.target.value)}
                placeholder="Enter activity title"
              />
            </label>
            <label>
              Due date
              <input
                type="datetime-local"
                value={draft.due}
                onInput={(e) => change("due", e.currentTarget.value)}
                onChange={(e) => change("due", e.target.value)}
              />
            </label>
          </div>
          <p className="help">
            Canvas assignment launches apply the assignment title and due date
            automatically. You can enter them here for assignments created
            directly in ClubALL.
          </p>
          <label>
            Description
            <textarea
              rows={4}
              value={draft.instructions}
              onChange={(e) => change("instructions", e.target.value)}
              placeholder="Describe the activity and what students should do."
            />
          </label>
        </section>
        <section className="panel">
          <h2>Course materials</h2>
          <div className="activity-material-heading">
            <h3>Existing documents</h3>
            <button
              type="button"
              disabled={!draft.course_id || busy || uploading}
              onClick={() => fileInput.current.click()}
            >
              {uploading ? "Processing documents…" : "Upload new documents"}
            </button>
            <input
              ref={fileInput}
              type="file"
              multiple
              accept=".txt,.md,.pdf,.tex,.latex,.html,.htm,.ppt,.pptx,.docx"
              hidden
              onChange={upload}
            />
          </div>
          <Notice error={uploadError} />
          <label>
            Search documents
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by document name"
            />
          </label>
          <div
            className="activity-document-list"
            aria-label="Existing documents"
          >
            {loadingFiles ? (
              <p role="status">Loading documents…</p>
            ) : (
              files
                .filter((f) =>
                  f.filename.toLowerCase().includes(search.toLowerCase()),
                )
                .sort((a, b) => a.filename.localeCompare(b.filename))
                .map((f) => (
                  <div className="activity-document-row" key={f.file_id}>
                    <label className="check">
                      <input
                        type="checkbox"
                        disabled={!f.document_id}
                        checked={selected.includes(f.document_id)}
                        onChange={(e) => {
                          setSelected((s) =>
                            e.target.checked
                              ? [...s, f.document_id]
                              : s.filter((v) => v !== f.document_id),
                          );
                          setStage(1);
                        }}
                      />
                      <span>
                        {f.filename}
                        {!f.document_id && <small>Not indexed</small>}
                      </span>
                      <small>{Math.round((f.file_size || 0) / 1024)} KB</small>
                    </label>
                    <button
                      type="button"
                      className="quiet activity-document-delete"
                      aria-label={`Delete ${f.filename}`}
                      onClick={() => deleteDocument(f)}
                    >
                      Delete
                    </button>
                  </div>
                ))
            )}
            {!loadingFiles && !files.length && (
              <p className="help">
                {draft.course_id
                  ? "No documents yet. Upload course materials to get started."
                  : "Loading course materials from your Canvas context."}
              </p>
            )}
          </div>
          <div className="activity-material-heading">
            <h3>Selected documents ({selected.length})</h3>
            {selected.length > 0 && (
              <button
                className="quiet"
                onClick={() => {
                  setSelected([]);
                  setStage(1);
                }}
              >
                Clear all
              </button>
            )}
          </div>
          {selected.length ? (
            <ul className="activity-selected-list">
              {files
                .filter((f) => selected.includes(f.document_id))
                .map((f) => (
                  <li key={f.file_id}>
                    {f.filename}
                    <button
                      className="quiet"
                      aria-label={`Remove ${f.filename}`}
                      onClick={() => {
                        setSelected((s) =>
                          s.filter((v) => v !== f.document_id),
                        );
                        setStage(1);
                      }}
                    >
                      ×
                    </button>
                  </li>
                ))}
            </ul>
          ) : (
            <p className="help">No documents selected.</p>
          )}
        </section>
        <section className="panel">
          <h2>Select activity</h2>
          <ActivityRail label="activity choices" className="activity-rail">
            {ACTIVITY_TYPES.map((key, index) => {
              const tool = TOOLS[key];
              return (
                <button
                  key={key}
                  aria-pressed={draft.tool === key}
                  style={{ "--tool-color": tool.color }}
                  className={`tool-card activity-choice ${draft.tool === key ? "is-selected" : ""}`}
                  onClick={() => chooseTool(key)}
                >
                  <span className="tool-card-topline">
                    <span className="tool-mark">
                      <ActivityIcon tool={key} />
                    </span>
                    <span className="tool-step" aria-hidden="true">
                      0{index + 1}
                    </span>
                  </span>
                  <span className="tool-mode">
                    {
                      {
                        socratic: "Guide",
                        reflections: "Reflect",
                        "self-directed-learning": "Learn",
                        debate: "Discuss",
                        aiducate: "Explore",
                      }[key]
                    }
                  </span>
                  <strong>{tool.name}</strong>
                  <span className="activity-choice-description">
                    {tool.description}
                  </span>
                </button>
              );
            })}
          </ActivityRail>
        </section>
        {draft.tool && (
          <section className="panel activity-settings" ref={settingsRef}>
            <h2>{TOOLS[draft.tool].name} settings</h2>
            {draft.tool === "socratic" ? (
              <SocraticConfig
                value={{ ...draft.config, document_ids: selected }}
                onChange={setConfig}
                courseId={draft.course_id}
                frozen={frozen}
                hideConversation
                hideDocuments
                documents={files}
                onPendingKeywordChange={setPendingKeyword}
                keywordPreparation={draft.keyword_preparation}
                onConfirmKeywords={confirmKeywords}
                onInvalidateKeywordPreparation={() =>
                  setDraft((current) => ({
                    ...current,
                    keyword_preparation: null,
                  }))
                }
                onMaterialsChange={({ files: nextFiles }) => {
                  setFiles(nextFiles);
                  const available = new Set(
                    nextFiles
                      .filter((file) => file.document_id)
                      .map((file) => file.document_id),
                  );
                  setSelected((current) =>
                    current.filter((documentId) =>
                      available.has(documentId),
                    ),
                  );
                }}
              />
            ) : draft.tool === "reflections" ? (
              <ReflectionConfig value={draft.config} onChange={setConfig} />
            ) : draft.tool === "self-directed-learning" ? (
              <>
                <label>
                  Learning focus
                  <textarea
                    rows={3}
                    value={draft.config.prompt || ""}
                    onChange={(e) =>
                      setConfig({ ...draft.config, prompt: e.target.value })
                    }
                    placeholder="What should students learn from these materials?"
                  />
                </label>
                <label>Starting point<textarea maxLength={2000} rows={3} value={draft.config.starting_point || ""} onChange={e=>setConfig({...draft.config,starting_point:e.target.value})} placeholder="What should students already know?" /></label>
                <label>Ending point<textarea maxLength={4000} rows={3} value={draft.config.ending_point || ""} onChange={e=>setConfig({...draft.config,ending_point:e.target.value})} placeholder="What should students be able to do by the end?" /></label>
              </>
            ) : (
              <>
                <label>
                  {draft.tool === "debate"
                    ? "Debate topic or scenario"
                    : "Activity instructions"}
                  <textarea
                    rows={4}
                    value={draft.config.scenario || draft.config.prompt || ""}
                    onChange={(e) =>
                      setConfig({
                        ...draft.config,
                        [draft.tool === "debate" ? "scenario" : "prompt"]:
                          e.target.value,
                      })
                    }
                  />
                </label>
                <p className="help">
                  {draft.tool === "aiducate"
                    ? "AIducate has no backend yet. You can save a draft."
                    : draft.tool === "self-directed-learning"
                      ? "Select course materials above. Review activity generates the adaptive lesson for you to check before publishing."
                      : "Students discuss this scenario with the Debate chatbot."}
                </p>
              </>
            )}
          </section>
        )}
        <div className="editor-actions">
          <button
            className="secondary"
            disabled={!ready || pendingKeyword}
            onClick={() => run(() => save(false))}
          >
            Save draft
          </button>
          <button
            className={draft.tool === "self-directed-learning" ? "" : "secondary"}
            disabled={
              !ready ||
              pendingKeyword ||
              (draft.tool === "self-directed-learning" && !selected.length)
            }
            onClick={review}
          >
            {busy ? "Preparing…" : "Review activity"}
          </button>
          {draft.tool !== "self-directed-learning" && <button onClick={publishActivity}>Publish activity</button>}
        </div>
        {!connected && (
          <p className="help">
            AIducate is available for draft testing; publishing needs its
            backend connection.
          </p>
        )}
        {draft.tool === "self-directed-learning" && !selected.length && (
          <p className="help">
            Select course materials to review or publish an SDL lesson.
          </p>
        )}
        {stage === 3 && (
          <section className="panel activity-review" ref={reviewRef}>
            <h2>Review and publish</h2>
            <dl className="activity-summary">
              <dt>Activity</dt>
              <dd>{draft.title}</dd>
              <dt>Course</dt>
              <dd>
                {course?.course_code} — {course?.title}
              </dd>
              <dt>Due date</dt>
              <dd>{draft.due ? date(draft.due) : "No due date"}</dd>
              <dt>Description</dt>
              <dd>{draft.instructions || "No description"}</dd>
              <dt>Chat</dt>
              <dd>{TOOLS[draft.tool].name}</dd>
              <dt>Materials</dt>
              <dd>{selected.length} selected documents</dd>
              <dt>Assigned to</dt>
              <dd>All currently enrolled students</dd>
            </dl>
            {draft.tool === "self-directed-learning" &&
              draft.config.learning_plan && (
                <LessonPreview plan={draft.config.learning_plan} onSave={saveReview} onChange={plan=>setDraft(d=>{
                  const next = {...d,config:{...d.config,starting_point:plan.starting_point,ending_point:plan.ending_point}};
                  return {...next,config:{...next.config,learning_plan:{...plan,review_input_key:sdlReviewKey(next,selected)}}};
                })} />
              )}
            {draft.tool === "self-directed-learning" && <div className="editor-actions"><button className="secondary" disabled={!ready} onClick={()=>run(()=>save(false))}>Save draft</button><button onClick={publishActivity}>Publish activity</button></div>}
            <p className="help">
              Publishing freezes the activity settings and the current student
              recipient list.
            </p>
            {!connected && (
              <Notice>
                This chat must be connected before publishing. Your draft can be
                saved now.
              </Notice>
            )}
            {draft.tool === "socratic" && !selected.length && (
              <p className="help">
                Select at least one indexed document before publishing Socratic.
              </p>
            )}
          </section>
        )}
      </fieldset>
    </>
  );
}

import { useEffect, useRef, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { api, TOOLS, date, label } from "./api";
import { Notice, Badge } from "./ui";
import DebateConfig from "./DebateConfig";
import ChatbotPicker from "./ChatbotPicker";
import {
  SocraticConfig,
  ReflectionConfig,
  TutorConfig,
  defaults,
} from "./ToolConfig";

function localDate(value) {
  if (!value) return "";
  const d = new Date(value);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}

export default function AssignmentEditor() {
  const { tool, id } = useParams(),
    [query] = useSearchParams(),
    navigate = useNavigate();
  useEffect(() => {
    const previousTitle = document.title;
    document.title = "CourseLab · Chatbot configuration";
    return () => {
      document.title = previousTitle;
    };
  }, []);
  const [item, setItem] = useState(null);
  const savedConfigs = useRef({});
  const [pendingKeyword, setPendingKeyword] = useState(false);
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setItem(null);
    setError("");
    const load =
      id === "new"
        ? Promise.resolve({
            course_id: query.get("course") || "",
            tool: tool || null,
            title: "",
            instructions: "",
            due_at: null,
            audience: "course",
            recipient_ids: [],
            config: structuredClone(defaults[tool] || {}),
            status: "draft",
          })
        : api(`/platform/assignments/${id}`);
    load
      .then((data) => {
        if (active) {
          savedConfigs.current = {};
          setItem(data);
        }
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [id, tool]);
  const change = (key, value) => setItem((prev) => ({ ...prev, [key]: value }));
  const config = (value) => change("config", value);
  const chooseChatbot = (nextTool) => {
    setPendingKeyword(false);
    setItem((previous) => {
      if (previous.tool === nextTool) return previous;
      if (previous.tool) savedConfigs.current[previous.tool] = previous.config;
      return {
        ...previous,
        tool: nextTool,
        config:
          savedConfigs.current[nextTool] || structuredClone(defaults[nextTool]),
      };
    });
  };
  const perform = async (fn) => {
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
  async function save(publish = false, confirmKeywords = false) {
    if (confirmKeywords && !item.title.trim())
      throw new Error("Enter an assignment title before confirming keywords.");
    if (item.tool === "socratic" && pendingKeyword)
      throw new Error("Press + to add the keyword before saving.");
    const payload = Object.fromEntries(
      [
        "course_id",
        "tool",
        "title",
        "instructions",
        "due_at",
        "audience",
        "recipient_ids",
        "config",
      ].map((k) => [k, item[k] ?? (k === "recipient_ids" ? [] : null)]),
    );
    const saved = await api(
      `/platform/assignments${id === "new" ? "" : `/${id}`}`,
      { method: id === "new" ? "POST" : "PUT", body: payload },
    );
    setItem({ ...item, ...saved });
    let publishSucceeded = false;
    try {
      if (confirmKeywords) {
        const prepared = await api(
          `/platform/assignments/${saved.id}/keywords/confirm`,
          { method: "POST" },
        );
        setItem({ ...item, ...saved, keyword_preparation: prepared });
        setNotice(
          "Keywords confirmed. Course materials are prepared; publish when ready.",
        );
      } else if (publish) {
        await api(`/platform/assignments/${saved.id}/publish`, {
          method: "POST",
        });
        publishSucceeded = true;
        navigate(`/professor/tools/${saved.tool}`, { replace: true });
      } else setNotice("Draft saved.");
    } finally {
      // Preserve the saved draft on publish failure, without racing the detail fetch.
      if (
        !publishSucceeded &&
        (id === "new" || (tool && saved.tool !== tool))
      )
        navigate(`/professor/assignments/${saved.id}`, {
          replace: true,
        });
    }
  }
  if (tool && !TOOLS[tool]) return <Notice error="Unknown tool." />;
  if (!item)
    return (
      <>
        <Link to={tool ? `/professor/tools/${tool}` : "/professor"}>
          Back to chat dashboard
        </Link>
        <Notice error={error} />
        {!error && <p>Loading assignment…</p>}
      </>
    );
  const frozen = item.status !== "draft";
  const prepared = item.keyword_preparation;
  const keywordsConfirmed =
    prepared?.ready &&
    prepared.course_id === item.course_id &&
    JSON.stringify(prepared.keywords) ===
      JSON.stringify(item.config?.keywords || []) &&
    JSON.stringify([...(prepared.document_ids || [])].sort()) ===
      JSON.stringify([...(item.config?.document_ids || [])].sort());
  const Config = {
    socratic: SocraticConfig,
    debate: DebateConfig,
    reflections: ReflectionConfig,
    "student-agent": TutorConfig,
  }[item.tool];
  return (
    <>
      <Link
        className="back"
        to={item.tool ? `/professor/tools/${item.tool}` : "/professor"}
      >
        ← Chat dashboard
      </Link>
      <div className="page-heading">
        <div>
          <p className="context">Assignment setup</p>
          <h1>Chatbot configuration</h1>
          <p>{id === "new" ? "A new learning assignment" : item.title}</p>
          <p>
            {frozen
              ? "Published settings are frozen. Duplicate this assignment to use different settings."
              : "Choose a chatbot, configure the learning experience, then publish."}
          </p>
        </div>
        <Badge value={item.status} />
      </div>
      <Notice error={error} />
      <Notice>{notice}</Notice>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          perform(() => save(false));
        }}
      >
        <fieldset disabled={busy || frozen} className="editor-fieldset">
          <section className="panel assignment-details-panel">
            <h2>Assignment details</h2>
            <label>
              Title
              <input
                required
                maxLength={200}
                value={item.title}
                onChange={(e) => change("title", e.target.value)}
                placeholder="e.g. Week 3: Requirements in practice"
              />
            </label>
            <label>
              Instructions
              <textarea
                rows={4}
                value={item.instructions}
                onChange={(e) => change("instructions", e.target.value)}
                placeholder="What should students focus on?"
              />
            </label>
            <label>
              Due date (your local time)
              <input
                type="datetime-local"
                value={localDate(item.due_at)}
                onChange={(e) =>
                  change(
                    "due_at",
                    e.target.value
                      ? new Date(e.target.value).toISOString()
                      : null,
                  )
                }
              />
            </label>
            <p className="help">
              Due dates are shown as guidance; students may continue after the
              due date.
            </p>
            <ChatbotPicker value={item.tool} onChange={chooseChatbot} />
          </section>
        </fieldset>
        <fieldset
          disabled={busy || (frozen && item.tool !== "socratic")}
          className="editor-fieldset"
        >
          {Config ? (
            <section
              className="panel tool-config"
              aria-label={`${TOOLS[item.tool].name} settings`}
            >
              <h2>{TOOLS[item.tool].name} settings</h2>
              <Config
                value={item.config}
                onChange={config}
                courseId={item.course_id}
                frozen={frozen}
                onPendingKeywordChange={setPendingKeyword}
                keywordPreparation={item.keyword_preparation}
                onConfirmKeywords={() => perform(() => save(false, true))}
                onInvalidateKeywordPreparation={() =>
                  change("keyword_preparation", null)
                }
              />
            </section>
          ) : (
            <p className="notice">
              Choose a chatbot above to see its settings.
            </p>
          )}
        </fieldset>
        <div className="editor-actions">
          {!frozen ? (
            <>
              <button
                className="secondary"
                type="submit"
                disabled={busy || pendingKeyword}
              >
                {busy ? "Saving…" : "Save draft"}
              </button>
              <button
                type="button"
                disabled={
                  busy ||
                  pendingKeyword ||
                  !item.title.trim() ||
                  !item.course_id ||
                  !item.tool ||
                  (item.tool === "socratic" &&
                    item.config?.keywords?.length > 0 &&
                    !keywordsConfirmed)
                }
                onClick={() => perform(() => save(true))}
              >
                Publish assignment
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  perform(async () => {
                    const copy = await api(
                      `/platform/assignments/${id}/duplicate`,
                      { method: "POST" },
                    );
                    navigate(`/professor/assignments/${copy.id}`);
                  })
                }
              >
                Duplicate as draft
              </button>
            </>
          )}
        </div>
      </form>
      {frozen && (
        <section className="section">
          <h2>Student progress</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Progress</th>
                  <th>Completed</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {(item.students || []).map((s) => (
                  <tr key={s.student_id}>
                    <td>{s.display_name || s.username}</td>
                    <td>
                      <Badge value={s.progress} />
                    </td>
                    <td>{s.completed_at ? date(s.completed_at) : "—"}</td>
                    <td>
                      {s.result ? (
                        <details>
                          <summary>View result</summary>
                          <pre>{JSON.stringify(s.result, null, 2)}</pre>
                        </details>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}

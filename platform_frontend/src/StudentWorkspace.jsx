import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Markdown from "react-markdown";
import { api, date, TOOLS } from "./api";
import { Badge, Notice } from "./ui";

function nextQuestion(messages) {
  const answer = [...(messages || [])]
    .reverse()
    .find((item) => item.role === "assistant")?.content;
  if (!answer) return "";
  const sentences = answer.split(/(?<=[.!?])\s+/).filter(Boolean);
  return (
    [...sentences].reverse().find((sentence) => sentence.trim().endsWith("?")) ||
    answer
  ).trim();
}

function EmphasizedText({ text, keywords = [] }) {
  const terms = keywords
    .map((keyword) => keyword.trim())
    .filter(Boolean)
    .sort((left, right) => right.length - left.length);
  if (!terms.length) return text;
  const escaped = terms.map((term) =>
    term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
  );
  const matcher = new RegExp(`(${escaped.join("|")})`, "gi");
  return text.split(matcher).map((part, index) =>
    terms.some((term) => term.toLowerCase() === part.toLowerCase()) ? (
      <strong key={index}>{part}</strong>
    ) : (
      part
    ),
  );
}

function Result({ result }) {
  if (!result) return null;
  const evaluation = result.evaluation;
  return (
    <section className="result">
      <h2>Assignment complete</h2>
      <p>Your work has been saved and your professor can see your progress.</p>
      {evaluation && (
        <>
          <div className="result-stats">
            <span>
              Reflection depth{" "}
              <strong>{evaluation.reflection_depth_score}</strong>
            </span>
            <span>
              Confidence <strong>{evaluation.confidence_level}</strong>
            </span>
            <span>
              Engagement <strong>{evaluation.engagement_score}</strong>
            </span>
          </div>
          {[
            ["Topics covered", evaluation.topics_covered],
            ["Topics to revisit", evaluation.missing_topics],
            ["Misconceptions to review", evaluation.misconceptions],
          ].map(([title, items]) =>
            items?.length ? (
              <div key={title}>
                <h3>{title}</h3>
                <ul>
                  {items.map((x, i) => (
                    <li key={i}>{x}</li>
                  ))}
                </ul>
              </div>
            ) : null,
          )}
        </>
      )}
      {result.similar?.length > 0 && (
        <>
          <h3>Related experiences</h3>
          {result.similar.map((item, i) => (
            <article className="related" key={i}>
              <p>
                <strong>Challenge:</strong> {item.challenge}
              </p>
              <p>
                <strong>Solution:</strong> {item.solution}
              </p>
            </article>
          ))}
        </>
      )}
    </section>
  );
}

export default function StudentWorkspace() {
  const { id } = useParams();
  const [assignment, setAssignment] = useState(null),
    [attempt, setAttempt] = useState(null),
    [message, setMessage] = useState("");
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [loaded, setLoaded] = useState(false),
    [generationStartedAt, setGenerationStartedAt] = useState(null),
    [generationSeconds, setGenerationSeconds] = useState(0),
    [lastGenerationSeconds, setLastGenerationSeconds] = useState(null),
    [selectedEvidence, setSelectedEvidence] = useState(null);
  const endRef = useRef(null),
    pending = useRef(null);
  useEffect(() => {
    let active = true;
    setLoaded(false);
    setAssignment(null);
    setAttempt(null);
    pending.current = null;
    Promise.all([
      api(`/platform/assignments/${id}`),
      api(`/platform/assignments/${id}/attempt`),
    ])
      .then(([a, t]) => {
        if (active) {
          setAssignment(a);
          setAttempt(t);
          setLoaded(true);
        }
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [id]);
  useEffect(() => {
    if (attempt)
      endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [attempt?.messages?.length]);
  useEffect(() => {
    if (!generationStartedAt) return;
    const update = () =>
      setGenerationSeconds((Date.now() - generationStartedAt) / 1000);
    update();
    const timer = window.setInterval(update, 100);
    return () => window.clearInterval(timer);
  }, [generationStartedAt]);
  useEffect(() => {
    setSelectedEvidence(null);
  }, [attempt?.engine_state?.sources]);
  useEffect(() => {
    if (assignment?.tool !== "reflections") return;
    let active = true;
    const refresh = () => api(`/platform/assignments/${id}/attempt`)
      .then((value) => { if (active) setAttempt(value); })
      .catch((e) => { if (active) setError(e.message); });
    window.addEventListener("focus", refresh);
    return () => { active = false; window.removeEventListener("focus", refresh); };
  }, [id, assignment?.tool]);
  async function perform(path, body) {
    setBusy(true);
    setError("");
    try {
      const result = await api(`/platform/assignments/${id}/${path}`, {
        method: "POST",
        body,
      });
      setAttempt(result);
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function send(e) {
    e.preventDefault();
    if (!message.trim() || busy) return;
    const text = message.trim();
    if (!pending.current || pending.current.message !== text)
      pending.current = { message: text, request_id: crypto.randomUUID() };
    const startedAt = Date.now();
    setGenerationStartedAt(startedAt);
    setGenerationSeconds(0);
    setLastGenerationSeconds(null);
    const sent = await perform("messages", pending.current);
    setLastGenerationSeconds(sent ? (Date.now() - startedAt) / 1000 : null);
    setGenerationStartedAt(null);
    if (sent) {
      setMessage("");
      pending.current = null;
    }
  }
  if (!loaded)
    return (
      <>
        <Link to="/student">← My assignments</Link>
        <Notice error={error} />
        {!error && <p>Opening assignment…</p>}
      </>
    );
  const tool = TOOLS[assignment.tool],
    completed = attempt?.status === "completed",
    state = attempt?.engine_state || {};
  const socratic = state.socratic || {};
  const thinkingStep =
    assignment.tool === "socratic"
      ? socratic.next_thinking_step || nextQuestion(attempt?.messages)
      : "";
  const keywords = socratic.keywords?.length
    ? socratic.keywords
    : socratic.active_concept
      ? [socratic.active_concept]
      : [];
  const milestone =
    assignment.student_config?.module_type === "milestone_based";
  return (
    <>
      <Link className="back" to="/student">
        ← My assignments
      </Link>
      <div className="page-heading">
        <div>
          <p className="context">{tool.name}</p>
          <h1>{assignment.title}</h1>
          <p>
            {assignment.due_at
              ? `Due ${date(assignment.due_at)}`
              : "Work at your own pace"}
          </p>
        </div>
        <Badge value={attempt?.status || "not_started"} />
      </div>
      <Notice error={error} />
      <div className="workspace-grid">
        <aside className="assignment-info">
          <h2>Your assignment</h2>
          <div className="prose">
            <Markdown>
              {assignment.instructions ||
                "Follow the prompts in this learning activity."}
            </Markdown>
          </div>
          {assignment.tool === "socratic" && (
            <p className="help">
              Send at least {assignment.student_config.minimum_messages}{" "}
              message(s), then mark the assignment complete.
            </p>
          )}
          {assignment.tool === "reflections" && (
            <p className="help">
              {milestone
                ? "Submit your milestone reflection to complete this assignment."
                : "Reflect on the prompts, then finish the session to receive your evaluation."}
            </p>
          )}
          {assignment.tool === "student-agent" && (
            <>
              <h3>{assignment.student_config.topic_name}</h3>
              <ul className="resources">
                {assignment.student_config.resources.map((r, i) => (
                  <li key={i}>
                    <a href={r.url} target="_blank" rel="noreferrer">
                      {r.title}
                    </a>
                  </li>
                ))}
              </ul>
              <p className="help">
                Work through reading, discussion, and practice. Complete the
                assignment at wrap-up.
              </p>
            </>
          )}
          {attempt && !completed && assignment.tool !== "reflections" && (
            <>
              <p className="saved-note">
                Progress is saved after each response. You can return to your
                dashboard at any time.
              </p>
              {!milestone && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => perform("complete")}
                >
                  {assignment.tool === "reflections"
                    ? "Finish reflection & evaluate"
                    : "Mark assignment complete"}
                </button>
              )}
            </>
          )}
        </aside>
        <section className="chat-panel" aria-label={`${tool.name} assignment`}>
          <div className="chat-heading">
            <span className="tool-mark" style={{ "--tool-color": tool.color }}>
              {tool.short}
            </span>
            <div>
              <h2>{tool.name}</h2>
              <p>
                {state.phase_label ||
                  (state.total_questions
                    ? `Question ${Math.min((state.question_index || 0) + 1, state.total_questions)} of ${state.total_questions}`
                    : tool.description)}
              </p>
            </div>
          </div>
          {assignment.tool === "reflections" ? (
            <div className="start-state">
              <h2>{completed ? "Your reflection is complete." : "Ready when you are."}</h2>
              <p>Open Reflections in a new tab. Your professor’s settings and saved progress are loaded automatically.</p>
              <a className="button" href={`/platform/reflections.html?assignment=${encodeURIComponent(id)}`} target="_blank" rel="noopener noreferrer">
                {completed ? "View reflection results" : attempt ? "Resume assignment" : "Start assignment"}
              </a>
            </div>
          ) : !attempt ? (
            <div className="start-state">
              <h2>Ready when you are.</h2>
              <p>
                Your professor’s settings are already loaded. Start to open your
                learning session.
              </p>
              <button disabled={busy} onClick={() => perform("start")}>
                {busy ? "Starting…" : "Start assignment"}
              </button>
            </div>
          ) : (
            <>
              <div className="messages" aria-live="polite" aria-busy={busy}>
                {attempt.messages.map((m, i) => (
                  <article className={`message ${m.role}`} key={i}>
                    <span className="message-author">
                      {m.role === "user" ? "You" : tool.name}
                    </span>
                    <div className="prose">
                      <Markdown>{m.content}</Markdown>
                    </div>
                  </article>
                ))}
                {busy && (
                  <p className="working" role="status">
                    {generationStartedAt
                      ? `Generating response · ${generationSeconds.toFixed(1)} s`
                      : "Working on your response…"}
                  </p>
                )}
                <div ref={endRef} />
              </div>
              {assignment.tool === "socratic" && thinkingStep && (
                <section className="thinking-support" aria-label="Learning support">
                  {lastGenerationSeconds !== null && (
                    <p className="generation-time">
                      Response generated in {lastGenerationSeconds.toFixed(1)} seconds
                    </p>
                  )}
                  <div className="thinking-step">
                    <span>Your next thinking step</span>
                    <p>
                      <EmphasizedText text={thinkingStep} keywords={keywords} />
                    </p>
                  </div>
                  {state.sources?.length > 0 && (
                    <div className="evidence-links">
                      <h3>Evidence from your course documents</h3>
                      <div>
                        {state.sources.map((source, index) => (
                          <button
                            type="button"
                            className="evidence-link"
                            key={source.chunk_id || index}
                            aria-pressed={
                              selectedEvidence?.chunk_id === source.chunk_id
                            }
                            onClick={() => setSelectedEvidence(source)}
                          >
                            {source.title}
                            {source.page_number
                              ? ` · page ${source.page_number}`
                              : ""}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  {selectedEvidence && (
                    <article className="evidence-context">
                      <span>Evidence context</span>
                      <h3>{selectedEvidence.title}</h3>
                      <p>
                        <EmphasizedText
                          text={selectedEvidence.text}
                          keywords={keywords}
                        />
                      </p>
                      <small>
                        {selectedEvidence.page_number
                          ? `Page ${selectedEvidence.page_number} · `
                          : ""}
                        Passage {selectedEvidence.chunk_id}
                      </small>
                    </article>
                  )}
                </section>
              )}
              {!completed && assignment.tool === "student-agent" && (
                <div className="tutor-controls">
                  {state.nav?.map((n) => (
                    <button
                      key={n.id}
                      disabled={busy || !n.unlocked || n.current}
                      className="secondary compact"
                      onClick={() =>
                        perform("actions", {
                          action: "navigate",
                          value: n.id,
                          request_id: crypto.randomUUID(),
                        })
                      }
                    >
                      {n.label}
                    </button>
                  ))}
                  {state.awaiting_scenario && (
                    <div>
                      <p>Choose a practice scenario:</p>
                      {state.practice_options?.map((s) => (
                        <button
                          className="secondary compact"
                          key={s}
                          disabled={busy}
                          onClick={() =>
                            perform("actions", {
                              action: "scenario",
                              value: s,
                              request_id: crypto.randomUUID(),
                            })
                          }
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
              {completed ? (
                <Result result={attempt.result || {}} />
              ) : (
                <form className="composer" onSubmit={send}>
                  <label className="sr-only" htmlFor="reply">
                    Your {milestone ? "reflection" : "message"}
                  </label>
                  <textarea
                    id="reply"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    disabled={busy}
                    rows={milestone ? 7 : 3}
                    maxLength={20000}
                    placeholder={
                      milestone
                        ? "Write your reflection…"
                        : "Share your thinking…"
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                        send(e);
                      }
                    }}
                  />
                  <div>
                    <span className="help">
                      {milestone
                        ? "Submitting completes this assignment."
                        : "Ctrl / ⌘ + Enter to send"}
                    </span>
                    <button disabled={busy || !message.trim()}>
                      {milestone ? "Submit reflection" : "Send message"}
                    </button>
                  </div>
                </form>
              )}
            </>
          )}
        </section>
      </div>
    </>
  );
}

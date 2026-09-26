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

function inferQuestionType(content) {
  const text = String(content || "").toLowerCase();
  if (/\b(?:reflect|understanding changed|would you revise|first response)\b/.test(text))
    return "Reflection";
  if (/\b(?:synthesi|combine|bring together|overall explanation)\b/.test(text))
    return "Synthesis";
  if (/\b(?:apply|application|new example|new domain)\b/.test(text))
    return "Application";
  if (/\b(?:compare|comparison|difference|distinction)\b/.test(text))
    return "Comparison";
  if (/\b(?:evidence|support|source|detail|according|how do you know)\b/.test(text))
    return "Evidence";
  if (/\b(?:assum|belie|thought|taking for granted)\b/.test(text))
    return "Assumption";
  if (/\b(?:impact|implication|consequence|what happens|lead to|affect)\b/.test(text))
    return "Implication";
  if (/\b(?:alternative|another|different perspective|other viewpoint|instead)\b/.test(text))
    return "Alternative viewpoint";
  return "Clarification";
}

function questionRationale(type) {
  return (
    {
      Clarification:
        "This question helps make the idea precise before the conversation moves deeper.",
      Assumption:
        "This question surfaces an underlying belief that may be shaping your conclusion.",
      Evidence:
        "This question asks you to connect your claim to support from the course material.",
      Implication:
        "This question explores what follows from the idea and why the consequence matters.",
      "Alternative viewpoint":
        "This question invites another perspective so you can compare possibilities.",
      Synthesis:
        "This question asks you to combine concepts and evidence into a coherent explanation.",
      Reflection:
        "This question helps you notice how your understanding changed during the conversation.",
      Application:
        "This question asks you to transfer the concept to a different situation.",
      Comparison:
        "This question helps distinguish related ideas by examining how they differ.",
    }[type] ||
    "This question helps make the idea precise before the conversation moves deeper."
  );
}

function messageTime(createdAt) {
  const parsed = createdAt ? new Date(createdAt) : new Date();
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(Number.isNaN(parsed.getTime()) ? new Date() : parsed);
}

function maximumEvidenceWidth() {
  const workspaceWidth = window.innerWidth - 48;
  return Math.max(320, workspaceWidth - 444);
}

function SocraticThinkingMessage({ elapsedSeconds }) {
  return (
    <article
      className="message socratic-thinking-message"
      role="status"
      aria-label="Socratic tutor is thinking through your response"
    >
      <span className="thinking-mark" aria-hidden="true">
        <svg viewBox="0 0 44 44" focusable="false">
          <circle
            className="thinking-orbit-track"
            cx="22"
            cy="22"
            r="16"
          />
          <g className="thinking-orbit-particles">
            <circle
              className="thinking-particle thinking-particle-primary"
              cx="22"
              cy="6"
              r="3.2"
            />
            <circle
              className="thinking-particle thinking-particle-secondary"
              cx="22"
              cy="38"
              r="2.4"
            />
          </g>
          <circle className="thinking-mark-center" cx="22" cy="22" r="10" />
          <g className="thinking-mark-stage">
            <path d="m17 27 2-1 9-9-2-2-9 9-1 4z" />
          </g>
        </svg>
      </span>
      <span className="thinking-copy">
        <strong>Socratic tutor</strong>
        <span className="thinking-status">Thinking through your response</span>
        <span className="thinking-elapsed" aria-hidden="true">
          {elapsedSeconds.toFixed(1)}s elapsed
        </span>
      </span>
    </article>
  );
}

function EvidenceDrawer({
  evidence,
  keywords,
  width,
  onClose,
  onResizeStart,
  onResize,
  onResizeEnd,
  onResizeKeyDown,
}) {
  useEffect(() => {
    if (!evidence) return;
    const closeOnEscape = (event) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("keydown", closeOnEscape);
      document.body.classList.remove("is-resizing-evidence");
    };
  }, [evidence, onClose]);

  if (!evidence) return null;
  return (
    <aside
      className="evidence-drawer"
      id="evidence-document-drawer"
      role="dialog"
      aria-label={`Evidence document: ${evidence.title}`}
      style={{ "--evidence-drawer-width": `${width}px` }}
    >
      <div
        className="evidence-drawer-resizer"
        role="separator"
        aria-label="Resize evidence document"
        aria-orientation="vertical"
        aria-valuemin={320}
        aria-valuemax={maximumEvidenceWidth()}
        aria-valuenow={Math.round(width)}
        tabIndex={0}
        onPointerDown={onResizeStart}
        onPointerMove={onResize}
        onPointerUp={onResizeEnd}
        onPointerCancel={onResizeEnd}
        onKeyDown={onResizeKeyDown}
      />
      <header className="evidence-drawer-header">
        <div>
          <span>Evidence document</span>
          <h2>{evidence.title}</h2>
        </div>
        <button
          type="button"
          className="quiet evidence-drawer-close"
          aria-label="Close evidence document"
          onClick={onClose}
          autoFocus
        >
          ×
        </button>
      </header>
      <div className="evidence-drawer-meta">
        {evidence.page_number && <span>Page {evidence.page_number}</span>}
        {evidence.chunk_id && <span>Passage {evidence.chunk_id}</span>}
        <span>Published assignment snapshot</span>
      </div>
      <article className="evidence-drawer-passage">
        <span>Selected passage</span>
        <p>
          <EmphasizedText text={evidence.text} keywords={keywords} />
        </p>
      </article>
      <p className="evidence-drawer-note">
        This passage comes from the frozen document version attached when the
        assignment was published.
      </p>
    </aside>
  );
}

function SocraticMessage({
  message,
  latest,
  thinkingStep,
  keywords,
  sources,
  score,
  responseSeconds,
  selectedEvidence,
  setSelectedEvidence,
}) {
  const question = latest ? thinkingStep : "";
  const hasQuestion = question.endsWith("?");
  const lead =
    question && message.content.trim().endsWith(question)
      ? message.content.trim().slice(0, -question.length).trim()
      : question === message.content.trim()
        ? ""
        : message.content;
  const questionType = hasQuestion ? inferQuestionType(question) : "";
  return (
    <article className={`message socratic-message-card ${message.role}`}>
      <header className="message-card-header">
        <div className="message-card-identity">
          <span className="message-avatar" aria-hidden="true">
            {message.role === "user" ? "Y" : "S"}
          </span>
          <strong>{message.role === "user" ? "You" : "Socratic tutor"}</strong>
          {latest && score != null && (
            <span className="score-badge">Score {Math.round(score)}/100</span>
          )}
        </div>
        <div className="message-card-meta">
          <time>{messageTime(message.created_at)}</time>
          {latest && responseSeconds !== null && (
            <span>Generated in {responseSeconds.toFixed(1)}s</span>
          )}
        </div>
      </header>
      <div className="message-card-body">
        {message.role === "assistant" && question ? (
          <>
            {lead && (
              <div className="prose message-lead">
                <Markdown>{lead}</Markdown>
              </div>
            )}
            <section
              className="message-thinking-step"
              aria-label="Your next thinking step"
            >
              <span>Your next thinking step</span>
              <p>
                <EmphasizedText text={question} keywords={keywords} />
              </p>
            </section>
          </>
        ) : (
          <div className="prose">
            <Markdown>{message.content}</Markdown>
          </div>
        )}
      </div>
      {latest && hasQuestion && (
        <details className="question-rationale">
          <summary>Why am I being asked this?</summary>
          <p>{questionRationale(questionType)}</p>
        </details>
      )}
      {latest && sources?.length > 0 && (
        <div className="message-evidence">
          <strong>Evidence context</strong>
          <div>
            {sources.map((source, index) => (
              <button
                type="button"
                className="evidence-chip"
                key={source.chunk_id || index}
                aria-pressed={selectedEvidence?.chunk_id === source.chunk_id}
                aria-controls="evidence-document-drawer"
                aria-expanded={selectedEvidence?.chunk_id === source.chunk_id}
                onClick={() =>
                  setSelectedEvidence((current) =>
                    current?.chunk_id === source.chunk_id ? null : source,
                  )
                }
              >
                {source.title}
                {source.page_number ? ` · page ${source.page_number}` : ""}
              </button>
            ))}
          </div>
        </div>
      )}
    </article>
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
    [selectedEvidence, setSelectedEvidence] = useState(null),
    [evidenceWidth, setEvidenceWidth] = useState(420),
    [chatExpanded, setChatExpanded] = useState(false);
  const endRef = useRef(null),
    pending = useRef(null),
    inputRef = useRef(null),
    evidenceResize = useRef(null);
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
    document.body.classList.toggle(
      "evidence-workspace-open",
      Boolean(selectedEvidence),
    );
    return () => document.body.classList.remove("evidence-workspace-open");
  }, [selectedEvidence]);
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
  function clampEvidenceWidth(width) {
    return Math.min(Math.max(320, width), maximumEvidenceWidth());
  }
  function startEvidenceResize(event) {
    if (window.innerWidth <= 760) return;
    evidenceResize.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startWidth: evidenceWidth,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
    document.body.classList.add("is-resizing-evidence");
  }
  function resizeEvidence(event) {
    const resize = evidenceResize.current;
    if (!resize || resize.pointerId !== event.pointerId) return;
    setEvidenceWidth(
      clampEvidenceWidth(resize.startWidth + resize.startX - event.clientX),
    );
  }
  function stopEvidenceResize(event) {
    if (evidenceResize.current?.pointerId !== event.pointerId) return;
    evidenceResize.current = null;
    document.body.classList.remove("is-resizing-evidence");
  }
  function resizeEvidenceWithKeyboard(event) {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Home") setEvidenceWidth(320);
    else if (event.key === "End")
      setEvidenceWidth(clampEvidenceWidth(window.innerWidth));
    else
      setEvidenceWidth((width) =>
        clampEvidenceWidth(width + (event.key === "ArrowLeft" ? 24 : -24)),
      );
  }
  if (!loaded)
    return (
      <>
        <Link to="/student">← Dashboard</Link>
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
  const latestAssistantIndex = attempt?.messages
    ? attempt.messages.findLastIndex((item) => item.role === "assistant")
    : -1;
  const suggestions = [
    ["I’m not sure yet", "I’m not sure yet."],
    [
      "Draft an example answer",
      "Could you draft a small example answer to help me understand?",
    ],
    ["Could you guide me?", "Could you guide me through this step?"],
  ];
  const milestone =
    assignment.student_config?.module_type === "milestone_based";
  return (
    <>
      <Link className="back" to="/student">
        ← Dashboard
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
      <div
        className={`workspace-grid${selectedEvidence ? " evidence-open" : ""}${chatExpanded ? " chat-expanded" : ""}`}
        style={
          selectedEvidence
            ? { "--evidence-drawer-width": `${evidenceWidth}px` }
            : undefined
        }
      >
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
            {assignment.tool === "socratic" && !selectedEvidence && (
              <button
                    type="button"
                    className="secondary compact chat-expand-control"
                    aria-pressed={chatExpanded}
                    aria-label={chatExpanded ? "Show assignment" : "Expand chat"}
                    title={chatExpanded ? "Show assignment" : "Expand chat"}
                    onClick={() => setChatExpanded((expanded) => !expanded)}
              >
                    {chatExpanded ? (
                      <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M9 3v6H3M15 3v6h6M9 21v-6H3M15 21v-6h6" />
                      </svg>
                    ) : (
                      <svg viewBox="0 0 24 24" aria-hidden="true">
                        <path d="M9 3H3v6M15 3h6v6M9 21H3v-6M15 21h6v-6" />
                      </svg>
                    )}
              </button>
            )}
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
                {attempt.messages.map((m, i) =>
                  assignment.tool === "socratic" ? (
                    <SocraticMessage
                      key={i}
                      message={m}
                      latest={i === latestAssistantIndex}
                      thinkingStep={thinkingStep}
                      keywords={keywords}
                      sources={state.sources}
                      score={socratic.last_score}
                      responseSeconds={lastGenerationSeconds}
                      selectedEvidence={selectedEvidence}
                      setSelectedEvidence={setSelectedEvidence}
                    />
                  ) : (
                    <article className={`message ${m.role}`} key={i}>
                      <span className="message-author">
                        {m.role === "user" ? "You" : tool.name}
                      </span>
                      <div className="prose">
                        <Markdown>{m.content}</Markdown>
                      </div>
                    </article>
                  ),
                )}
                {busy &&
                  (assignment.tool === "socratic" ? (
                    <SocraticThinkingMessage
                      elapsedSeconds={generationStartedAt ? generationSeconds : 0}
                    />
                  ) : (
                    <p className="working" role="status">
                      Working on your response…
                    </p>
                  ))}
                <div ref={endRef} />
              </div>
              {assignment.tool === "socratic" &&
                thinkingStep.endsWith("?") &&
                !completed && (
                  <div
                    className={`suggested-responses${busy ? " is-busy" : ""}`}
                    aria-label="Suggested responses"
                  >
                    {suggestions.map(([label, value]) => (
                      <button
                        type="button"
                        className="suggestion-chip"
                        disabled={busy}
                        key={label}
                        onClick={() => {
                          setMessage(value);
                          inputRef.current?.focus();
                        }}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
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
                    ref={inputRef}
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
                      if (
                        e.key === "Enter" &&
                        !e.shiftKey &&
                        !e.nativeEvent.isComposing
                      ) {
                        e.preventDefault();
                        send(e);
                      }
                    }}
                  />
                  <div>
                    <span className="help">
                      {milestone
                        ? "Submitting completes this assignment."
                        : "Enter to send · Shift + Enter for a new line"}
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
      <EvidenceDrawer
        evidence={selectedEvidence}
        keywords={keywords}
        width={evidenceWidth}
        onClose={() => setSelectedEvidence(null)}
        onResizeStart={startEvidenceResize}
        onResize={resizeEvidence}
        onResizeEnd={stopEvidenceResize}
        onResizeKeyDown={resizeEvidenceWithKeyboard}
      />
    </>
  );
}

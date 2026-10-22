import React, { useEffect, useRef, useState } from "react";
import { api } from "./api";

const stages = [
  "welcome",
  "study_resources",
  "diagnostic_quiz",
  "adaptive_learning",
  "reflection",
];
const stageLabels = [
  "Welcome",
  "Study",
  "Understanding check",
  "Practice & recheck",
  "Reflect",
];

// Separate readable paragraphs without cutting sentences or fenced code blocks.
function replyParagraphs(content) {
  const paragraphs = [];
  let lines = [];
  let fence = null;
  for (const line of content.split(/\r?\n/)) {
    const marker = line.match(/^\s*(`{3,}|~{3,})/);
    if (marker) {
      if (!fence) fence = marker[1];
      else if (marker[1][0] === fence[0] && marker[1].length >= fence.length) fence = null;
    }
    if (!line.trim() && !fence) {
      if (lines.length) paragraphs.push(lines.join("\n"));
      lines = [];
    } else {
      lines.push(line);
    }
  }
  if (lines.length) paragraphs.push(lines.join("\n"));
  return paragraphs;
}

function StudyResourceCard({ resource, recommended, compact = false }) {
  const body = compact ? (
    <><strong>{resource.title}</strong><span>{resource.description}</span>{recommended && <small>{recommended}</small>}</>
  ) : (
    <div>
      <small>{resource.provider}</small>
      {recommended && <small>{recommended}</small>}
      <strong>{resource.title}</strong>
      <p>{resource.description}</p>
      <p><b>Focus:</b> {resource.focus}</p>
    </div>
  );
  const className = compact ? (resource.url ? "" : "local-reading") : "resource-card lesson-resource";
  if (!resource.url) {
    return <div className={className}>{body}{!compact && <small>Included in this lesson</small>}</div>;
  }
  return <a className={className} href={resource.url} target="_blank" rel="noopener noreferrer">{body}{!compact && <b>↗</b>}</a>;
}

// CURRENT V2: student interactions submit to the learning-turn endpoint.
export default function LessonWorkspace({ assignmentId, onBack, embedded = false }) {
  const [lesson, setLesson] = useState(null);
  const [attempt, setAttempt] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [value, setValue] = useState("");
  const [submittedMessage, setSubmittedMessage] = useState(null);
  const [waitingForReply, setWaitingForReply] = useState(false);
  const pending = useRef(null);
  const end = useRef(null);
  const loadLessonAttempt = async () => {
    setBusy(true);
    setError("");
    try {
      const [detail,current] = await Promise.all([
        api(`/student/assignments/${assignmentId}`),
        api(`/student/assignments/${assignmentId}/start`, {method: "POST"}),
      ]);
      setLesson(detail);
      setAttempt(current);
      setSubmittedMessage(null);
      pending.current = null;
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const restartLessonAttempt = async () => {
    if (busy || !window.confirm("Restart this assignment? This clears your saved answers, conversation, and progress for this assignment.")) return;
    setBusy(true);
    setError("");
    try {
      const restarted = await api(`/student/assignments/${assignmentId}/restart`, { method: "POST" });
      pending.current = null;
      setSubmittedMessage(null);
      setValue("");
      setAttempt(restarted);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    loadLessonAttempt();
  }, [assignmentId]);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [attempt?.messages.length, submittedMessage, waitingForReply]);
  const submitLessonTurn = async (data, retry = false) => {
    if (busy) return;
    const body = retry
      ? pending.current
      : { ...data, turn_id: crypto.randomUUID() };
    if (!body) return;
    pending.current = body;
    if (!retry) {
      // Mirror the stored student text; the server history replaces this on success.
      const content = body.content?.trim() || (
        body.option_index != null
          ? `Option ${String.fromCharCode(65 + body.option_index)}; confidence: ${body.confidence || "not reported"}; explanation: ${body.explanation || "not reported"}`
          : body.action
      );
      setSubmittedMessage({ id: body.turn_id, role: "student", content });
      setValue("");
    }
    setWaitingForReply(true);
    setBusy(true);
    setError("");
    try {
      const next = await api(
        `/student/assignments/${assignmentId}/learning-turn`,
        { method: "POST", body: JSON.stringify(body) },
      );
      setAttempt(next);
      setSubmittedMessage(null);
      setValue("");
      pending.current = null;
    } catch (e) {
      setError(e.message);
    } finally {
      setWaitingForReply(false);
      setBusy(false);
    }
  };
  const state = attempt?.learning_state;
  const stage = state?.stage;
  const stageIndex = stages.indexOf(
    stage === "learning_choice"
      ? state.reflections?.length
        ? "reflection"
        : "adaptive_learning"
      : stage,
  );
  return (
    <>
      <button className="back" onClick={onBack}>
        ← My assignments
      </button>
      {error && (
        <div className="notice error" role="alert">
          {error}
          <button
            disabled={busy}
            onClick={() =>
              pending.current
                ? submitLessonTurn(null, true)
                : loadLessonAttempt()
            }
          >
            Try again
          </button>
        </div>
      )}
      {!lesson || !attempt ? (
        <p>
          {busy
            ? "Opening your lesson…"
            : "The lesson is not ready yet. Your instructor can review its setup."}
        </p>
      ) : (
        <>
          <div className={embedded ? "page-heading" : "workspace-head"}>
            <div>
              <p className={embedded ? "context" : "eyebrow"}>{embedded ? "Self Directed Learning" : "Your lesson"}</p>
              <h1>{embedded ? lesson.title : lesson.learning_plan.topic}</h1>
            </div>
            <span>
              {stage === "paused"
                ? "Paused · progress saved"
                : "Learn at your own pace"}
            </span>
            <button className="secondary" disabled={busy} onClick={restartLessonAttempt}>
              Restart assignment
            </button>
          </div>
          <div className="workspace-grid">
            <aside>
              <ol className="lesson-stages" aria-label="Learning stages">
                {stageLabels.map((label, index) => (
                  <li
                    key={label}
                    className={index === stageIndex ? "active" : ""}
                    aria-current={index === stageIndex ? "step" : undefined}
                  >
                    <span>{index + 1}</span>
                    {label}
                  </li>
                ))}
              </ol>
              <p className="eyebrow">Learning objectives</p>
              <div className="objectives">
                {attempt.objective_progress.map((objective, index) => (
                  <div
                    key={objective.objective_id}
                    className={`objective ${objective.status}`}
                  >
                    <span>
                      {objective.status === "demonstrated" ? "✓" : index + 1}
                    </span>
                    <div>
                      <strong>{objective.title}</strong>
                      <small>
                        {objective.status === "demonstrated"
                          ? "Shown in an independent activity"
                          : "Open for learning"}
                      </small>
                    </div>
                  </div>
                ))}
              </div>
              {state.diagnostic_complete && (
                <div className="placement">
                  <strong>Understanding check: {attempt.quiz_score}/5</strong>
                  <span>A starting point, not a mastery label</span>
                </div>
              )}
              {state.target_concept && state.diagnostic_complete && <div className="placement"><strong>Current concept: {state.target_concept}</strong><span>Independent checks: {Math.min(2, state.concept_checks?.[state.target_objective]?.[state.target_concept] || 0)} of 2</span></div>}
              <details className="lesson-readings" open={stage === "study_resources"}>
                <summary>Approved materials</summary>
                <p>These materials support your lesson. You don't need to open every optional link before the quiz.</p>
                {(lesson.learning_plan.study_resources || []).map((resource, index) => <StudyResourceCard key={`${resource.title}-${index}`} resource={resource} compact recommended={resource.url && state.recommended_resource_url === resource.url ? (state.familiarity === "new" ? "Start here" : "Suggested for your focus") : null} />)}
              </details>
              <button
                className="secondary lesson-pause"
                disabled={busy}
                onClick={() =>
                  submitLessonTurn({
                    action: stage === "paused" ? "resume" : "pause",
                  })
                }
              >
                {stage === "paused" ? "Resume learning" : "Pause & save"}
              </button>
            </aside>
            <section
              className="chat lesson-chat"
              aria-label="Lesson conversation"
            >
              <div
                className="messages"
                aria-live="polite"
                aria-relevant="additions"
              >
                {[...attempt.messages, ...(submittedMessage ? [submittedMessage] : [])].map((message) => (
                  <article
                    className={`message ${message.role}`}
                    key={message.id}
                  >
                    <div className="avatar">
                      {message.role === "assistant" ? "A" : "You"}
                    </div>
                    <div>
                      {(message.role === "assistant"
                        ? replyParagraphs(message.content)
                        : [message.content]
                      ).map((paragraph, index) => (
                        <p key={index}>{paragraph}</p>
                      ))}
                      {message.sources?.length > 0 && (
                        <div className="citations">
                          {message.sources.map((source) => (
                            <span key={source.document_id}>
                              ▤ {source.filename}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </article>
                ))}
                {waitingForReply && (
                  <article className="message assistant thinking" role="status">
                    <div className="avatar" aria-hidden="true">A</div>
                    <div>
                      <p>
                        Thinking…
                        <span className="thinking-dots" aria-hidden="true">
                          <span /><span /><span />
                        </span>
                      </p>
                    </div>
                  </article>
                )}
                {stage === "study_resources" && (
                  <div className="resource-cards">
                    {lesson.learning_plan.study_resources.map((resource, index) => (
                      <StudyResourceCard key={`${resource.title}-${index}`} resource={resource} recommended={resource.url && state.recommended_resource_url === resource.url ? (state.familiarity === "new" ? "Start here" : "Suggested for your focus") : null} />
                    ))}
                  </div>
                )}
                {stage === "welcome" && (
                  <div className="learning-choices familiarity-choices" aria-label="Your familiarity with this topic">
                    {["I'm completely new", "I know some of this", "I'm comfortable with this topic"].map(choice => <button className="secondary" key={choice} disabled={busy} onClick={() => submitLessonTurn({ content: choice })}>{choice}</button>)}
                  </div>
                )}
                {stage === "study_resources" && state.study_concepts?.length > 0 && <div className="learning-choices" aria-label="Choose an unfamiliar concept">{state.study_concepts.map(concept => <button key={concept} className="secondary" disabled={busy} onClick={() => submitLessonTurn({ content: concept })}>{concept}</button>)}</div>}
                {stage === "study_resources" && <div className="learning-choices"><button className="secondary" disabled={busy} onClick={() => submitLessonTurn({ content: state.familiarity === "comfortable" ? "Quick recap" : "Please explain more" })}>{state.familiarity === "comfortable" ? "Quick recap" : "Explain more"}</button></div>}
                {stage === "study_resources" && (
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() => submitLessonTurn({ content: "I am done" })}
                  >
                    I'm ready · start the quiz
                  </button>
                )}
                {stage === "diagnostic_quiz" && (
                  <QuestionCard
                    key={state.current_question.id}
                    state={state}
                    submitLessonTurn={submitLessonTurn}
                    disabled={busy}
                  />
                )}
                {stage === "adaptive_learning" && (
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => submitLessonTurn({ action: "hint" })}
                  >
                    Give me a hint
                  </button>
                )}
                {state.choices?.length > 0 && stage === "learning_choice" && (
                  <div
                    className="learning-choices format-choices"
                    aria-label="Choose how to learn"
                  >
                    {state.choices.map((choice) => (
                      <button
                        className="secondary"
                        key={choice}
                        disabled={busy}
                        onClick={() =>
                          submitLessonTurn({
                            action: "choice",
                            content: choice,
                          })
                        }
                      >
                        <strong>{choice}</strong>
                        <small>{state.choice_descriptions?.[choice]}</small>
                      </button>
                    ))}
                  </div>
                )}
                {stage === "paused" && (
                  <div className="learning-choices">
                    <button
                      className="primary"
                      disabled={busy}
                      onClick={() => submitLessonTurn({ action: "resume" })}
                    >
                      Resume learning
                    </button>
                    <button className="secondary" onClick={onBack}>
                      Return to my assignments
                    </button>
                  </div>
                )}
                <div ref={end} />
              </div>
              {stage !== "paused" && (
                <form
                  className="composer"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (value.trim())
                      submitLessonTurn({
                        content: value.trim(),
                        question_id: state.current_question?.id,
                      });
                  }}
                >
                  <label className="sr-only" htmlFor="lesson-reply">
                    Your reply
                  </label>
                  <textarea
                    id="lesson-reply"
                    disabled={busy}
                    value={value}
                    onChange={(event) => setValue(event.target.value)}
                    onKeyDown={(event) => {
                      if (
                        event.key === "Enter" &&
                        !event.shiftKey &&
                        !event.nativeEvent.isComposing &&
                        event.keyCode !== 229
                      ) {
                        event.preventDefault();
                        if (!busy && !event.repeat && value.trim()) {
                          event.currentTarget.form.requestSubmit();
                        }
                      }
                    }}
                    placeholder={
                      stage === "welcome"
                        ? "Or tell us what feels unfamiliar…"
                        : stage === "diagnostic_quiz"
                          ? "Or reply naturally: B, medium confidence, because…"
                          : stage === "reflection"
                            ? "What can you explain or do now?"
                            : "Ask a question, request an example, or explain your reasoning…"
                    }
                  />
                  <button disabled={busy || !value.trim()}>
                    Send
                  </button>
                  <small>
                    You can ask for help or pause whenever you need.
                  </small>
                </form>
              )}
            </section>
          </div>
        </>
      )}
    </>
  );
}

function QuestionCard({ state, submitLessonTurn, disabled }) {
  const question = state.current_question;
  const [selection, setSelection] = useState(null);
  const [confidence, setConfidence] = useState("");
  const [explanation, setExplanation] = useState("");
  const submitQuizAnswer = () =>
    submitLessonTurn({
      action: state.metadata_requested ? "continue" : "answer",
      question_id: question.id,
      option_index: state.metadata_requested ? undefined : selection,
      confidence: confidence || undefined,
      explanation: explanation.trim() || undefined,
    });
  return (
    <div className="diagnostic-card">
      <p>Confidence and reasoning help choose your next practice; they don't change your quiz score.</p>
      <p className="eyebrow">
        Question {state.quiz_index + 1} of 5 · {question.difficulty}
      </p>
      <fieldset
        disabled={disabled || state.metadata_requested}
        className="quiz-question"
      >
        <legend>{question.question}</legend>
        {question.options.map((option, index) => (
          <label key={index}>
            <input
              type="radio"
              name={`question-${question.id}`}
              checked={
                (state.metadata_requested
                  ? state.recorded_option
                  : selection) === index
              }
              onChange={() => setSelection(index)}
            />
            <span>
              {String.fromCharCode(65 + index)}. {option}
            </span>
          </label>
        ))}
      </fieldset>
      <label>
        How confident are you?
        <select
          disabled={disabled}
          value={confidence}
          onChange={(event) => setConfidence(event.target.value)}
        >
          <option value="">Not reported</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>
      </label>
      {state.quiz_index >= 3 && (
        <label>
          Explain your choice in one sentence
          <textarea
            disabled={disabled}
            value={explanation}
            onChange={(event) => setExplanation(event.target.value)}
            placeholder="My reasoning is…"
          />
        </label>
      )}
      <div className="learning-choices">
        <button
          className="primary"
          disabled={
            disabled || (!state.metadata_requested && selection === null)
          }
          onClick={submitQuizAnswer}
        >
          {state.metadata_requested ? "Continue" : "Record answer"}
        </button>
        {state.metadata_requested ? (
          <button
            className="secondary"
            disabled={disabled}
            onClick={() =>
              submitLessonTurn({ action: "continue", question_id: question.id })
            }
          >
            Continue without extra details
          </button>
        ) : (
          <button
            className="secondary"
            disabled={disabled}
            onClick={() =>
              submitLessonTurn({
                action: "answer",
                question_id: question.id,
                content: "I don't know",
                confidence: confidence || undefined,
              })
            }
          >
            I don't know
          </button>
        )}
        <button
          className="secondary"
          disabled={disabled}
          onClick={() =>
            submitLessonTurn({ action: "hint", question_id: question.id })
          }
        >
          Conceptual hint
        </button>
      </div>
    </div>
  );
}

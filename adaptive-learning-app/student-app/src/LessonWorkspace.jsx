import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
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
  const messagesRef = useRef(null);
  const savedScroll = useRef(null);
  useLayoutEffect(() => {
    if (!savedScroll.current) return;
    if (messagesRef.current) messagesRef.current.scrollTop = savedScroll.current.chat;
    if (document.scrollingElement) document.scrollingElement.scrollTop = savedScroll.current.page;
  }, [attempt, submittedMessage, waitingForReply, busy]);
  const lastReply = attempt?.messages?.at(-1);
  const quizHelp = attempt?.learning_state?.stage === "diagnostic_quiz" && lastReply?.role === "assistant" && /^(Hint:|Review:)/.test(lastReply.content) ? lastReply : null;
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
  const submitLessonTurn = async (data, retry = false) => {
    if (busy) return;
    const body = retry
      ? pending.current
      : { ...data, turn_id: crypto.randomUUID() };
    if (!body) return;
    savedScroll.current = {chat: messagesRef.current?.scrollTop || 0, page: document.scrollingElement?.scrollTop || 0};
    pending.current = body;
    if (!retry) {
      // Mirror the stored student text; the server history replaces this on success.
      const content = body.content?.trim() || (
        body.option_index != null
          ? `Option ${String.fromCharCode(65 + body.option_index)}; confidence: ${body.confidence || "not reported"}`
          : body.action === "hint" ? "I'd like a hint and worked example."
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
  const activeStages = state?.bounded_flow ? ["welcome", "study_resources", "diagnostic_quiz", "application", "completed"] : stages;
  const activeLabels = state?.bounded_flow ? ["Prerequisites", "Study", "Five questions", "Application", "Complete"] : stageLabels;
  const stageIndex = activeStages.indexOf(
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
                {activeLabels.map((label, index) => (
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
                  <strong>{state.bounded_flow ? "First-attempt score" : "Understanding check"}: {attempt.quiz_score}/5</strong>
                  <span>A starting point, not a mastery label</span>
                </div>
              )}
              {state.target_concept && state.diagnostic_complete && <div className="placement"><strong>Current concept: {state.target_concept}</strong><span>Independent checks: {Math.min(2, state.concept_checks?.[state.target_objective]?.[state.target_concept] || 0)} of 2</span></div>}
              <details className="lesson-readings" open={stage === "study_resources"}>
                <summary>Approved readings</summary>
                <p>Available throughout your lesson. You don't need to open every link before the quiz.</p>
                {(lesson.learning_plan.study_resources || []).map(resource => <a key={resource.url} href={resource.url} target="_blank" rel="noopener noreferrer"><strong>{resource.title}</strong><span>{resource.description}</span>{state.recommended_resource_url === resource.url && <small>{state.familiarity === "new" ? "Start here" : "Suggested for your focus"}</small>}</a>)}
              </details>
              {stage !== "completed" && <button
                className="secondary lesson-pause"
                disabled={busy}
                onClick={() =>
                  submitLessonTurn({
                    action: stage === "paused" ? "resume" : "pause",
                  })
                }
              >
                {stage === "paused" ? "Resume learning" : "Pause & save"}
              </button>}
            </aside>
            <section
              className="chat lesson-chat"
              aria-label="Lesson conversation"
            >
              <div
                ref={messagesRef}
                onScroll={event=>{if(savedScroll.current) savedScroll.current.chat=event.currentTarget.scrollTop;}}
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
                        : [message.content === "hint" ? "I'd like a hint and worked example." : message.content.replace(/; explanation:.*$/s, "")]
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
                {state.bounded_flow && stage === "welcome" && <div className="resource-cards">
                  {(lesson.learning_plan.prerequisite_resources || []).map(resource=><a className="resource-card" key={resource.url} href={resource.url} target="_blank" rel="noopener noreferrer"><strong>{resource.title}</strong><p>{resource.description}</p></a>)}
                  <button disabled={busy} onClick={()=>submitLessonTurn({action:"continue"})}>I’m familiar with the prerequisites · continue</button>
                </div>}
                {state.bounded_flow && stage === "application" && <p>Final application: {lesson.learning_plan.required_task.submission_prompt}</p>}
                {(stage === "study_resources" || (state.bounded_flow && stage === "diagnostic_quiz" && quizHelp?.content.startsWith("Review:"))) && (
                  <div className="resource-cards">
                    {lesson.learning_plan.study_resources.map((resource) => (
                      <a
                        className="resource-card lesson-resource"
                        key={resource.url}
                        href={resource.url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <div>
                          <small>{resource.provider}</small>
                          {state.recommended_resource_url === resource.url && <small>{state.familiarity === "new" ? "Start here" : "Suggested for your focus"}</small>}
                          <strong>{resource.title}</strong>
                          <p>{resource.description}</p>
                          <p>
                            <b>Focus:</b> {resource.focus}
                          </p>
                        </div>
                        <b>↗</b>
                      </a>
                    ))}
                  </div>
                )}
                {stage === "welcome" && !state.bounded_flow && (
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
                  <>
                  {quizHelp && <aside className="diagnostic-card" aria-label="Help for this question" role="status">
                    <strong>{quizHelp.content.startsWith("Hint:") ? "Hint and worked example" : "Reading guidance"}</strong>
                    {replyParagraphs(quizHelp.content).map((paragraph,index)=><p key={index}>{paragraph}</p>)}
                  </aside>}
                  <QuestionCard
                    state={state}
                    submitLessonTurn={submitLessonTurn}
                    disabled={busy}
                  />
                  </>
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
              </div>
              {stage !== "paused" && stage !== "completed" && (
                <form
                  className="composer"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (value.trim())
                      submitLessonTurn({
                        ...(stage === "application" ? {action: "answer"} : {}),
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
                    {stage === "application" ? "Submit final response" : "Send"}
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
  useEffect(() => {
    setSelection(null);
    setConfidence("");
    setExplanation("");
  }, [question.id, state.quiz_attempt_count]);
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
      {state.bounded_flow && <p>Attempt {state.quiz_attempt_count + 1} of 3. Hints are recorded without deductions.</p>}
      {state.bounded_flow && state.quiz_retry && <button disabled={disabled} onClick={()=>submitLessonTurn({content:"Read more",question_id:question.id})}>Read more</button>}
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
          {state.bounded_flow ? "Get a hint / worked example" : "Conceptual hint"}
        </button>
      </div>
    </div>
  );
}

import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { api } from "./api";
import ResultCard, { downloadBlob } from "./ResultCard";

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
      else if (marker[1][0] === fence[0] && marker[1].length >= fence.length)
        fence = null;
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
export default function LessonWorkspace({
  assignmentId,
  onBack,
  embedded = false,
}) {
  const [lesson, setLesson] = useState(null);
  const [attempt, setAttempt] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [value, setValue] = useState("");
  const [submittedMessage, setSubmittedMessage] = useState(null);
  const [waitingForReply, setWaitingForReply] = useState(false);
  const pending = useRef(null);
  const messagesRef = useRef(null);
  const turnRef = useRef(null);
  const anchorNextTurn = useRef(false);
  const savedPosition = useRef(null);
  const [turnStart, setTurnStart] = useState(null);
  const [codeCopied, setCodeCopied] = useState(false);
  const [materials, setMaterials] = useState([]);
  const [downloading, setDownloading] = useState(null);
  const [showResult, setShowResult] = useState(false);
  const [pendingQuiz, setPendingQuiz] = useState(null);
  const questionPositions = useRef({});
  const replyInput = useRef(null);
  useLayoutEffect(() => {
    const chat = messagesRef.current;
    if (!chat) return;
    if (anchorNextTurn.current && turnRef.current) {
      // Move once to the new outgoing bubble, never to the end of the reply.
      // The turn reserves a viewport of space, so replacing Thinking keeps its top.
      chat.scrollTop +=
        turnRef.current.getBoundingClientRect().top -
        chat.getBoundingClientRect().top -
        24;
      anchorNextTurn.current = false;
      savedPosition.current = chat.scrollTop;
    } else if (savedPosition.current != null) {
      chat.scrollTop = savedPosition.current;
    }
  }, [attempt, submittedMessage, waitingForReply]);
  const lastReply = attempt?.messages?.at(-1);
  const quizHelp =
    attempt?.learning_state?.stage === "diagnostic_quiz" &&
    lastReply?.role === "assistant" &&
    /^(Hint:|Review:)/.test(lastReply.content)
      ? lastReply
      : null;
  const loadLessonAttempt = async () => {
    setBusy(true);
    setError("");
    try {
      const [detail, current, sources] = await Promise.all([
        api(`/student/assignments/${assignmentId}`),
        api(`/student/assignments/${assignmentId}/start`, { method: "POST" }),
        api(`/student/assignments/${assignmentId}/materials`).catch(() => ({
          files: [],
        })),
      ]);
      setTurnStart(null);
      savedPosition.current = null;
      setMaterials(Array.isArray(sources?.files) ? sources.files : []);
      questionPositions.current = {};
      setPendingQuiz(null);
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
    if (
      busy ||
      !window.confirm(
        "Restart this assignment? This clears your saved answers, conversation, and progress for this assignment.",
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      const restarted = await api(
        `/student/assignments/${assignmentId}/restart`,
        { method: "POST" },
      );
      pending.current = null;
      setSubmittedMessage(null);
      setValue("");
      setTurnStart(null);
      savedPosition.current = null;
      questionPositions.current = {};
      setPendingQuiz(null);
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
    if (!retry) {
      setTurnStart(attempt.messages.length);
      anchorNextTurn.current = true;
    }
    pending.current = body;
    if (
      !retry &&
      attempt.learning_state?.stage === "diagnostic_quiz" &&
      body.action === "answer"
    ) {
      setPendingQuiz({
        question_id: attempt.learning_state.current_question.id,
        selected_index: body.option_index ?? null,
        pending: true,
        confidence: body.confidence,
      });
    }
    if (!retry) {
      // Mirror the stored student text; the server history replaces this on success.
      const content =
        body.content?.trim() ||
        (body.option_index != null
          ? `Option ${String.fromCharCode(65 + body.option_index)}; confidence: ${body.confidence || "not reported"}`
          : body.action === "hint"
            ? "I'd like a hint and worked example."
            : body.action === "continue"
              ? attempt.learning_state.stage === "welcome"
                ? "I’m familiar with the prerequisites. Let’s continue."
                : "Let’s continue."
              : body.action === "pause"
                ? "Pause and save my progress."
                : body.action === "resume"
                  ? "I’m ready to continue."
                  : body.action);
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
      setPendingQuiz(null);
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
  const activeStages = state?.bounded_flow
    ? [
        "welcome",
        "study_resources",
        "diagnostic_quiz",
        "application",
        "completed",
      ]
    : stages;
  const activeLabels = state?.bounded_flow
    ? ["Prerequisites", "Study", "Quiz", "Application", "Complete"]
    : stageLabels;
  const stageIndex = activeStages.indexOf(
    stage === "learning_choice"
      ? state.reflections?.length
        ? "reflection"
        : "adaptive_learning"
      : stage,
  );
  const progressStage = stage === "paused" ? state?.resume_stage : stage;
  const progressPercent =
    progressStage === "completed"
      ? 100
      : progressStage === "application"
        ? 85
        : progressStage === "diagnostic_quiz"
          ? 30 + Math.min(5, state.quiz_index || 0) * 11
          : progressStage === "study_resources"
            ? 15
            : 0;
  const messages = [
    ...(attempt?.messages || []),
    ...(submittedMessage ? [submittedMessage] : []),
  ];
  const feedback = state?.quiz_feedback || [];
  const quizCards = (state?.quiz_cards || []).map((card) => ({ ...card }));
  if (
    state?.bounded_flow &&
    state.current_question &&
    !quizCards.some((card) => card.id === state.current_question.id)
  ) {
    quizCards.push({
      ...state.current_question,
      question_index: state.quiz_index,
    });
  }
  for (const card of quizCards) {
    if (questionPositions.current[card.id] == null)
      questionPositions.current[card.id] =
        card.position ?? attempt.messages.length;
    card.position = card.position ?? questionPositions.current[card.id];
  }
  const renderCards = (position) =>
    quizCards
      .filter((card) => card.position === position)
      .map((card) => (
        <QuestionCard
          key={card.id}
          state={{
            ...state,
            current_question: card,
            quiz_index: card.question_index,
          }}
          submitLessonTurn={submitLessonTurn}
          disabled={busy}
          records={[
            ...feedback.filter((entry) => entry.question_id === card.id),
            ...(pendingQuiz?.question_id === card.id ? [pendingQuiz] : []),
          ]}
          readOnly={
            stage !== "diagnostic_quiz" ||
            state.current_question?.id !== card.id
          }
        />
      ));
  const renderMessage = (message, index) => (
    <React.Fragment key={message.id}>
      {renderCards(index)}
      <ChatMessage
        message={message}
        bounded={state?.bounded_flow}
        verdict={
          message.role === "assistant"
            ? feedback.find((entry) => entry.message_index === index - 1)
                ?.correct
            : undefined
        }
      />
    </React.Fragment>
  );
  const downloadMaterial = async (file) => {
    setDownloading(file.id);
    setError("");
    try {
      const blob = await api(
        `/student/assignments/${assignmentId}/materials/${file.id}`,
        { responseType: "blob" },
      );
      downloadBlob(blob, file.filename);
    } catch (error) {
      setError(error.message);
    } finally {
      setDownloading(null);
    }
  };
  const materialLinks = (
    <div className="sdl-course-downloads">
      <strong>Read your course materials</strong>
      <p>
        No supplemental links are available here. Download the materials your
        instructor selected for this lesson.
      </p>
      {materials.map((file) => (
        <button
          type="button"
          className="secondary"
          key={file.id}
          disabled={downloading !== null}
          onClick={() => downloadMaterial(file)}
        >
          {downloading === file.id
            ? "Downloading…"
            : `↓ Download ${file.filename}`}
        </button>
      ))}
      {!materials.length && (
        <p className="help">
          Ask your instructor for the course material if no download is
          available.
        </p>
      )}
    </div>
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
              <p className={embedded ? "context" : "eyebrow"}>
                {embedded ? "Self Directed Learning" : "Your lesson"}
              </p>
              <h1>{embedded ? lesson.title : lesson.learning_plan.topic}</h1>
            </div>
            <span>
              {stage === "paused"
                ? "Paused · progress saved"
                : "Learn at your own pace"}
            </span>
            <button
              className="secondary"
              disabled={busy}
              onClick={restartLessonAttempt}
            >
              Restart assignment
            </button>
          </div>
          <div className="workspace-grid">
            <aside>
              {state.bounded_flow && (
                <div className="sdl-progress">
                  <div>
                    <strong>Your progress</strong>
                    <span>{progressPercent}%</span>
                  </div>
                  <progress
                    aria-label="Lesson progress"
                    max="100"
                    value={progressPercent}
                  />
                </div>
              )}
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
                  <strong>
                    {state.bounded_flow
                      ? "First-attempt score"
                      : "Understanding check"}
                    : {attempt.quiz_score}/5
                  </strong>
                  <span>A starting point, not a mastery label</span>
                </div>
              )}
              {state.target_concept && state.diagnostic_complete && (
                <div className="placement">
                  <strong>Current concept: {state.target_concept}</strong>
                  <span>
                    Independent checks:{" "}
                    {Math.min(
                      2,
                      state.concept_checks?.[state.target_objective]?.[
                        state.target_concept
                      ] || 0,
                    )}{" "}
                    of 2
                  </span>
                </div>
              )}
              <details
                className="lesson-readings"
                open={stage === "study_resources"}
              >
                <summary>Approved readings</summary>
                <p>
                  Available throughout your lesson. You don't need to open every
                  link before the quiz.
                </p>
                {(lesson.learning_plan.study_resources || []).map(
                  (resource) => (
                    <a
                      key={resource.url}
                      href={resource.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <strong>{resource.title}</strong>
                      <span>{resource.description}</span>
                      {state.recommended_resource_url === resource.url && (
                        <small>
                          {state.familiarity === "new"
                            ? "Start here"
                            : "Suggested for your focus"}
                        </small>
                      )}
                    </a>
                  ),
                )}
              </details>
              {stage !== "completed" && (
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
              )}
            </aside>
            <section
              className="chat lesson-chat"
              aria-label="Lesson conversation"
            >
              <div
                ref={messagesRef}
                onScroll={(event) => {
                  savedPosition.current = event.currentTarget.scrollTop;
                }}
                className="messages"
                aria-live="polite"
                aria-relevant="additions"
              >
                {messages
                  .slice(0, turnStart ?? messages.length)
                  .map(renderMessage)}
                <div
                  className={turnStart != null ? "sdl-current-turn" : ""}
                  ref={turnRef}
                >
                  {turnStart != null &&
                    messages
                      .slice(turnStart)
                      .map((message, index) =>
                        renderMessage(message, index + turnStart),
                      )}
                  {renderCards(messages.length)}
                  {waitingForReply && (
                    <div className="sdl-message-group assistant">
                      <span className="sdl-speaker">Tutor</span>
                      <article
                        className="message assistant sdl-bubble thinking"
                        role="status"
                        aria-label="Tutor is thinking"
                      >
                        <span>Thinking</span>
                        <span className="thinking-dots" aria-hidden="true">
                          <span />
                          <span />
                          <span />
                        </span>
                      </article>
                    </div>
                  )}
                  {!waitingForReply && (
                    <>
                      {state.bounded_flow && stage === "welcome" && (
                        <div className="resource-cards">
                          {(
                            lesson.learning_plan.prerequisite_resources || []
                          ).map((resource) => (
                            <a
                              className="resource-card"
                              key={resource.url}
                              href={resource.url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              <strong>{resource.title}</strong>
                              <p>{resource.description}</p>
                            </a>
                          ))}
                          {!(lesson.learning_plan.prerequisite_resources || [])
                            .length && materialLinks}
                          <button
                            disabled={busy}
                            onClick={() =>
                              submitLessonTurn({ action: "continue" })
                            }
                          >
                            I’m familiar with the prerequisites · continue
                          </button>
                        </div>
                      )}
                      {state.bounded_flow &&
                        stage === "completed" &&
                        state.completion_code && (
                          <div className="sdl-completion-code">
                            <strong>Share this code with your TA</strong>
                            <p>
                              View your result card, save it as an image or take
                              a screenshot, and share it with your TA.
                            </p>
                            <button
                              type="button"
                              onClick={() => setShowResult(true)}
                            >
                              View result card
                            </button>
                            <ResultCard
                              key={state.completion_code}
                              open={showResult}
                              onClose={() => setShowResult(false)}
                              title={lesson.title}
                              code={state.completion_code}
                              score={
                                state.quiz_score ?? attempt.quiz_score ?? 0
                              }
                              attempts={state.quiz_attempt_summary || []}
                            />
                            <code>{state.completion_code}</code>
                            <button
                              type="button"
                              className="secondary"
                              onClick={async () => {
                                try {
                                  await navigator.clipboard.writeText(
                                    state.completion_code,
                                  );
                                  setCodeCopied(true);
                                } catch {
                                  setCodeCopied(false);
                                }
                              }}
                            >
                              {codeCopied ? "Copied" : "Copy code"}
                            </button>
                          </div>
                        )}
                      {(stage === "study_resources" ||
                        (state.bounded_flow &&
                          stage === "diagnostic_quiz" &&
                          quizHelp?.content.startsWith("Review:"))) && (
                        <div className="resource-cards">
                          {!lesson.learning_plan.study_resources.length &&
                            materialLinks}
                          {lesson.learning_plan.study_resources.map(
                            (resource) => (
                              <a
                                className="resource-card lesson-resource"
                                key={resource.url}
                                href={resource.url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                <div>
                                  <small>{resource.provider}</small>
                                  {state.recommended_resource_url ===
                                    resource.url && (
                                    <small>
                                      {state.familiarity === "new"
                                        ? "Start here"
                                        : "Suggested for your focus"}
                                    </small>
                                  )}
                                  <strong>{resource.title}</strong>
                                  <p>{resource.description}</p>
                                  <p>
                                    <b>Focus:</b> {resource.focus}
                                  </p>
                                </div>
                                <b>↗</b>
                              </a>
                            ),
                          )}
                        </div>
                      )}
                      {stage === "welcome" && !state.bounded_flow && (
                        <div
                          className="learning-choices familiarity-choices"
                          aria-label="Your familiarity with this topic"
                        >
                          {[
                            "I'm completely new",
                            "I know some of this",
                            "I'm comfortable with this topic",
                          ].map((choice) => (
                            <button
                              className="secondary"
                              key={choice}
                              disabled={busy}
                              onClick={() =>
                                submitLessonTurn({ content: choice })
                              }
                            >
                              {choice}
                            </button>
                          ))}
                        </div>
                      )}
                      {stage === "study_resources" &&
                        state.study_concepts?.length > 0 && (
                          <div
                            className="learning-choices"
                            aria-label="Choose an unfamiliar concept"
                          >
                            {state.study_concepts.map((concept) => (
                              <button
                                key={concept}
                                className="secondary"
                                disabled={busy}
                                onClick={() =>
                                  submitLessonTurn({ content: concept })
                                }
                              >
                                {concept}
                              </button>
                            ))}
                          </div>
                        )}
                      {stage === "study_resources" && state.bounded_flow && (
                        <div className="learning-choices" aria-label="Choose how to prepare for the quiz">
                          <button className="secondary" disabled={busy}
                            onClick={() => submitLessonTurn({ content: "Explain with an example" })}>
                            Explain with an example
                          </button>
                          <button className="secondary" disabled={busy}
                            onClick={() => replyInput.current?.focus()}>
                            Ask a question
                          </button>
                        </div>
                      )}
                      {stage === "study_resources" && !state.bounded_flow && (
                        <div className="learning-choices">
                          <button
                            className="secondary"
                            disabled={busy}
                            onClick={() =>
                              submitLessonTurn({
                                content:
                                  state.familiarity === "comfortable"
                                    ? "Quick recap"
                                    : "Please explain more",
                              })
                            }
                          >
                            {state.familiarity === "comfortable"
                              ? "Quick recap"
                              : "Explain more"}
                          </button>
                        </div>
                      )}
                      {stage === "study_resources" && (
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() =>
                            submitLessonTurn({ content: "I am done" })
                          }
                        >
                          I'm ready for the quiz
                        </button>
                      )}
                      {stage === "diagnostic_quiz" && !state.bounded_flow && (
                        <>
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
                      {state.choices?.length > 0 &&
                        stage === "learning_choice" && (
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
                                <small>
                                  {state.choice_descriptions?.[choice]}
                                </small>
                              </button>
                            ))}
                          </div>
                        )}
                      {stage === "paused" && (
                        <div className="learning-choices">
                          <button
                            className="primary"
                            disabled={busy}
                            onClick={() =>
                              submitLessonTurn({ action: "resume" })
                            }
                          >
                            Resume learning
                          </button>
                          <button className="secondary" onClick={onBack}>
                            Return to my assignments
                          </button>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
              {stage !== "paused" && stage !== "completed" && (
                <form
                  className="composer"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (value.trim())
                      submitLessonTurn({
                        ...(stage === "application"
                          ? { action: "answer" }
                          : {}),
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
                    ref={replyInput}
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
                          ? "Or type your answer…"
                          : stage === "application"
                            ? "Type your response…"
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

function ChatMessage({ message, bounded, verdict }) {
  const student = message.role === "student";
  let content = message.content;
  if (student) {
    content = (
      {
        hint: "I'd like a hint and worked example.",
        continue: "Let’s continue.",
        pause: "Pause and save my progress.",
        resume: "I’m ready to continue.",
      }[content] || content
    ).replace(/; explanation:.*$/s, "");
  } else if (bounded) {
    // Previously saved conversations also avoid duplicating the active quiz card.
    content = content.startsWith("Five questions, with up to three attempts")
      ? "Okay, let’s take a small quiz based on the topics we just studied."
      : content
          .replace(/\n\nQuestion \d+ of 5[\s\S]*$/, "")
          .replace(/\b\d attempts remaining\.\s*/g, "")
          .replace(/Three attempts used\./g, "Let’s review this.")
          .replace(/You have one submission, followed by feedback\./g, "");
  }
  const paragraphs = student ? [content] : replyParagraphs(content);
  return (
    <div className={`sdl-message-group ${student ? "student" : "assistant"}`}>
      <span className="sdl-speaker">{student ? "You" : "Tutor"}</span>
      {paragraphs.map((paragraph, index) => (
        <article
          key={index}
          className={`message sdl-bubble ${student ? "student" : "assistant"} ${index === 0 && verdict === true ? "sdl-correct" : index === 0 && verdict === false ? "sdl-incorrect" : ""}`}
        >
          <p>
            {[
              "What you got right",
              "What you got wrong",
              "How to improve",
            ].some((heading) => paragraph.startsWith(heading + "\n")) ? (
              <>
                <strong>{paragraph.split("\n")[0]}</strong>
                <br />
                {paragraph.substring(paragraph.indexOf("\n") + 1)}
              </>
            ) : (
              paragraph
            )}
          </p>
        </article>
      ))}
      {message.sources?.length > 0 && (
        <div className="citations">
          {message.sources.map((source) => (
            <span key={source.document_id}>▤ {source.filename}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function QuestionCard({
  state,
  submitLessonTurn,
  disabled,
  records = [],
  readOnly = false,
}) {
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
  const latest = records.at(-1);
  const correctIndex = records.find(
    (record) => record.correct_index != null,
  )?.correct_index;
  const wrongOptions = records
    .filter((record) => record.correct === false)
    .map((record) => record.selected_index);
  if (state.bounded_flow)
    return (
      <section
        className="diagnostic-card sdl-quiz-card"
        aria-label={`Question ${state.quiz_index + 1}`}
      >
        <p className="eyebrow">Question {state.quiz_index + 1} of 5</p>
        <h3>{question.question}</h3>
        <label>
          Confidence <span className="help">(optional)</span>
          <select
            disabled={disabled || readOnly}
            value={readOnly ? latest?.confidence || "" : confidence}
            onChange={(e) => setConfidence(e.target.value)}
          >
            <option value="">Not reported</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </label>
        <div className="sdl-answer-options">
          {question.options.map((option, index) => (
            <button
              key={index}
              type="button"
              className={`secondary ${correctIndex === index ? "sdl-option-correct" : wrongOptions.includes(index) ? "sdl-option-incorrect" : latest?.pending && latest.selected_index === index ? "sdl-option-selected" : ""}`}
              aria-label={`Option ${String.fromCharCode(65 + index)}: ${option}${correctIndex === index ? " — correct" : wrongOptions.includes(index) ? " — incorrect" : ""}`}
              disabled={disabled || readOnly || wrongOptions.includes(index)}
              onClick={() =>
                submitLessonTurn({
                  action: "answer",
                  question_id: question.id,
                  option_index: index,
                  confidence: confidence || undefined,
                })
              }
            >
              <span>{String.fromCharCode(65 + index)}</span>
              {option}
              {correctIndex === index && <b aria-hidden="true">✓</b>}
              {wrongOptions.includes(index) && <b aria-hidden="true">✕</b>}
            </button>
          ))}
        </div>
        <div className="learning-choices">
          {
            <button
              type="button"
              className="secondary"
              disabled={disabled || readOnly}
              onClick={() =>
                submitLessonTurn({
                  content: "Read more",
                  question_id: question.id,
                })
              }
            >
              Read more
            </button>
          }
          <button
            type="button"
            className="secondary"
            disabled={disabled || readOnly}
            onClick={() =>
              submitLessonTurn({ action: "hint", question_id: question.id })
            }
          >
            Get a hint / worked example
          </button>
          <button
            type="button"
            className="quiet"
            disabled={disabled || readOnly}
            onClick={() =>
              submitLessonTurn({
                action: "answer",
                question_id: question.id,
                content: "I don't know",
                confidence: confidence || undefined,
              })
            }
          >
            I don’t know
          </button>
        </div>
      </section>
    );
  return (
    <div className="diagnostic-card">
      {state.bounded_flow && state.quiz_retry && (
        <button
          disabled={disabled}
          onClick={() =>
            submitLessonTurn({ content: "Read more", question_id: question.id })
          }
        >
          Read more
        </button>
      )}
      {!state.bounded_flow && (
        <p>
          Confidence and reasoning help choose your next practice; they don't
          change your quiz score.
        </p>
      )}
      <p className="eyebrow">Question {state.quiz_index + 1} of 5</p>
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
          {state.bounded_flow
            ? "Get a hint / worked example"
            : "Conceptual hint"}
        </button>
      </div>
    </div>
  );
}

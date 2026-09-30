import React, { useEffect, useRef, useState } from "react";
import { api } from "./api";

const stages = ["welcome", "study_resources", "diagnostic_quiz", "adaptive_learning", "reflection"];
const stageLabels = ["Welcome", "Study", "Understanding check", "Practice & recheck", "Reflect"];

export default function LessonWorkspace({ assignmentId, onBack }) {
  const [lesson, setLesson] = useState(null);
  const [attempt, setAttempt] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [value, setValue] = useState("");
  const pending = useRef(null);
  const end = useRef(null);
  const load = async () => {
    setBusy(true); setError("");
    try {
      const detail = await api(`/student/assignments/${assignmentId}`);
      setLesson(detail);
      const current = await api(`/student/assignments/${assignmentId}/start`, { method: "POST" });
      setAttempt(current);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  useEffect(() => { load(); }, [assignmentId]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [attempt?.messages.length]);
  const send = async (data, retry = false) => {
    if (busy) return;
    const body = retry ? pending.current : { ...data, turn_id: crypto.randomUUID() };
    if (!body) return;
    pending.current = body;
    setBusy(true); setError("");
    try {
      const next = await api(`/student/assignments/${assignmentId}/learning-turn`, { method: "POST", body: JSON.stringify(body) });
      setAttempt(next); setValue(""); pending.current = null;
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const state = attempt?.learning_state;
  const stage = state?.stage;
  const stageIndex = stages.indexOf(stage === "learning_choice" ? (state.reflections?.length ? "reflection" : "adaptive_learning") : stage);
  return <>
    <button className="back" onClick={onBack}>← My assignments</button>
    {error && <div className="notice error" role="alert">{error}<button disabled={busy} onClick={() => pending.current ? send(null, true) : load()}>Try again</button></div>}
    {!lesson || !attempt ? <p>{busy ? "Opening your lesson…" : "The lesson is not ready yet. Your instructor can review its setup."}</p> : <>
      <div className="workspace-head"><div><p className="eyebrow">Your lesson</p><h1>{lesson.learning_plan.topic}</h1></div><span>{stage === "paused" ? "Paused · progress saved" : "Learn at your own pace"}</span></div>
      <div className="workspace-grid">
        <aside>
          <ol className="lesson-stages" aria-label="Learning stages">{stageLabels.map((label, index) => <li key={label} className={index === stageIndex ? "active" : ""} aria-current={index === stageIndex ? "step" : undefined}><span>{index + 1}</span>{label}</li>)}</ol>
          <p className="eyebrow">Learning objectives</p>
          <div className="objectives">{attempt.objective_progress.map((objective, index) => <div key={objective.objective_id} className={`objective ${objective.status}`}><span>{objective.status === "demonstrated" ? "✓" : index + 1}</span><div><strong>{objective.title}</strong><small>{objective.status === "demonstrated" ? "Shown in an independent activity" : "Open for learning"}</small></div></div>)}</div>
          {state.diagnostic_complete && <div className="placement"><strong>Understanding check: {attempt.quiz_score}/5</strong><span>A starting point, not a mastery label</span></div>}
          <button className="secondary lesson-pause" disabled={busy} onClick={() => send({ action: stage === "paused" ? "resume" : "pause" })}>{stage === "paused" ? "Resume learning" : "Pause & save"}</button>
        </aside>
        <section className="chat lesson-chat" aria-label="Lesson conversation">
          <div className="messages" aria-live="polite" aria-relevant="additions">
            {attempt.messages.map(message => <article className={`message ${message.role}`} key={message.id}><div className="avatar">{message.role === "assistant" ? "A" : "You"}</div><div><p>{message.content}</p>{message.sources?.length > 0 && <div className="citations">{message.sources.map(source => <span key={source.document_id}>▤ {source.filename}</span>)}</div>}</div></article>)}
            {stage === "study_resources" && <div className="resource-cards">{lesson.learning_plan.study_resources.map(resource => <a className="resource-card lesson-resource" key={resource.url} href={resource.url} target="_blank" rel="noopener noreferrer"><div><small>{resource.provider}</small><strong>{resource.title}</strong><p>{resource.description}</p><p><b>Focus:</b> {resource.focus}</p></div><b>↗</b></a>)}</div>}
            {stage === "welcome" && <button className="secondary" disabled={busy} onClick={() => send({ content: "I am completely new to this topic." })}>I'm completely new</button>}
            {stage === "study_resources" && <button className="primary" disabled={busy} onClick={() => send({ content: "I am done" })}>I am done · start the check</button>}
            {stage === "diagnostic_quiz" && <QuestionCard key={state.current_question.id} state={state} send={send} disabled={busy} />}
            {stage === "adaptive_learning" && <button className="secondary" disabled={busy} onClick={() => send({ action: "hint" })}>Give me a hint</button>}
            {state.choices?.length > 0 && stage === "learning_choice" && <div className="learning-choices format-choices" aria-label="Choose how to learn">{state.choices.map(choice => <button className="secondary" key={choice} disabled={busy} onClick={() => send({ action: "choice", content: choice })}><strong>{choice}</strong><small>{state.choice_descriptions?.[choice]}</small></button>)}</div>}
            {stage === "paused" && <div className="learning-choices"><button className="primary" disabled={busy} onClick={() => send({ action: "resume" })}>Resume learning</button><button className="secondary" onClick={onBack}>Return to my assignments</button></div>}
            <div ref={end} />
          </div>
          {stage !== "paused" && <form className="composer" onSubmit={event => { event.preventDefault(); if (value.trim()) send({ content: value.trim(), question_id: state.current_question?.id }); }}><label className="sr-only" htmlFor="lesson-reply">Your reply</label><textarea id="lesson-reply" disabled={busy} value={value} onChange={event => setValue(event.target.value)} placeholder={stage === "welcome" ? "Tell me what feels unfamiliar…" : stage === "diagnostic_quiz" ? "Or reply naturally: B, medium confidence, because…" : stage === "reflection" ? "What can you explain or do now?" : "Ask a question, request an example, or explain your reasoning…"} /><button disabled={busy || !value.trim()}>{busy ? "Thinking…" : "Send"}</button><small>You can ask for help or pause whenever you need.</small></form>}
        </section>
      </div>
    </>}
  </>;
}

function QuestionCard({ state, send, disabled }) {
  const question = state.current_question;
  const [selection, setSelection] = useState(null);
  const [confidence, setConfidence] = useState("");
  const [explanation, setExplanation] = useState("");
  const answer = () => send({ action: state.metadata_requested ? "continue" : "answer", question_id: question.id, option_index: state.metadata_requested ? undefined : selection, confidence: confidence || undefined, explanation: explanation.trim() || undefined });
  return <div className="diagnostic-card">
    <p className="eyebrow">Question {state.quiz_index + 1} of 5 · {question.difficulty}</p>
    <fieldset disabled={disabled || state.metadata_requested} className="quiz-question"><legend>{question.question}</legend>{question.options.map((option, index) => <label key={index}><input type="radio" name={`question-${question.id}`} checked={(state.metadata_requested ? state.recorded_option : selection) === index} onChange={() => setSelection(index)} /><span>{String.fromCharCode(65 + index)}. {option}</span></label>)}</fieldset>
    <label>How confident are you?<select disabled={disabled} value={confidence} onChange={event => setConfidence(event.target.value)}><option value="">Not reported</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label>
    {state.quiz_index >= 3 && <label>Explain your choice in one sentence<textarea disabled={disabled} value={explanation} onChange={event => setExplanation(event.target.value)} placeholder="My reasoning is…" /></label>}
    <div className="learning-choices"><button className="primary" disabled={disabled || (!state.metadata_requested && selection === null)} onClick={answer}>{state.metadata_requested ? "Continue" : "Record answer"}</button>{state.metadata_requested ? <button className="secondary" disabled={disabled} onClick={() => send({ action: "continue", question_id: question.id })}>Continue without extra details</button> : <button className="secondary" disabled={disabled} onClick={() => send({ action: "answer", question_id: question.id, content: "I don't know", confidence: confidence || undefined })}>I don't know</button>}<button className="secondary" disabled={disabled} onClick={() => send({ action: "hint", question_id: question.id })}>Conceptual hint</button></div>
  </div>;
}

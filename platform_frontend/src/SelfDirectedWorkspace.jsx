import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Markdown from "react-markdown";
import { api } from "./api";
import { Notice } from "./ui";

function Status({ value }) {
  const label = (value || "not_started").replaceAll("_", " ");
  return <span className={`sdl-status ${value || "not_started"}`}>{label}</span>;
}

function StudyPhase({ resources, submit, busy }) {
  return (
    <section className="sdl-stage">
      <p className="context">Step 1 · Prepare</p>
      <h2>Study these resources first</h2>
      <p>Open each resource, take notes, and return when you are ready for a short placement quiz.</p>
      <div className="sdl-resources">
        {resources.map((resource, index) => (
          <a href={resource.url} target="_blank" rel="noreferrer" key={resource.url}>
            <span>{index + 1}</span>
            <div><small>{resource.provider}</small><strong>{resource.title}</strong></div>
            <b aria-hidden="true">↗</b>
          </a>
        ))}
      </div>
      <button disabled={busy} onClick={() => submit({ message: "I've finished studying" })}>
        {busy ? "Opening quiz…" : "I've studied these—start the quiz"}
      </button>
    </section>
  );
}

function QuizPhase({ questions, submit, busy }) {
  const [answers, setAnswers] = useState(() => Array(questions.length).fill(null));
  const ready = questions.length === 5 && answers.every((answer) => answer !== null);
  return (
    <section className="sdl-stage sdl-quiz">
      <p className="context">Step 2 · Diagnostic</p>
      <h2>Five-question placement quiz</h2>
      <p>This selects your starting path. It does not count as mastery.</p>
      {questions.map((question, questionIndex) => (
        <fieldset key={question.id}>
          <legend><span>{questionIndex + 1}</span>{question.question}</legend>
          {question.options.map((option, optionIndex) => (
            <label key={option}>
              <input
                type="radio"
                name={question.id}
                checked={answers[questionIndex] === optionIndex}
                onChange={() => setAnswers((current) => current.map((answer, index) => index === questionIndex ? optionIndex : answer))}
              />
              <span>{option}</span>
            </label>
          ))}
        </fieldset>
      ))}
      <button disabled={busy || !ready} onClick={() => submit({ answers })}>
        {busy ? "Scoring…" : "Submit quiz and begin"}
      </button>
    </section>
  );
}

function Conversation({ attempt, task, perform, busy }) {
  const [message, setMessage] = useState("");
  const endRef = useRef(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [attempt.messages.length]);
  const finalTask = attempt.phase === "required_task";
  const submit = async (event) => {
    event.preventDefault();
    const content = message.trim();
    if (!content || busy) return;
    const ok = await perform(finalTask ? "submit-task" : "messages", { content });
    if (ok) setMessage("");
  };
  return (
    <section className="sdl-conversation">
      <div className="sdl-messages" aria-live="polite" aria-busy={busy}>
        {attempt.messages.map((item) => (
          <article className={`message ${item.role === "student" ? "user" : "assistant"}`} key={item.id}>
            <span className="message-author">{item.role === "student" ? "You" : "Self-Directed Learning"}</span>
            <div className="prose"><Markdown>{item.content}</Markdown></div>
            {item.sources?.length > 0 && (
              <div className="sdl-citations">
                {item.sources.map((source) => <span key={`${source.document_id}-${source.filename}`}>▤ {source.filename}</span>)}
              </div>
            )}
          </article>
        ))}
        {attempt.status === "completed" && (
          <div className="sdl-complete"><span>✓</span><div><strong>Assignment complete</strong><p>Your work and evidence are available to your instructor.</p></div></div>
        )}
        {busy && <p className="working" role="status">Working on your response…</p>}
        <div ref={endRef} />
      </div>
      {attempt.status !== "completed" && (
        <form className={`composer ${finalTask ? "sdl-final" : ""}`} onSubmit={submit}>
          {finalTask && <div><p className="context">Final submission</p><strong>{task.submission_prompt}</strong></div>}
          <label className="sr-only" htmlFor="sdl-reply">{finalTask ? "Final submission" : "Your response"}</label>
          <textarea
            id="sdl-reply"
            rows={finalTask ? 8 : 3}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder={finalTask ? "Write or paste your completed work here…" : "Explain your thinking…"}
            disabled={busy}
          />
          <div><span className="help">{finalTask ? "Submit when your work is complete." : "Show your reasoning in your own words."}</span><button disabled={busy || !message.trim()}>{busy ? "Working…" : finalTask ? "Submit final task" : "Send response"}</button></div>
        </form>
      )}
    </section>
  );
}

export default function SelfDirectedWorkspace() {
  const { id } = useParams();
  const [assignment, setAssignment] = useState(null);
  const [attempt, setAttempt] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([
      api(`/platform/self-directed/assignments/${id}`),
      api(`/platform/self-directed/assignments/${id}/attempt`),
    ]).then(([detail, current]) => {
      if (active) { setAssignment(detail); setAttempt(current); }
    }).catch((reason) => active && setError(reason.message));
    return () => { active = false; };
  }, [id]);

  const perform = async (action, body) => {
    setBusy(true);
    setError("");
    try {
      setAttempt(await api(`/platform/self-directed/assignments/${id}/${action}`, { method: "POST", body }));
      return true;
    } catch (reason) {
      setError(reason.message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (!assignment) return <><Link className="back" to="/student">← My assignments</Link><Notice error={error} />{!error && <p>Opening Self-Directed Learning…</p>}</>;
  if (!attempt) return (
    <>
      <Link className="back" to="/student">← My assignments</Link>
      <Notice error={error} />
      <section className="sdl-start">
        <p className="context">Self-Directed Learning</p>
        <h1>{assignment.title}</h1>
        <p>{assignment.instructions}</p>
        <div><span><strong>{assignment.learning_plan.objectives.length}</strong> objectives</span><span><strong>5</strong> quiz questions</span><span><strong>1</strong> final task</span></div>
        <button disabled={busy} onClick={() => perform("start")}>{busy ? "Starting…" : "Start learning"}</button>
      </section>
    </>
  );

  const demonstrated = attempt.objective_progress.filter((item) => item.status === "demonstrated").length;
  const content = attempt.phase === "study_resources"
    ? <StudyPhase resources={assignment.learning_plan.study_resources || []} submit={(body) => perform("study-complete", body)} busy={busy} />
    : attempt.phase === "diagnostic_quiz"
      ? <QuizPhase questions={assignment.learning_plan.diagnostic_quiz || []} submit={(body) => perform("quiz", body)} busy={busy} />
      : <Conversation attempt={attempt} task={assignment.learning_plan.required_task} perform={perform} busy={busy} />;

  return (
    <>
      <Link className="back" to="/student">← My assignments</Link>
      <div className="page-heading sdl-heading"><div><p className="context">Self-Directed Learning</p><h1>{assignment.title}</h1></div><Status value={attempt.status} /></div>
      <Notice error={error} />
      <div className="workspace-grid sdl-workspace">
        <aside className="assignment-info">
          <p className="context">Learning path</p>
          {attempt.learning_path ? <div className="sdl-placement"><strong>{attempt.learning_path}</strong><span>{attempt.quiz_score}/5 diagnostic score</span></div> : <div className="sdl-placement pending"><strong>Placement pending</strong><span>Study first, then complete the quiz</span></div>}
          <h3>Objectives</h3>
          <p className="help">{demonstrated} of {attempt.objective_progress.length} demonstrated</p>
          <div className="sdl-objectives">
            {attempt.objective_progress.map((objective, index) => <div className={objective.status} key={objective.objective_id}><span>{objective.status === "demonstrated" ? "✓" : index + 1}</span><div><strong>{objective.title}</strong><small>{objective.status.replaceAll("_", " ")}</small></div></div>)}
          </div>
          <div className={`sdl-task ${attempt.phase === "required_task" ? "ready" : ""}`}><p className="context">Final task</p><strong>{assignment.learning_plan.required_task.title}</strong><p>{assignment.learning_plan.required_task.description}</p><Status value={attempt.required_task_status} /></div>
        </aside>
        {content}
      </div>
    </>
  );
}

import React, { useEffect, useRef, useState } from "react";
import { api, currentUser, setCurrentUser } from "./api";
import "./styles.css";
import LessonWorkspace from "./LessonWorkspace";

function Status({ value }) {
  return <span className={`status ${value || "not-started"}`}>{(value || "not started").replaceAll("_", " ")}</span>;
}

export function App({ loadUsers = () => fetch("/api/demo/users?role=student").then(res => res.json()), initialAssignmentId = null }) {
  const [users, setUsers] = useState([]); const [user, setUser] = useState(null); const [assignments, setAssignments] = useState(null); const [selected, setSelected] = useState(null); const [error, setError] = useState("");
  const load = async () => { try { setError(""); const people = await loadUsers(); setUsers(people); const active = people.find((item) => item.id === currentUser()) || people[0]; if (active) { setCurrentUser(active.id); setUser(active); const items = await api("/student/assignments"); setAssignments(items); if (initialAssignmentId && !assignments) setSelected(initialAssignmentId); } } catch (e) { setError(e.message); } };
  useEffect(() => { load(); }, []);
  const changeUser = async (id) => { setCurrentUser(id); setSelected(null); await load(); };
  return <div className="shell"><header><button className="brand" onClick={() => { setSelected(null); load(); }}><span className="brand-mark">A</span><span>Adaptive Learning<small>Student workspace</small></span></button><label className="user-switch">Viewing as<select value={user?.id || ""} onChange={(e) => changeUser(e.target.value)}>{users.map((person) => <option value={person.id} key={person.id}>{person.display_name}</option>)}</select></label></header>
    <main>{error && <div className="notice error">{error}</div>}{selected ? (assignments?.find(item => item.id === selected)?.learning_plan.flow_version === 2 ? <LessonWorkspace key={`${user?.id}-${selected}`} assignmentId={selected} onBack={() => { setSelected(null); load(); }} /> : <Workspace key={`${user?.id}-${selected}`} user={user} assignmentId={selected} onBack={() => { setSelected(null); load(); }} />) : <AssignmentList assignments={assignments} user={user} onOpen={setSelected} />}</main>
  </div>;
}

function AssignmentList({ assignments, user, onOpen }) {
  return <><section className="welcome"><div><p className="eyebrow">Student workspace</p><h1>Welcome back, {user?.display_name?.split(" ")[0] || "student"}.</h1><p>Continue an assignment or begin something new. Your tutor adjusts to the evidence you show.</p></div><div className="orb"><span>{assignments?.filter((item) => item.attempt_status === "completed").length || 0}</span><small>completed</small></div></section>
    <section className="section-head"><div><p className="eyebrow">Learning queue</p><h2>Your assignments</h2></div><span>{assignments?.length || 0} assigned</span></section>
    {!assignments ? <p>Loading assignments…</p> : !assignments.length ? <div className="empty">No published assignments are waiting for you.</div> : <div className="assignment-list">{assignments.map((item, index) => <button key={item.id} className="assignment" onClick={() => onOpen(item.id)}><div className="index">{String(index + 1).padStart(2, "0")}</div><div className="assignment-copy"><div><Status value={item.attempt_status} /><span>{item.learning_plan.objectives.length} objectives</span></div><h3>{item.title}</h3><p>{item.instructions}</p></div><div className="arrow">→</div></button>)}</div>}
  </>;
}

function Workspace({ assignmentId, user, onBack }) {
  const [assignment, setAssignment] = useState(null); const [attempt, setAttempt] = useState(null); const [error, setError] = useState(""); const [sending, setSending] = useState(false); const endRef = useRef(null);
  const load = async () => { try { setError(""); const [detail, current] = await Promise.all([api(`/student/assignments/${assignmentId}`), api(`/student/assignments/${assignmentId}/attempt`)]); setAssignment(detail); setAttempt(current); } catch (e) { setError(e.message); } };
  useEffect(() => { load(); }, [assignmentId]); useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [attempt?.messages?.length]);
  const completeStudy = async (message) => { setSending(true); setError(""); try { setAttempt(await api(`/student/assignments/${assignmentId}/study-complete`, { method: "POST", body: JSON.stringify({ message }) })); } catch (e) { setError(e.message); } finally { setSending(false); } };
  const submitQuiz = async (answers) => { setSending(true); setError(""); try { setAttempt(await api(`/student/assignments/${assignmentId}/quiz`, { method: "POST", body: JSON.stringify({ answers }) })); } catch (e) { setError(e.message); } finally { setSending(false); } };
  const send = async (content) => { setSending(true); setError(""); try { setAttempt(await api(`/student/assignments/${assignmentId}/messages`, { method: "POST", body: JSON.stringify({ content }) })); } catch (e) { setError(e.message); } finally { setSending(false); } };
  const submitTask = async (content) => { setSending(true); setError(""); try { setAttempt(await api(`/student/assignments/${assignmentId}/submit-task`, { method: "POST", body: JSON.stringify({ content }) })); } catch (e) { setError(e.message); } finally { setSending(false); } };
  if (!assignment) return <><button className="back" onClick={onBack}>← My assignments</button>{error ? <div className="notice error">{error}<button onClick={load}>Try again</button></div> : <p>Loading workspace…</p>}</>;
  if (!attempt) return <><button className="back" onClick={onBack}>← My assignments</button><StudyPhase user={user} plan={assignment.learning_plan} complete={async (message) => { setSending(true); setError(""); try { await api(`/student/assignments/${assignmentId}/start`, { method: "POST" }); await completeStudy(message); } catch (e) { setError(e.message); } finally { setSending(false); } }} disabled={sending} />{error && <div className="notice error">{error}</div>}</>;
  const readyForTask = attempt.phase === "required_task";
  const phaseContent = attempt.phase === "study_resources"
    ? <StudyPhase user={user} plan={assignment.learning_plan} complete={completeStudy} disabled={sending} />
    : attempt.phase === "diagnostic_quiz"
      ? <QuizPhase questions={assignment.learning_plan.diagnostic_quiz || []} submit={submitQuiz} disabled={sending} />
      : <section className="chat"><div className="messages"><p className="eyebrow">{attempt.status === "completed" ? "Session complete" : readyForTask ? "Step 4 · Final write-up" : "Step 3 · Questions & examples"}</p>{attempt.messages.map((message) => <Message message={message} key={message.id} />)}{attempt.status === "completed" && <div className="complete-card"><span>✓</span><div><strong>Thank you, {user?.display_name?.split(" ")[0]}!</strong><p>Your write-up is saved. You can leave the session now.</p><button onClick={onBack}>Exit session</button></div></div>}<div ref={endRef} /></div>{attempt.status !== "completed" && (readyForTask ? <TaskComposer task={assignment.learning_plan.required_task} submit={submitTask} disabled={sending} /> : <Composer send={send} disabled={sending} />)}</section>;
  return <><button className="back" onClick={onBack}>← My assignments</button><div className="workspace-head"><div><Status value={attempt.status} /><h1>{assignment.title}</h1></div><span>{attempt.objective_progress.filter((item) => item.status === "demonstrated").length}/{attempt.objective_progress.length} objectives demonstrated</span></div><div className="workspace-grid"><aside><p className="eyebrow">Learning path</p>{attempt.learning_path ? <div className="placement"><strong>{attempt.learning_path}</strong><span>{attempt.quiz_score}/5 diagnostic score</span></div> : <div className="placement pending"><strong>Placement pending</strong><span>Complete the study and quiz steps</span></div>}<div className="objectives">{attempt.objective_progress.map((objective, index) => <div className={`objective ${objective.status}`} key={objective.objective_id}><span>{objective.status === "demonstrated" ? "✓" : index + 1}</span><div><strong>{objective.title}</strong><small>{objective.status.replaceAll("_", " ")}</small></div></div>)}</div><div className={`task-card ${readyForTask ? "ready" : ""}`}><p className="eyebrow">Required task</p><strong>{assignment.learning_plan.required_task.title}</strong><p>{assignment.learning_plan.required_task.description}</p><Status value={attempt.required_task_status} /></div>{assignment.documents.length > 0 && <div className="source-list"><p className="eyebrow">Course sources</p>{assignment.documents.map((doc) => <span key={doc.id}>▤ {doc.filename}</span>)}</div>}</aside>{phaseContent}</div>{error && <div className="notice error floating">{error}</div>}</>;
}

function StudyPhase({ user, plan, complete, disabled }) {
  const [message, setMessage] = useState("");
  const resources = plan.study_resources || [];
  return <section className="study-phase"><p className="eyebrow">Step 1 · Study</p><h2>Hi {user?.display_name?.split(" ")[0] || "student"}, today we are going to discuss {plan.topic || plan.title}.</h2><p className="topic-introduction">{plan.topic_introduction}</p><h3>A few links to study before we continue</h3><p>Read these resources and look for examples that help explain the topic. When you are done, come back for a short diagnostic quiz.</p>{resources.length ? <div className="resource-cards">{resources.map((resource, index) => <a className="resource-card" href={resource.url} target="_blank" rel="noopener noreferrer" key={resource.url}><span>{index + 1}</span><div><small>{resource.provider}</small><strong>{resource.title}</strong></div><b>↗</b></a>)}</div> : <p className="notice error">Topic-specific study links are unavailable. Ask your instructor to refresh the study resources before continuing.</p>}<button className="primary" disabled={disabled || !resources.length} onClick={() => complete("I am done")}>{disabled ? "Opening quiz…" : "I am done"}</button><form onSubmit={(event) => { event.preventDefault(); if (message.trim() && !disabled && resources.length) complete(message.trim()); }}><label htmlFor="study-ready">Or tell me when you have finished studying</label><div className="readiness-reply"><input id="study-ready" value={message} disabled={disabled} placeholder="I'm done studying, let's continue…" onChange={(event) => setMessage(event.target.value)} /><button disabled={disabled || !message.trim() || !resources.length}>Send</button></div></form></section>;
}

function QuizPhase({ questions, submit, disabled }) {
  const [answers, setAnswers] = useState(Array(questions.length).fill(null));
  const complete = answers.length === 5 && answers.every((answer) => answer !== null);
  const levels = ["Basics", "Understanding", "Application", "Analysis", "Challenge"];
  return <section className="quiz-phase"><p className="eyebrow">Step 2 · Diagnostic</p><h2>Now let's take a short quiz</h2><p>These five multiple-choice questions get progressively harder and help assess your understanding. Afterward, we will reason through examples together.</p>{questions.map((question, questionIndex) => <fieldset className="quiz-question" key={question.id} disabled={disabled}><legend><small className="difficulty-label">Level {questionIndex + 1} · {levels[questionIndex]}</small><span>{questionIndex + 1}</span>{question.question}</legend>{question.options.map((option, optionIndex) => <label key={option}><input type="radio" name={question.id} checked={answers[questionIndex] === optionIndex} onChange={() => setAnswers(answers.map((answer, index) => index === questionIndex ? optionIndex : answer))} /><span>{option}</span></label>)}</fieldset>)}<button className="primary" disabled={disabled || !complete} onClick={() => submit(answers)}>{disabled ? "Scoring…" : "Submit quiz and start Q&A"}</button></section>;
}

function Message({ message }) {
  return <article className={`message ${message.role}`}><div className="avatar">{message.role === "assistant" ? "A" : "You"}</div><div><p>{message.content}</p>{message.sources?.length > 0 && <div className="citations">{message.sources.map((source) => <span key={`${source.document_id}-${source.filename}`}>▤ {source.filename}</span>)}</div>}<time>{new Date(message.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</time></div></article>;
}

function Composer({ send, disabled }) {
  const [value, setValue] = useState(""); const submit = (event) => { event.preventDefault(); if (!value.trim() || disabled) return; const content = value.trim(); setValue(""); send(content); };
  return <form className="composer" onSubmit={submit}><textarea value={value} onChange={(e) => setValue(e.target.value)} placeholder="Explain your reasoning with an example, or ask for a hint or analogy…" onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) submit(e); }} /><button disabled={disabled || !value.trim()}>{disabled ? "Thinking…" : "Send"}</button><small>Press Enter to send · Shift + Enter for a new line</small></form>;
}

function TaskComposer({ task, submit, disabled }) {
  const [value, setValue] = useState(""); return <form className="task-composer" onSubmit={(e) => { e.preventDefault(); if (value.trim()) submit(value.trim()); }}><div><p className="eyebrow">Final write-up</p><strong>{task.submission_prompt}</strong><p>Write in your own words. Explain what you learned, apply it to a concrete example, and describe your reasoning.</p></div><textarea value={value} onChange={(e) => setValue(e.target.value)} placeholder="Write or paste your completed work here…" /><button className="primary" disabled={disabled || !value.trim()}>{disabled ? "Submitting…" : "Submit required task"}</button></form>;
}

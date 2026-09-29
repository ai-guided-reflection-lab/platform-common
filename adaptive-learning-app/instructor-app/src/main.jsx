import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import "./styles.css";

const blankObjective = (number) => ({
  id: `OBJECTIVE-${number}`,
  title: "",
  description: "",
  success_criteria: [""],
  diagnostic_prompt: "",
});

const initialDraft = {
  title: "",
  instructions: "",
  student_ids: [],
  learning_plan: {
    title: "",
    course_context: "",
    objectives: [blankObjective(1)],
    required_task: { title: "", description: "", submission_prompt: "" },
  },
};

function Notice({ children, error = false }) {
  return children ? <div className={error ? "notice error" : "notice"}>{children}</div> : null;
}

function Status({ value }) {
  return <span className={`status ${value || "not-started"}`}>{(value || "not started").replaceAll("_", " ")}</span>;
}

function App() {
  const [assignments, setAssignments] = useState(null);
  const [students, setStudents] = useState([]);
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const load = async () => {
    try {
      setError("");
      const [items, people] = await Promise.all([
        api("/instructor/assignments"),
        fetch("/api/demo/users?role=student").then((res) => res.json()),
      ]);
      setAssignments(items);
      setStudents(people);
    } catch (e) {
      setError(e.message);
    }
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="shell">
      <header>
        <button className="brand" onClick={() => { setSelected(null); setCreating(false); }}>
          <span className="brand-mark">A</span>
          <span>Adaptive Learning<small>Instructor studio</small></span>
        </button>
        <div className="identity"><span className="live-dot" /> Dr. Taylor · Demo instructor</div>
      </header>
      <main>
        <Notice error>{error}</Notice>
        {creating ? (
          <AssignmentForm students={students} onCancel={() => setCreating(false)} onSaved={(item) => { setCreating(false); setSelected(item.id); load(); }} />
        ) : selected ? (
          <AssignmentDetail id={selected} onBack={() => { setSelected(null); load(); }} />
        ) : (
          <Dashboard assignments={assignments} onCreate={() => setCreating(true)} onOpen={setSelected} />
        )}
      </main>
    </div>
  );
}

function Dashboard({ assignments, onCreate, onOpen }) {
  return (
    <>
      <section className="hero">
        <div><p className="eyebrow">Instructor workspace</p><h1>Design learning that responds.</h1><p>Create adaptive assignments, ground them in your course material, and follow each student’s evidence of learning.</p></div>
        <button className="primary" onClick={onCreate}>Create assignment</button>
      </section>
      <section className="section-head"><div><p className="eyebrow">Your work</p><h2>Assignments</h2></div><span>{assignments?.length || 0} total</span></section>
      {!assignments ? <p>Loading assignments…</p> : !assignments.length ? <div className="empty">Create your first assignment to begin.</div> : (
        <div className="cards">
          {assignments.map((item) => (
            <button className="assignment-card" key={item.id} onClick={() => onOpen(item.id)}>
              <div className="card-top"><Status value={item.status} /><span>{item.learning_plan.objectives.length} objectives</span></div>
              <h3>{item.title}</h3><p>{item.instructions || item.learning_plan.course_context}</p>
              <div className="metrics"><span><strong>{item.recipient_count}</strong> students</span><span><strong>{item.completed_count}</strong> complete</span></div>
            </button>
          ))}
        </div>
      )}
    </>
  );
}

function AssignmentForm(props) {
  const [mode, setMode] = useState("quick");
  return <div className="setup-page">
    <div className="setup-switch" role="tablist" aria-label="Assignment setup mode">
      <button type="button" role="tab" aria-selected={mode === "quick"} className={mode === "quick" ? "active" : ""} onClick={() => setMode("quick")}>Quick setup</button>
      <button type="button" role="tab" aria-selected={mode === "advanced"} className={mode === "advanced" ? "active" : ""} onClick={() => setMode("advanced")}>Advanced setup</button>
    </div>
    {mode === "quick" ? <QuickAssignmentForm {...props} /> : <AdvancedAssignmentForm {...props} />}
  </div>;
}

function QuickAssignmentForm({ students, onCancel, onSaved }) {
  const [topic, setTopic] = useState("");
  const [courseLevel, setCourseLevel] = useState("Undergraduate");
  const [studentIds, setStudentIds] = useState(() => students.map((student) => student.id));
  const [file, setFile] = useState(null);
  const [working, setWorking] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState("");

  const create = async (event) => {
    event.preventDefault();
    setWorking(true); setError("");
    try {
      setStage("Generating the learning plan…");
      const plan = await api("/instructor/generate-plan", {
        method: "POST",
        body: JSON.stringify({ topic, course_level: courseLevel }),
      });
      setStage("Creating the assignment…");
      const assignment = await api("/instructor/assignments", {
        method: "POST",
        body: JSON.stringify({
          title: plan.title,
          instructions: `Work through the adaptive activities for ${topic}. Explain your reasoning, use the tutor feedback, and complete the required task.`,
          learning_plan: plan,
          student_ids: studentIds,
        }),
      });
      if (file) {
        setStage("Indexing your course material…");
        const upload = new FormData(); upload.append("file", file);
        await api(`/instructor/assignments/${assignment.id}/documents`, { method: "POST", body: upload });
      }
      setStage("Publishing to students…");
      const published = await api(`/instructor/assignments/${assignment.id}/publish`, { method: "POST" });
      onSaved(published);
    } catch (e) {
      setError(e.message); setWorking(false); setStage("");
    }
  };

  return <form className="quick-editor" onSubmit={create}>
    <button type="button" className="back" onClick={onCancel}>← Assignments</button>
    <section className="quick-hero">
      <div className="spark">✦</div>
      <p className="eyebrow">AI-assisted setup</p>
      <h1>What should students learn?</h1>
      <p>Choose a topic. We’ll create the objectives, diagnostics, adaptive activities, and final task for you.</p>
    </section>
    <Notice error>{error}</Notice>
    <section className="panel quick-panel">
      <label className="topic-field">Topic
        <input required autoFocus value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="For example: Large Language Models" />
      </label>
      <div className="quick-options">
        <label>Course level<select value={courseLevel} onChange={(e) => setCourseLevel(e.target.value)}><option>Undergraduate</option><option>Introductory undergraduate</option><option>Upper-level undergraduate</option></select></label>
        <label className="file-pick">Course content <span>optional</span><input type="file" accept=".pdf,.txt,.md" onChange={(e) => setFile(e.target.files[0] || null)} /><div>{file ? `▤ ${file.name}` : "＋ Add a PDF, Markdown, or text file"}</div></label>
      </div>
      <details className="recipient-details"><summary>{studentIds.length} students selected</summary><div className="student-picks">{students.map((student) => <label className="check" key={student.id}><input type="checkbox" checked={studentIds.includes(student.id)} onChange={(e) => setStudentIds(e.target.checked ? [...studentIds, student.id] : studentIds.filter((id) => id !== student.id))} /><span><strong>{student.display_name}</strong><small>{student.email}</small></span></label>)}</div></details>
      <button className="primary launch" disabled={working || !topic.trim() || !studentIds.length}>{working ? stage : "Generate and publish assignment"}<span>→</span></button>
      <p className="quick-note">You can inspect the generated learning plan and student progress after publishing.</p>
    </section>
  </form>;
}

function AdvancedAssignmentForm({ students, onCancel, onSaved }) {
  const [draft, setDraft] = useState(initialDraft);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const plan = draft.learning_plan;
  const updatePlan = (patch) => setDraft({ ...draft, learning_plan: { ...plan, ...patch } });
  const updateObjective = (index, patch) => updatePlan({ objectives: plan.objectives.map((item, i) => i === index ? { ...item, ...patch } : item) });
  const save = async (event) => {
    event.preventDefault(); setSaving(true); setError("");
    try { onSaved(await api("/instructor/assignments", { method: "POST", body: JSON.stringify(draft) })); }
    catch (e) { setError(e.message); setSaving(false); }
  };
  return (
    <form className="editor" onSubmit={save}>
      <div className="editor-head"><div><button type="button" className="back" onClick={onCancel}>← Assignments</button><h1>New adaptive assignment</h1><p>Define what students must demonstrate. Course documents can be added after saving the draft.</p></div><button className="primary" disabled={saving}>{saving ? "Saving…" : "Save draft"}</button></div>
      <Notice error>{error}</Notice>
      <section className="panel"><p className="step">01 · Assignment</p><div className="field-grid"><label>Assignment title<input required value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} placeholder="Requirements engineering practice" /></label><label>Learning-plan title<input required value={plan.title} onChange={(e) => updatePlan({ title: e.target.value })} placeholder="Requirements engineering" /></label></div><label>Student instructions<textarea required value={draft.instructions} onChange={(e) => setDraft({ ...draft, instructions: e.target.value })} /></label><label>Course context<textarea value={plan.course_context} onChange={(e) => updatePlan({ course_context: e.target.value })} /></label></section>
      <section className="panel"><div className="panel-title"><div><p className="step">02 · Objectives</p><h2>Evidence students must show</h2></div><button type="button" className="secondary" onClick={() => updatePlan({ objectives: [...plan.objectives, blankObjective(plan.objectives.length + 1)] })}>Add objective</button></div>
        {plan.objectives.map((objective, index) => <ObjectiveEditor key={index} objective={objective} index={index} update={(patch) => updateObjective(index, patch)} remove={() => updatePlan({ objectives: plan.objectives.filter((_, i) => i !== index) })} canRemove={plan.objectives.length > 1} />)}
      </section>
      <section className="panel"><p className="step">03 · Required task</p><div className="field-grid"><label>Task title<input required value={plan.required_task.title} onChange={(e) => updatePlan({ required_task: { ...plan.required_task, title: e.target.value } })} /></label><label>Submission prompt<input required value={plan.required_task.submission_prompt} onChange={(e) => updatePlan({ required_task: { ...plan.required_task, submission_prompt: e.target.value } })} /></label></div><label>Description<textarea required value={plan.required_task.description} onChange={(e) => updatePlan({ required_task: { ...plan.required_task, description: e.target.value } })} /></label></section>
      <section className="panel"><p className="step">04 · Students</p><div className="student-picks">{students.map((student) => <label className="check" key={student.id}><input type="checkbox" checked={draft.student_ids.includes(student.id)} onChange={(e) => setDraft({ ...draft, student_ids: e.target.checked ? [...draft.student_ids, student.id] : draft.student_ids.filter((id) => id !== student.id) })} /><span><strong>{student.display_name}</strong><small>{student.email}</small></span></label>)}</div></section>
    </form>
  );
}

function ObjectiveEditor({ objective, index, update, remove, canRemove }) {
  return <div className="objective"><div className="objective-number">{String(index + 1).padStart(2, "0")}</div><div className="objective-fields"><div className="field-grid"><label>Objective ID<input required value={objective.id} onChange={(e) => update({ id: e.target.value })} /></label><label>Short title<input required value={objective.title} onChange={(e) => update({ title: e.target.value })} /></label></div><label>Description<textarea required value={objective.description} onChange={(e) => update({ description: e.target.value })} /></label><label>Success criteria<textarea required value={objective.success_criteria.join("\n")} onChange={(e) => update({ success_criteria: e.target.value.split("\n").filter(Boolean) })} placeholder="One criterion per line" /></label><label>Diagnostic prompt<textarea required value={objective.diagnostic_prompt} onChange={(e) => update({ diagnostic_prompt: e.target.value })} /></label>{canRemove && <button type="button" className="danger-link" onClick={remove}>Remove objective</button>}</div></div>;
}

function AssignmentDetail({ id, onBack }) {
  const [item, setItem] = useState(null); const [progress, setProgress] = useState([]); const [error, setError] = useState(""); const [uploading, setUploading] = useState(false); const [studentDetail, setStudentDetail] = useState(null); const [studentLoading, setStudentLoading] = useState(false);
  const load = async () => { try { setError(""); const [detail, rows] = await Promise.all([api(`/instructor/assignments/${id}`), api(`/instructor/assignments/${id}/progress`)]); setItem(detail); setProgress(rows); } catch (e) { setError(e.message); } };
  useEffect(() => { load(); }, [id]);
  const upload = async (event) => { const file = event.target.files[0]; if (!file) return; setUploading(true); const body = new FormData(); body.append("file", file); try { await api(`/instructor/assignments/${id}/documents`, { method: "POST", body }); await load(); } catch (e) { setError(e.message); } finally { setUploading(false); event.target.value = ""; } };
  const publish = async () => { try { await api(`/instructor/assignments/${id}/publish`, { method: "POST" }); load(); } catch (e) { setError(e.message); } };
  const openStudent = async (studentId) => { setStudentLoading(true); setError(""); try { setStudentDetail(await api(`/instructor/assignments/${id}/students/${studentId}`)); } catch (e) { setError(e.message); } finally { setStudentLoading(false); } };
  if (!item) return <><button className="back" onClick={onBack}>← Assignments</button><Notice error>{error}</Notice><p>Loading assignment…</p></>;
  return <><button className="back" onClick={onBack}>← Assignments</button><div className="detail-title"><div><Status value={item.status} /><h1>{item.title}</h1><p>{item.instructions}</p></div>{item.status === "draft" && <button className="primary" onClick={publish}>Publish assignment</button>}</div><Notice error>{error}</Notice>
    <div className="detail-grid"><section className="panel"><p className="step">Learning plan</p><h2>{item.learning_plan.title}</h2><p>{item.learning_plan.course_context}</p><div className="objective-list">{item.learning_plan.objectives.map((objective, index) => <div key={objective.id}><span>{index + 1}</span><div><strong>{objective.title}</strong><p>{objective.description}</p></div></div>)}</div>{item.learning_plan.study_resources?.length > 0 && <div className="published-resources"><p className="step">Automatically published resources</p>{item.learning_plan.study_resources.map((resource) => <a href={resource.url} target="_blank" rel="noreferrer" key={resource.url}><span>↗</span><div><strong>{resource.title}</strong><small>{resource.provider}</small></div></a>)}<p>{item.learning_plan.diagnostic_quiz?.length || 0} diagnostic questions · foundational, standard, and accelerated paths</p></div>}</section>
      <section className="panel"><p className="step">Course knowledge</p><h2>RAG documents</h2><p>PDF, Markdown, and text files are chunked and embedded for source-grounded tutoring.</p>{item.status === "draft" && <label className="upload"><input type="file" accept=".pdf,.txt,.md" onChange={upload} disabled={uploading} />{uploading ? "Indexing document…" : "Upload course document"}</label>}<div className="document-list">{item.documents.length ? item.documents.map((doc) => <div key={doc.id}><span>▤</span><div><strong>{doc.filename}</strong><small>{doc.chunk_count} indexed chunks</small></div></div>) : <p className="muted">No documents yet. The tutor can still use the learning plan.</p>}</div></section></div>
    <section className="panel progress-panel"><div className="panel-title"><div><p className="step">Student evidence</p><h2>Progress</h2></div><span>{progress.filter((row) => row.status === "completed").length} of {progress.length} complete</span></div><p className="row-hint">Select a student to inspect their quiz, responses, tutor feedback, and final submission.</p><div className="progress-table">{progress.map((row) => <button type="button" className="progress-row" key={row.student_id} onClick={() => openStudent(row.student_id)} disabled={studentLoading}><div><strong>{row.display_name}</strong><small>{row.email}</small></div><Status value={row.status} /><span className="phase-label">{row.phase?.replaceAll("_", " ") || "not started"}</span><span className="quiz-result">{row.quiz_score === null || row.quiz_score === undefined ? "Quiz —" : `Quiz ${row.quiz_score}/5`}</span><strong className="path-label">{row.learning_path || "—"}</strong><div className="mini-objectives">{row.objective_progress.length ? row.objective_progress.map((objective) => <span className={objective.status} title={`${objective.title}: ${objective.status}`} key={objective.objective_id} />) : <span className="muted">Not started</span>}</div><span className="row-arrow">View →</span></button>)}</div></section>
    {studentDetail && <StudentEvidenceDetail detail={studentDetail} close={() => setStudentDetail(null)} />}
  </>;
}

function StudentEvidenceDetail({ detail, close }) {
  const { student, attempt, evidence, quiz_results: quizResults } = detail;
  const [showConversation, setShowConversation] = useState(false);
  return <div className="evidence-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}><section className="evidence-drawer" role="dialog" aria-modal="true" aria-label={`${student.display_name} evidence`}><div className="drawer-head"><div><p className="step">Student detail</p><h2>{student.display_name}</h2><span>{student.email}</span></div><button type="button" className="close-detail" onClick={close} aria-label="Close student detail">×</button></div>
    {!attempt ? <div className="empty">This student has not started the assignment.</div> : <>
      <div className="detail-metrics"><div><small>Status</small><Status value={attempt.status} /></div><div><small>Diagnostic</small><strong>{attempt.quiz_score ?? "—"}/5</strong></div><div><small>Learning path</small><strong>{attempt.learning_path || "—"}</strong></div><div><small>Objectives</small><strong>{attempt.objective_progress.filter((objective) => objective.status === "demonstrated").length}/{attempt.objective_progress.length}</strong></div></div>
      {detail.summary && <section className="student-summary"><div className="summary-intro"><p className="step">Whole-student summary</p><h3>What {student.display_name.split(" ")[0]} knows and should improve</h3><p>{detail.summary.overview}</p></div><div className="summary-grid"><SummaryCard title="Understands" tone="strength" items={detail.summary.strengths} /><SummaryCard title="Needs support" tone="weakness" items={detail.summary.weaknesses} /><SummaryCard title="Next improvements" tone="improvement" items={detail.summary.improvements} /></div></section>}
      {quizResults.length > 0 && <section className="evidence-section"><div className="section-label"><h3>Diagnostic quiz</h3><span>{attempt.quiz_score}/5 correct</span></div><div className="quiz-review">{quizResults.map((result, index) => <article className={result.correct ? "correct" : "incorrect"} key={result.id}><div className="result-mark">{result.correct ? "✓" : "×"}</div><div><strong>{index + 1}. {result.question}</strong><p>Your answer: {result.selected_answer || "No answer"}</p>{!result.correct && <p>Correct answer: {result.correct_answer}</p>}<small>{result.explanation}</small></div></article>)}</div></section>}
      <section className="evidence-section"><div className="section-label"><h3>Objective evidence</h3><span>{evidence.length} responses assessed</span></div>{evidence.length ? <div className="evidence-list">{evidence.map((entry) => <article key={entry.id}><div><strong>{entry.objective_title}</strong><Status value={entry.demonstrated ? "completed" : "in_progress"} /></div><blockquote>{entry.response}</blockquote><p>{entry.rationale}</p><small>Score {Math.round(entry.score * 100)}%</small></article>)}</div> : <p className="muted">No free-response evidence yet.</p>}</section>
      <section className="evidence-section conversation-section"><div className="section-label"><div><h3>Learning conversation</h3><span>{attempt.messages.length} messages · hidden by default</span></div><button type="button" className="secondary conversation-toggle" onClick={() => setShowConversation(!showConversation)}>{showConversation ? "Close conversation" : "Open conversation"}</button></div>{showConversation && <div className="conversation-review">{attempt.messages.map((message) => <article className={message.role} key={message.id}><strong>{message.role === "assistant" ? "Tutor" : student.display_name}</strong><p>{message.content}</p>{message.sources?.length > 0 && <small>Sources: {message.sources.map((source) => source.filename).join(", ")}</small>}</article>)}</div>}</section>
      <section className="evidence-section final-review"><div className="section-label"><h3>Final submission</h3><Status value={attempt.required_task_status} /></div><strong>{detail.required_task?.title}</strong><p className="submission-prompt">{detail.required_task?.submission_prompt}</p>{attempt.required_task_submission ? <div className="submission-content">{attempt.required_task_submission}</div> : <p className="muted">No final submission yet.</p>}</section>
    </>}
  </section></div>;
}

function SummaryCard({ title, tone, items }) {
  return <article className={`summary-card ${tone}`}><h4>{title}</h4><ul>{items.map((item, index) => <li key={`${tone}-${index}`}>{item}</li>)}</ul></article>;
}

createRoot(document.getElementById("root")).render(<App />);

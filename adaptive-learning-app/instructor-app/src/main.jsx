import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import "./styles.css";
import LessonConfigEditor, { ResourceEditor } from "./LessonConfigEditor";

// Match backend rag.py SUPPORTED_SUFFIXES; MIME types help native file pickers.
const COURSE_DOCUMENT_ACCEPT = ".pdf,.pptx,.ppt,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.ms-powerpoint,text/plain,text/markdown";
const COURSE_DOCUMENT_HELP = "PDF (.pdf), PowerPoint (.pptx, .ppt), text (.txt), or Markdown (.md). Maximum 10 MB.";

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
    flow_version: 2,
    topic: "", topic_introduction: "", approved_material: "", introductory_example: "",
    intended_difficulty: "", prerequisite_knowledge: "", study_resources: [], diagnostic_quiz: [], learning_assets: [], content_approved: false,
    objectives: [blankObjective(1)],
    required_task: { title: "Reflection", description: "Reflect on what you can explain or do now.", submission_prompt: "What can you explain or do now that you couldn’t before?" },
  },
};

function Notice({ children, error = false }) {
  return children ? <div className={error ? "notice error" : "notice"}>{children}</div> : null;
}

function Status({ value }) {
  return <span className={`status ${value || "not-started"}`}>{(value || "not started").replaceAll("_", " ")}</span>;
}

function AssignmentAccessCode({ code }) {
  const [message, setMessage] = useState("");
  const copy = async () => {
    try { await navigator.clipboard.writeText(code); setMessage("Code copied"); }
    catch { setMessage("Select the code above and copy it manually."); }
  };
  return <section className="panel"><h2>Student access code</h2><p>Open the demo link → enter your name → enter this code under Add an assignment.</p><strong style={{fontSize:"24px",letterSpacing:".15em",userSelect:"all"}}>{code}</strong><button type="button" className="secondary" onClick={copy} style={{marginLeft:"16px"}}>Copy access code</button>{message && <p role="status">{message}</p>}</section>;
}

function App() {
  const [assignments, setAssignments] = useState(null);
  const [students, setStudents] = useState([]);
  const [selected, setSelected] = useState(() => new URLSearchParams(window.location.search).get("assignment"));
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
          <AssignmentDetail id={selected} onBack={() => { setSelected(null); load(); }} onRevision={setSelected} />
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
              {item.access_code && <p><strong>Student access code: {item.access_code}</strong></p>}
              <div className="metrics"><span><strong>{item.recipient_count}</strong> students</span><span><strong>{item.completed_count}</strong> complete</span></div>
            </button>
          ))}
        </div>
      )}
    </>
  );
}

function AssignmentForm(props) {
  return <QuickAssignmentForm {...props} />;
}

export function QuickAssignmentForm({ students, onCancel, onSaved }) {
  const documentInput = useRef(null);
  const [file, setFile] = useState(null);
  const [material, setMaterial] = useState("");
  const [working, setWorking] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState("");
  const [stage, setStage] = useState("");
  const [sourceMode, setSourceMode] = useState("file");
  const [sourceUrl, setSourceUrl] = useState("");
  const removeDocument = () => {
    setFile(null);
    setMaterial("");
    setError("");
    setStage("");
    if (documentInput.current) documentInput.current.value = "";
  };
  const selectDocument = async event => {
    const selected = event.target.files[0];
    if (!selected) return;
    setError(""); setFile(null); setMaterial(""); setExtracting(true);
    try {
      const upload = new FormData(); upload.append("file", selected);
      const result = await api("/instructor/documents/preview", { method: "POST", body: upload, timeoutMs: 45000 });
      setFile(selected); setMaterial(result.text);
    } catch (e) { setError(e.message); }
    finally { setExtracting(false); }
  };
  const review = async event => {
    event.preventDefault(); setWorking(true); setError("");
    try {
      setStage("Preparing your lesson for review…");
      const preview = sourceMode === "url" ? await api("/instructor/documents/url-preview", { method: "POST", timeoutMs: 120000, body: JSON.stringify({ url: sourceUrl.trim() }) }) : { text: material, filename: file.name };
      const plan = await api("/instructor/document-draft", { method: "POST", timeoutMs: 600000, body: JSON.stringify({ material: preview.text, filename: preview.filename }) });
      const assignment = await api("/instructor/assignments", { method: "POST", body: JSON.stringify({ title: plan.title, instructions: "Study the readings, complete the diagnostic quiz, reason through examples, and reflect on your learning.", learning_plan: plan, student_ids: students.map(student => student.id) }) });
      setStage("Indexing your document…");
      if (sourceMode === "url") {
        await api(`/instructor/assignments/${assignment.id}/documents/url`, { method: "POST", timeoutMs: 120000, body: JSON.stringify({ url: sourceUrl.trim() }) });
      } else {
        const upload = new FormData(); upload.append("file", file);
        await api(`/instructor/assignments/${assignment.id}/documents`, { method: "POST", body: upload });
      }
      onSaved(assignment);
    } catch (e) { setError(e.message); }
    finally { setWorking(false); setStage(""); }
  };
  return <form className="quick-editor" onSubmit={review}>
    <button type="button" className="back" onClick={onCancel}>← Assignments</button>
    <section className="quick-hero"><p className="eyebrow">Create a lesson</p><h1>Start with a document or URL.</h1><p>We prepare the topic, objectives, study links, quiz, examples, and reflection. Edit and review everything before publishing.</p></section>
    <Notice error>{error}</Notice>
    <section className="panel quick-panel">
      <div className="learning-choices"><button type="button" className="secondary" aria-pressed={sourceMode === "file"} disabled={working || extracting} onClick={() => setSourceMode("file")}>Upload document</button><button type="button" className="secondary" aria-pressed={sourceMode === "url"} disabled={working || extracting} onClick={() => setSourceMode("url")}>Use a URL</button></div>
      {sourceMode === "file" ? <>
      <label className="file-pick">Course document<input ref={documentInput} type="file" accept={COURSE_DOCUMENT_ACCEPT} onChange={selectDocument} disabled={working || extracting} /><div>{extracting ? "Reading document…" : file ? `▤ ${file.name} · ready` : "＋ Choose a course document"}</div></label>
      {file && <button type="button" onClick={removeDocument} disabled={working || extracting}>Remove document</button>}
      <p className="muted">{COURSE_DOCUMENT_HELP}</p>
      </> : <><label>Course source URL<input type="url" required value={sourceUrl} disabled={working} onChange={event => setSourceUrl(event.target.value)} placeholder="https://university.edu/article" /></label><p className="muted">Use a public article or PDF. We'll read and index it as your lesson source.</p></>}
      <button className="primary launch" disabled={working || extracting || (sourceMode === "file" ? !file || material.trim().length < 30 : !sourceUrl.trim())}>{working ? stage : "Review"}</button>
    </section>
  </form>;
}

function AdvancedAssignmentForm({ students, onCancel, onSaved, initial }) {
  const [draft, setDraft] = useState(() => initial ? { title: initial.title, instructions: initial.instructions, student_ids: initial.students.map(student => student.id), learning_plan: { ...initial.learning_plan, flow_version: 2 } } : structuredClone(initialDraft));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const plan = draft.learning_plan;
  const updatePlan = (patch) => setDraft({ ...draft, learning_plan: { ...plan, ...patch, content_approved: Object.keys(patch).length === 1 && "content_approved" in patch ? patch.content_approved : false } });
  const updateObjective = (index, patch) => {
    const previousId = plan.objectives[index].id;
    updatePlan({ objectives: plan.objectives.map((item, i) => i === index ? { ...item, ...patch } : item),
      ...(patch.id && patch.id !== previousId ? {
        diagnostic_quiz: plan.diagnostic_quiz.map(question => question.objective_id === previousId ? { ...question, objective_id: patch.id } : question),
        learning_assets: plan.learning_assets.map(asset => asset.objective_id === previousId ? { ...asset, objective_id: patch.id } : asset),
      } : {}) });
  };
  const save = async (event) => {
    event.preventDefault(); setSaving(true); setError("");
    try { onSaved(await api(initial ? `/instructor/assignments/${initial.id}` : "/instructor/assignments", { method: initial ? "PUT" : "POST", body: JSON.stringify(draft) })); }
    catch (e) { setError(e.message); setSaving(false); }
  };
  return (
    <form className="editor" onSubmit={save}>
      <div className="editor-head"><div><button type="button" className="back" onClick={onCancel}>← Lesson review</button><h1>{initial ? "Edit lesson" : "New adaptive assignment"}</h1><p>Edit the content, concepts, quiz, and practice. Save your changes, then review before publishing.</p></div><button className="primary" disabled={saving}>{saving ? "Saving…" : "Save draft"}</button></div>
      <Notice error>{error}</Notice>
      <section className="panel"><p className="step">01 · Assignment</p><div className="field-grid"><label>Assignment title<input required value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} placeholder="Requirements engineering practice" /></label><label>Learning-plan title<input required value={plan.title} onChange={(e) => updatePlan({ title: e.target.value })} placeholder="Requirements engineering" /></label></div><label>Student instructions<textarea required value={draft.instructions} onChange={(e) => setDraft({ ...draft, instructions: e.target.value })} /></label><label>Course context<textarea value={plan.course_context} onChange={(e) => updatePlan({ course_context: e.target.value })} /></label></section>
      <section className="panel"><div className="panel-title"><div><p className="step">02 · Objectives</p><h2>Evidence students must show</h2></div><button type="button" className="secondary" onClick={() => updatePlan({ objectives: [...plan.objectives, blankObjective(plan.objectives.length + 1)] })}>Add objective</button></div>
        {plan.objectives.map((objective, index) => <ObjectiveEditor key={index} objective={objective} index={index} update={(patch) => updateObjective(index, patch)} remove={() => updatePlan({ objectives: plan.objectives.filter((_, i) => i !== index) })} canRemove={plan.objectives.length > 1} />)}
      </section>
      <LessonConfigEditor plan={plan} update={updatePlan} />
      <section className="panel"><p className="step">03 · Required task</p><div className="field-grid"><label>Task title<input required value={plan.required_task.title} onChange={(e) => updatePlan({ required_task: { ...plan.required_task, title: e.target.value } })} /></label><label>Submission prompt<input required value={plan.required_task.submission_prompt} onChange={(e) => updatePlan({ required_task: { ...plan.required_task, submission_prompt: e.target.value } })} /></label></div><label>Description<textarea required value={plan.required_task.description} onChange={(e) => updatePlan({ required_task: { ...plan.required_task, description: e.target.value } })} /></label></section>
      <section className="panel"><p className="step">04 · Students</p><div className="student-picks">{students.map((student) => <label className="check" key={student.id}><input type="checkbox" checked={draft.student_ids.includes(student.id)} onChange={(e) => setDraft({ ...draft, student_ids: e.target.checked ? [...draft.student_ids, student.id] : draft.student_ids.filter((id) => id !== student.id) })} /><span><strong>{student.display_name}</strong><small>{student.email}</small></span></label>)}</div></section>
    </form>
  );
}

function ObjectiveEditor({ objective, index, update, remove, canRemove }) {
  return <div className="objective"><div className="objective-number">{String(index + 1).padStart(2, "0")}</div><div className="objective-fields"><div className="field-grid"><label>Objective ID<input required value={objective.id} onChange={(e) => update({ id: e.target.value })} /></label><label>Short title<input required value={objective.title} onChange={(e) => update({ title: e.target.value })} /></label></div><label>Description<textarea required value={objective.description} onChange={(e) => update({ description: e.target.value })} /></label><label>Success criteria<textarea required value={objective.success_criteria.join("\n")} onChange={(e) => update({ success_criteria: e.target.value.split("\n").filter(Boolean) })} placeholder="One criterion per line" /></label><label>Diagnostic prompt<textarea required value={objective.diagnostic_prompt} onChange={(e) => update({ diagnostic_prompt: e.target.value })} /></label>{canRemove && <button type="button" className="danger-link" onClick={remove}>Remove objective</button>}</div></div>;
}

function AssignmentDetail({ id, onBack, onRevision }) {
  const [item, setItem] = useState(null); const [progress, setProgress] = useState([]); const [error, setError] = useState(""); const [uploading, setUploading] = useState(false); const [studentDetail, setStudentDetail] = useState(null); const [studentLoading, setStudentLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const load = async () => { try { setError(""); const [detail, rows] = await Promise.all([api(`/instructor/assignments/${id}`), api(`/instructor/assignments/${id}/progress`)]); setItem(detail); setProgress(rows); } catch (e) { setError(e.message); } };
  useEffect(() => { load(); }, [id]);
  const upload = async (event) => { const file = event.target.files[0]; if (!file) return; setUploading(true); const body = new FormData(); body.append("file", file); try { await api(`/instructor/assignments/${id}/documents`, { method: "POST", body }); await load(); } catch (e) { setError(e.message); } finally { setUploading(false); event.target.value = ""; } };
  const publish = async () => { try { await api(`/instructor/assignments/${id}/publish`, { method: "POST" }); load(); } catch (e) { setError(e.message); } };
  const [copying, setCopying] = useState(false);
  const revise = async () => { setCopying(true); setError(""); try { const copy = await api(`/instructor/assignments/${id}/editable-copy`, { method: "POST" }); onRevision(copy.id); } catch (e) { setError(e.message); } finally { setCopying(false); } };
  const openStudent = async (studentId) => { setStudentLoading(true); setError(""); try { setStudentDetail(await api(`/instructor/assignments/${id}/students/${studentId}`)); } catch (e) { setError(e.message); } finally { setStudentLoading(false); } };
  if (!item) return <><button className="back" onClick={onBack}>← Assignments</button><Notice error>{error}</Notice><p>Loading assignment…</p></>;
  if (item.status === "draft") return <DocumentLessonReview item={item} onBack={onBack} onPublished={load} />;
  if (editing && item) return <AdvancedAssignmentForm initial={item} students={item.students} onCancel={() => setEditing(false)} onSaved={() => { setEditing(false); load(); }} />;
  return <><button className="back" onClick={onBack}>← Assignments</button><div className="detail-title"><div><Status value={item.status} /><h1>{item.title}</h1><p>{item.instructions}</p></div>{item.status === "draft" && <div className="learning-choices"><button className="secondary" onClick={() => setEditing(true)}>Review & edit lesson</button><button className="primary" disabled={!!item.configuration_issues?.length} onClick={publish}>Publish approved lesson</button></div>}</div><Notice error>{error}</Notice>
    {item.status === "published" && <section className="panel"><h2>Revise this lesson</h2><p>Create a draft to edit the content, concepts, and quiz. Existing students keep their current lesson and results; publishing the copy creates a new access code.</p><button type="button" className="secondary" disabled={copying} onClick={revise}>{copying ? "Creating draft…" : "Create editable copy"}</button></section>}
    {item.access_code && <AssignmentAccessCode code={item.access_code} />}
    <ClassLearningAnalytics progress={progress} onOpen={openStudent} onRefresh={load} disabled={studentLoading} />
    {item.configuration_issues?.length > 0 && <section className="panel config-issues"><h2>Lesson setup needs attention</h2><ul>{item.configuration_issues.map(issue => <li key={issue}>{issue}</li>)}</ul></section>}<div className="detail-grid"><section className="panel"><p className="step">Learning plan</p><h2>{item.learning_plan.title}</h2><p>{item.learning_plan.course_context}</p><div className="objective-list">{item.learning_plan.objectives.map((objective, index) => <div key={objective.id}><span>{index + 1}</span><div><strong>{objective.title}</strong><p>{objective.description}</p></div></div>)}</div>{item.learning_plan.study_resources?.length > 0 && <div className="published-resources"><p className="step">Automatically published resources</p>{item.learning_plan.study_resources.map((resource) => <a href={resource.url} target="_blank" rel="noreferrer" key={resource.url}><span>↗</span><div><strong>{resource.title}</strong><small>{resource.provider}</small></div></a>)}<p>{item.learning_plan.diagnostic_quiz?.length || 0} diagnostic questions · foundational, standard, and accelerated paths</p></div>}</section>
      <section className="panel"><p className="step">Course knowledge</p><h2>RAG documents</h2><p>PDF, PowerPoint, Markdown, and text files are chunked and embedded for source-grounded tutoring.</p>{item.status === "draft" && <label className="upload"><input type="file" accept={COURSE_DOCUMENT_ACCEPT} onChange={upload} disabled={uploading} />{uploading ? "Indexing document…" : "Upload course document"}</label>}<div className="document-list">{item.documents.length ? item.documents.map((doc) => <div key={doc.id}><span>▤</span><div><strong>{doc.filename}</strong><small>{doc.chunk_count} indexed chunks</small></div></div>) : <p className="muted">No documents yet. The tutor can still use the learning plan.</p>}</div></section></div>
    <section className="panel progress-panel"><div className="panel-title"><div><p className="step">Student evidence</p><h2>Progress</h2></div><span>{progress.filter((row) => row.status === "completed").length} of {progress.length} complete</span></div><p className="row-hint">Select a student to inspect their quiz, responses, tutor feedback, and final submission.</p><div className="progress-table">{progress.map((row) => <button type="button" className="progress-row" key={row.student_id} onClick={() => openStudent(row.student_id)} disabled={studentLoading}><div><strong>{row.display_name}</strong><small>{row.email}</small></div><Status value={row.status} /><span className="phase-label">{row.phase?.replaceAll("_", " ") || "not started"}</span><span className="quiz-result">{row.quiz_score === null || row.quiz_score === undefined ? "Quiz —" : `Quiz ${row.quiz_score}/5`}</span><strong className="path-label">{row.learning_path || "—"}</strong><div className="mini-objectives">{row.objective_progress.length ? row.objective_progress.map((objective) => <span className={objective.status} title={`${objective.title}: ${objective.status}`} key={objective.objective_id} />) : <span className="muted">Not started</span>}</div><span className="row-arrow">View →</span></button>)}</div></section>
    {studentDetail && <StudentEvidenceDetail detail={studentDetail} close={() => setStudentDetail(null)} />}
  </>;
}

export function DocumentLessonReview({ item, onBack, onPublished }) {
  const [draft, setDraft] = useState(item);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [resourceUrl, setResourceUrl] = useState("");
  const [editing, setEditing] = useState(false);
  const addResource = async (event, file = null) => {
    event.preventDefault();
    setWorking(true); setError("");
    try {
      if (file) {
        const body = new FormData(); body.append("file", file);
        await api(`/instructor/assignments/${draft.id}/documents`, { method: "POST", body });
      } else {
        await api(`/instructor/assignments/${draft.id}/documents/url`, { method: "POST", body: JSON.stringify({ url: resourceUrl }) });
      }
      setDraft(await api(`/instructor/assignments/${draft.id}`));
      if (!file) setResourceUrl("");
    } catch (e) { setError(e.message); }
    finally { setWorking(false); }
  };
  const plan = draft.learning_plan;
  const issues = (draft.configuration_issues || []).filter(issue => !issue.startsWith("Review and approve"));
  const ready = issues.length === 0;
  const review = async () => {
    setWorking(true); setError("");
    try { setDraft(await api(`/instructor/assignments/${draft.id}/prepare-review`, { method: "POST", timeoutMs: 600000 })); }
    catch (e) { setError(e.message); }
    finally { setWorking(false); }
  };
  const publish = async () => {
    setWorking(true); setError("");
    try {
      await api(`/instructor/assignments/${draft.id}`, { method: "PUT", body: JSON.stringify({ title: draft.title, instructions: draft.instructions, student_ids: draft.students.map(student => student.id), learning_plan: { ...plan, content_approved: true } }) });
      await api(`/instructor/assignments/${draft.id}/publish`, { method: "POST" });
      onPublished();
    } catch (e) { setError(e.message); }
    finally { setWorking(false); }
  };
  if (editing) return <AdvancedAssignmentForm initial={draft} students={draft.students} onCancel={() => setEditing(false)} onSaved={saved => { setDraft(saved); setEditing(false); }} />;
  return <>
    <button className="back" onClick={onBack}>← Assignments</button>
    <div className="detail-title"><div><Status value="draft" /><h1>{draft.title}</h1><p>{ready ? "Review the prepared lesson. Publish when you are happy with it." : "Your document is ingested. Review prepares the complete lesson automatically."}</p></div></div>
    <Notice error>{error}</Notice>
    <button type="button" className="secondary" disabled={working} onClick={() => setEditing(true)}>Edit content, concepts & quiz</button>
    <section className="panel"><h2>Ingested documents</h2><div className="document-list">{draft.documents.map(doc => <div key={doc.id}><span>▤</span><div><strong>{doc.filename}</strong><small>{doc.chunk_count} indexed chunks</small></div></div>)}</div>
      <label className="upload">Add course document (PDF, PPTX/PPT, Markdown, or text)
        <input type="file" accept={COURSE_DOCUMENT_ACCEPT} disabled={working} onChange={event => {
          const file = event.target.files[0];
          if (file) addResource(event, file);
          event.target.value = "";
        }} />
      </label>
      <p className="muted">{COURSE_DOCUMENT_HELP}</p>
      <form onSubmit={addResource}>
        <label>Article or PDF URL<input type="url" required value={resourceUrl} disabled={working} onChange={event => setResourceUrl(event.target.value)} placeholder="https://university.edu/article" /></label>
        <button className="secondary" disabled={working || !resourceUrl.trim()}>{working ? "Processing…" : "Add URL resource"}</button>
      </form>
    </section>
    {!ready ? <section className="panel"><p>We will prepare the topic, objectives, credible readings, five quiz questions, examples, practice activities, and reflection from your document.</p><button className="primary launch" disabled={working} onClick={review}>{working ? "Preparing your lesson for review…" : "Review"}</button></section> : <>
      <section className="panel"><p className="step">Topic</p><h2>{plan.topic}</h2><p>{plan.topic_introduction}</p><p>{plan.introductory_example}</p><small>{plan.intended_difficulty} · Prerequisites: {plan.prerequisite_knowledge}</small><h3>Learning objectives</h3>{plan.objectives.map(objective => <div key={objective.id}><h4>{objective.title}</h4><p>{objective.description}</p><ul>{objective.success_criteria.map((criterion, i) => <li key={i}>{criterion}</li>)}</ul></div>)}</section>
      <section className="panel"><h2>Study readings</h2>{plan.study_resources.map(resource => <article key={resource.url}><h3><a href={resource.url} target="_blank" rel="noreferrer">{resource.title}</a></h3><p>{resource.provider} · {resource.description}</p><p>{resource.focus}</p></article>)}</section>
      <section className="panel"><h2>Diagnostic quiz</h2>{plan.diagnostic_quiz.map((question, i) => <article className="config-item" key={question.id}><h3>{i + 1}. {question.question}</h3><small>{question.difficulty} · {question.concept}</small><ol type="A">{question.options.map((option, j) => <li key={j}>{option}{question.correct_index === j ? " ✓ Correct" : ""}</li>)}</ol><p>{question.explanation}</p><p>Hint: {question.hint}</p><details><summary>Assessment criteria</summary>{question.reasoning_rubric.map((criterion, j) => <p key={j}>{criterion.description}</p>)}</details></article>)}</section>
      <section className="panel"><h2>Examples and adaptive practice</h2>{plan.learning_assets.map(asset => <article className="config-item" key={asset.objective_id}><h3>{plan.objectives.find(objective => objective.id === asset.objective_id)?.title}</h3><p>{asset.explanation}</p><h4>Worked example</h4><p>{asset.worked_example}</p>{asset.analogy && <><h4>Analogy</h4><p>{asset.analogy}</p></>}<h4>Counterexample</h4><p>{asset.counterexample}</p>{["foundational", "standard", "accelerated"].map(level => <details key={level}><summary>{level} practice</summary>{asset[level].map((activity, i) => <div key={i}><p>{activity.prompt}</p><p>Hint: {activity.hint}</p>{activity.rubric.map((criterion, j) => <p key={j}>{criterion.description}</p>)}</div>)}</details>)}</article>)}</section>
      <section className="panel"><h2>Final reflection</h2><h3>{plan.required_task.title}</h3><p>{plan.required_task.description}</p><p>{plan.required_task.submission_prompt}</p></section>
      <section className="panel"><p>Publishing approves this lesson and makes it available to {draft.students.length} students.</p><button className="primary launch" disabled={working || !draft.students.length} onClick={publish}>{working ? "Publishing…" : "Publish"}</button></section>
    </>}
  </>;
}

const conceptStatusLabels = { demonstrated: "Demonstrated", developing: "Developing", needs_support: "Needs support", not_assessed: "Not yet assessed" };

export function ClassLearningAnalytics({ progress, onOpen, onRefresh, disabled }) {
  const [filter, setFilter] = useState("all");
  const hasGap = row => row.concept_analytics?.some(concept => concept.status === "needs_support");
  const filtered = progress.filter(row => filter === "all" || (filter === "needs_support" ? hasGap(row) : filter === "not_started" ? !row.attempt_id : row.concept_analytics?.some(concept => concept.status === "developing")));
  const concepts = new Map();
  for (const row of progress) for (const concept of row.concept_analytics || []) {
    const key = `${concept.objective_id}:${concept.concept}`;
    if (!concepts.has(key)) concepts.set(key, { concept: concept.concept, objective_title: concept.objective_title, demonstrated: 0, developing: 0, needs_support: 0, not_assessed: 0 });
    concepts.get(key)[concept.status] += 1;
  }
  const ranked = [...concepts.values()].sort((a, b) => b.needs_support - a.needs_support || b.developing - a.developing);
  return <section className="panel learning-analytics"><div className="panel-title"><div><p className="step">Learning analytics</p><h2>What students understand and where to help</h2></div><span>{progress.length} students</span></div>
    {onRefresh && <button type="button" className="secondary" onClick={onRefresh} disabled={disabled}>Refresh analytics</button>}
    <p>Demonstrated means two distinct independent checks. Correct quiz selections show a starting point; missing evidence does not mean a student is wrong.</p>
    <div className="analytics-metrics"><div><strong>{progress.filter(row => row.attempt_id).length}</strong><span>Started</span></div><div><strong>{progress.filter(hasGap).length}</strong><span>Need support</span></div><div><strong>{progress.filter(row => row.concept_analytics?.length && row.concept_analytics.every(concept => concept.status === "demonstrated")).length}</strong><span>All concepts demonstrated</span></div><div><strong>{progress.filter(row => !row.attempt_id).length}</strong><span>Not started</span></div></div>
    {ranked.length > 0 && <div className="analytics-table-scroll"><table className="analytics-table"><caption>Concept coverage · student counts</caption><thead><tr><th scope="col">Concept</th><th scope="col">Demonstrated</th><th scope="col">Developing</th><th scope="col">Needs support</th><th scope="col">Not assessed</th></tr></thead><tbody>{ranked.map(concept => <tr key={`${concept.objective_title}:${concept.concept}`}><th scope="row">{concept.concept}<small>{concept.objective_title}</small></th><td>{concept.demonstrated}</td><td>{concept.developing}</td><td>{concept.needs_support}</td><td>{concept.not_assessed}</td></tr>)}</tbody></table></div>}
    <label className="analytics-filter">Show students<select value={filter} onChange={event => setFilter(event.target.value)}><option value="all">All students</option><option value="needs_support">Need support</option><option value="developing">Developing understanding</option><option value="not_started">Not started</option></select></label>
    <div className="analytics-students">{filtered.map(row => <button type="button" className="analytics-student" key={row.student_id} disabled={disabled} onClick={() => onOpen(row.student_id)}><strong>{row.display_name}</strong><span>{row.concept_analytics?.filter(concept => concept.status === "demonstrated").length || 0}/{row.concept_analytics?.length || 0} concepts demonstrated</span><span>{hasGap(row) ? `Needs support: ${row.concept_analytics.filter(concept => concept.status === "needs_support").map(concept => concept.concept).join(", ")}` : row.attempt_id ? "Open evidence and next steps" : "Not started · no evidence yet"}</span><b>View →</b></button>)}</div>{!filtered.length && <p>No students match this filter.</p>}
  </section>;
}

export function StudentConceptAnalytics({ concepts, reflections = [] }) {
  return <><section className="evidence-section"><h3>Understanding by concept</h3><p>Current practice evidence updates the picture; earlier quiz mistakes remain visible as history.</p><div className="concept-evidence">{concepts.map(concept => <article key={`${concept.objective_id}:${concept.concept}`}><div><h4>{concept.concept}</h4><span className={`concept-status ${concept.status}`}>{conceptStatusLabels[concept.status]}</span></div><p>{concept.independent_checks}/2 independent checks · {concept.assisted_responses} responses with support</p><p><strong>Next step:</strong> {concept.next_action}</p>{concept.grader_issue && <p className="notice">Assessment unavailable: {concept.grader_issue} This is not a student error.</p>}<details><summary>View supporting evidence</summary><p>Diagnostic: {concept.diagnostic_total ? `${concept.diagnostic_correct}/${concept.diagnostic_total} correct` : "Not assessed"}{concept.confident_errors > 0 ? ` · ${concept.confident_errors} confident incorrect answers` : ""}</p>{concept.earlier_misconceptions?.length > 0 && <p>Earlier diagnostic misconceptions: {concept.earlier_misconceptions.join("; ")}</p>}{concept.latest_response ? <><blockquote>{concept.latest_response}</blockquote><p>{concept.latest_feedback}</p>{concept.assessment_source && <small>Assessment: {concept.assessment_source === "demo_rubric" ? "Approximate demo phrase check" : "AI rubric assessment"}</small>}</> : <p>No assessed practice response yet.</p>}</details></article>)}</div></section><section className="evidence-section"><h3>Student reflections</h3>{reflections.length ? reflections.map((reflection, index) => <blockquote key={index}>{reflection.content}</blockquote>) : <p>No reflections recorded yet.</p>}</section></>;
}

function StudentEvidenceDetail({ detail, close }) {
  const { student, attempt, evidence, quiz_results: quizResults } = detail;
  const [showConversation, setShowConversation] = useState(false);
  return <div className="evidence-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}><section className="evidence-drawer" role="dialog" aria-modal="true" aria-label={`${student.display_name} evidence`}><div className="drawer-head"><div><p className="step">Student detail</p><h2>{student.display_name}</h2><span>{student.email}</span></div><button type="button" className="close-detail" onClick={close} aria-label="Close student detail">×</button></div>
    {!attempt ? <div className="empty">This student has not started the assignment.</div> : <>
      <div className="detail-metrics"><div><small>Status</small><Status value={attempt.status} /></div><div><small>Diagnostic</small><strong>{attempt.quiz_score ?? "—"}/5</strong></div><div><small>Learning path</small><strong>{attempt.learning_path || "—"}</strong></div><div><small>Objectives</small><strong>{attempt.objective_progress.filter((objective) => objective.status === "demonstrated").length}/{attempt.objective_progress.length}</strong></div></div>
      {detail.summary && <section className="student-summary"><div className="summary-intro"><p className="step">Whole-student summary</p><h3>Evidence of {student.display_name.split(" ")[0]}’s understanding</h3><p>{detail.summary.overview}</p></div><div className="summary-grid"><SummaryCard title="Demonstrated understanding" tone="strength" items={detail.summary.strengths} /><SummaryCard title="Needs support" tone="weakness" items={detail.summary.weaknesses} /><SummaryCard title="Recommended next steps" tone="improvement" items={detail.summary.improvements} /></div></section>}
      {detail.concept_analytics && <StudentConceptAnalytics concepts={detail.concept_analytics} reflections={attempt.learning_state?.reflections || []} />}
      {quizResults.length > 0 && <section className="evidence-section"><div className="section-label"><h3>Diagnostic quiz</h3><span>{attempt.quiz_score}/5 correct</span></div><div className="quiz-review">{quizResults.map((result, index) => <article className={result.correct ? "correct" : "incorrect"} key={result.id}><div className="result-mark">{result.correct ? "✓" : "×"}</div><div><strong>{index + 1}. {result.question}</strong><p>Your answer: {result.selected_answer || "No answer"}</p>{!result.correct && <p>Correct answer: {result.correct_answer}</p>}<small>{result.explanation}</small>{result.confidence !== undefined && <p>Confidence: {result.confidence || "not reported"} · Assistance: {result.assistance_used ? "used" : "none"}</p>}{result.student_explanation && <p>Student reasoning: {result.student_explanation}</p>}{result.reasoning && <p>Reasoning: {result.reasoning.category.replaceAll("_", " ")} · {result.reasoning.feedback}</p>}</div></article>)}</div></section>}
      <section className="evidence-section"><div className="section-label"><h3>Objective evidence</h3><span>{evidence.length} responses assessed</span></div>{evidence.length ? <div className="evidence-list">{evidence.map((entry) => <article key={entry.id}><div><strong>{entry.objective_title}</strong><Status value={entry.demonstrated ? "completed" : "in_progress"} /></div><blockquote>{entry.response}</blockquote><p>{entry.rationale}</p><small>Score {Math.round(entry.score * 100)}%</small></article>)}</div> : <p className="muted">No free-response evidence yet.</p>}</section>
      <section className="evidence-section conversation-section"><div className="section-label"><div><h3>Learning conversation</h3><span>{attempt.messages.length} messages · hidden by default</span></div><button type="button" className="secondary conversation-toggle" onClick={() => setShowConversation(!showConversation)}>{showConversation ? "Close conversation" : "Open conversation"}</button></div>{showConversation && <div className="conversation-review">{attempt.messages.map((message) => <article className={message.role} key={message.id}><strong>{message.role === "assistant" ? "Tutor" : student.display_name}</strong><p>{message.content}</p>{message.sources?.length > 0 && <small>Sources: {message.sources.map((source) => source.filename).join(", ")}</small>}</article>)}</div>}</section>
      {!detail.concept_analytics && <section className="evidence-section final-review"><div className="section-label"><h3>Final submission</h3><Status value={attempt.required_task_status} /></div><strong>{detail.required_task?.title}</strong><p className="submission-prompt">{detail.required_task?.submission_prompt}</p>{attempt.required_task_submission ? <div className="submission-content">{attempt.required_task_submission}</div> : <p className="muted">No final submission yet.</p>}</section>}
    </>}
  </section></div>;
}

function SummaryCard({ title, tone, items }) {
  return <article className={`summary-card ${tone}`}><h4>{title}</h4><ul>{items.map((item, index) => <li key={`${tone}-${index}`}>{item}</li>)}</ul></article>;
}

const root = document.getElementById("root");
if (root) createRoot(root).render(<App />);

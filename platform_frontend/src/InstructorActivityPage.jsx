import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, cachedAssignmentView, pendingAssignmentDetail, date, TOOLS } from "./api";
import { Notice, Badge } from "./ui";
import { loadCourseContext, cachedCourseContext } from "./courseContext";
import CreateActivity from "./CreateActivity";

export function progressMetrics(students = []) {
  const assigned = students.length;
  const completed = students.filter(s => s.progress === "completed").length;
  const inProgress = students.filter(s => s.progress === "in_progress").length;
  // Scores are displayed only when an engine supplies an explicit percentage.
  const grades = students.map(s => s.result?.grade_percent ?? s.result?.score_percent)
    .filter(v => typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 100);
  return {assigned,completed,inProgress,pending:assigned-completed,started:completed+inProgress,
    completionRate:assigned ? Math.round(completed/assigned*100) : 0,
    averageGrade:grades.length ? Math.round(grades.reduce((a,b)=>a+b,0)/grades.length) : null};
}

export default function InstructorActivityPage() {
  const {id} = useParams();
  const [item,setItem] = useState(()=>cachedAssignmentView(`/platform/assignments/${id}`));
  const [context,setContext]=useState(()=>cachedCourseContext());
  const [files,setFiles] = useState([]);
  const [error,setError] = useState("");
  useEffect(()=>{
    let active=true;
    setItem(cachedAssignmentView(`/platform/assignments/${id}`));setFiles([]);setError("");
    if(id === "new") return;
    const load=async()=>{
      const activity=await (pendingAssignmentDetail(id) || api(`/platform/assignments/${id}`));
      const context=await loadCourseContext(activity.course_id);
      if(String(activity.course_id)!==String(context.course_id)) throw Error("Open this activity from its Canvas course.");
      if(!active)return;
      setContext(context);setItem(activity);
      if(activity.status !== "draft" && activity.config.document_ids?.length) {
        const data=await api(`/platform/courses/${activity.course_id}/documents`);
        if(active)setFiles(data.files.filter(f=>(activity.config.document_ids || []).includes(f.document_id)));
      }
    };
    load().catch(e=>active&&setError(e.message));
    return()=>{active=false;};
  },[id]);
  if(id === "new") return <CreateActivity/>;
  if(error) return <><Link className="back" to="/professor">← All assignments</Link><Notice error={error}/></>;
  if(!item) return <p role="status">Opening activity…</p>;
  if(item.status === "draft") return <CreateActivity initialActivity={item} initialContext={context}/>;
  const metrics=progressMetrics(item.students);
  const config=item.config || {};
  const progressValue=value=>item.progress_unavailable ? "Not available" : value;
  return <>
    <div className="activity-detail-nav"><Link className="back" to="/professor">← All assignments</Link></div>
    <div className="page-heading"><div><p className="context">{TOOLS[item.tool]?.name || item.tool}</p><h1>{item.title}</h1></div><Badge value={item.status}/></div>
    <section className="panel" aria-labelledby="activity-progress-title"><div className="activity-glance-heading"><h2 id="activity-progress-title">At a glance</h2><Link className="button compact" to="/professor/analytics">Detailed Insights →</Link></div><div className="activity-kpis">{[
      ["Assigned students",metrics.assigned],["Students started",progressValue(metrics.started)],["Completed",progressValue(metrics.completed)],["Pending",progressValue(metrics.pending)],["Completion rate",progressValue(`${metrics.completionRate}%`)],["Average grade",metrics.averageGrade===null ? "Not available" : `${metrics.averageGrade}%`]
    ].map(([label,value])=><div className="activity-kpi" key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><p className="help">Pending includes students who have not finished. Grades appear when the chatbot supplies percentage scores.</p></section>
    <section className="panel"><h2>Assignment details</h2><dl className="activity-summary"><dt>Assigned chat</dt><dd>{TOOLS[item.tool]?.name || item.tool}</dd><dt>Due date</dt><dd>{date(item.due_at)}</dd><dt>Audience</dt><dd>{metrics.assigned} assigned student{metrics.assigned===1?"":"s"}</dd></dl><h3>Description</h3><p className="activity-description">{item.instructions || "No additional instructions."}</p>
    {(config.scenario || config.prompt) && <><h3>{item.tool==="debate" ? "Debate scenario":"Learning focus"}</h3><p className="activity-description">{config.scenario || config.prompt}</p></>}
    {config.custom_questions?.length>0 && <><h3>Sub-questions</h3><ul>{config.custom_questions.map((q,i)=><li key={i}>{q}</li>)}</ul></>}
    {config.sub_topics?.length>0 && <><h3>Reflection topics</h3><ul>{config.sub_topics.map((q,i)=><li key={i}>{q}</li>)}</ul></>}
    {config.learning_plan?.objectives?.length>0 && <><h3>Learning objectives</h3><ul>{config.learning_plan.objectives.map(o=><li key={o.id}>{o.title}</li>)}</ul></>}
    <h3>Course materials</h3>{files.length ? <ul>{files.map(f=><li key={f.file_id}>{f.filename} · {Math.ceil((f.file_size || 0)/1024)} KB</li>)}</ul> : <p className="help">No selected documents attached.</p>}</section>

  </>;
}

export function AnalyticsPage() {
  return <><div className="page-heading"><div><p className="context">Professor studio</p><h1>Analytics</h1></div></div><section className="panel"><p>Analytics will come here.</p></section></>;
}

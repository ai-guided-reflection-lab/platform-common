const label = key => key.replaceAll("_", " ").replace(/^./, c => c.toUpperCase());

function Content({value}) {
  if (value == null) return null;
  if (Array.isArray(value)) return <ol>{value.map((item,index)=><li key={item?.id || index}><Content value={item}/></li>)}</ol>;
  if (typeof value === "object") return <dl>{Object.entries(value).filter(([key])=>key!=="id").map(([key,item])=><div key={key}><dt><strong>{key==="correct_index" ? "Correct option (1–4)" : label(key)}</strong></dt><dd><Content value={key==="correct_index" ? Number(item)+1 : item}/></dd></div>)}</dl>;
  return <p style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{typeof value === "boolean" ? (value ? "Yes" : "No") : String(value)}</p>;
}

export default function LessonPreview({plan, onChange}) {
  return <section aria-label="Full SDL lesson preview">
    <h3>Complete lesson preview</h3>
    <p>{plan.bounded_flow ? "Student flow: prerequisites → study with examples → five questions with feedback and three attempts → final application → completion." : "Student flow: introduction and study → diagnostic quiz → adaptive practice and feedback → reflection."}</p>
    <p>This instructor preview includes answer keys and assessment rubrics.</p>
    {plan.bounded_flow && <>
      <label>Prerequisite assumptions<textarea disabled={!onChange} value={plan.prerequisite_knowledge || ""} onChange={e=>onChange({...plan,prerequisite_knowledge:e.target.value})}/></label>
      {(plan.prerequisite_resources || []).map((resource,index)=><div key={index}>
        <label>Prerequisite topic {index+1}<input disabled={!onChange} value={resource.title} onChange={e=>onChange({...plan,prerequisite_resources:plan.prerequisite_resources.map((r,i)=>i===index ? {...r,title:e.target.value} : r)})}/></label>
        <label>Prerequisite reading link {index+1}<input type="url" disabled={!onChange} value={resource.url} onChange={e=>onChange({...plan,prerequisite_resources:plan.prerequisite_resources.map((r,i)=>i===index ? {...r,url:e.target.value} : r)})}/></label>
      </div>)}
      <label>Final application question<textarea disabled={!onChange} value={plan.required_task.submission_prompt} onChange={e=>onChange({...plan,required_task:{...plan.required_task,submission_prompt:e.target.value}})}/></label>
      <label>Application assessment rubric<textarea disabled={!onChange} value={(plan.application_rubric || []).map(r=>r.description).join("\n")} onChange={e=>onChange({...plan,application_rubric:e.target.value.split("\n").filter(s=>s.trim()).map(description=>({description,evidence_groups:[]}))})}/><span className="help">One assessment criterion per line.</span></label>
    </>}
    {Object.entries(plan).map(([key,value])=><details key={key} open={["topic_introduction","objectives","diagnostic_quiz"].includes(key)}><summary><strong>{label(key)}</strong>{Array.isArray(value) ? ` (${value.length})` : ""}</summary><Content value={value}/></details>)}
  </section>;
}

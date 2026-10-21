const label = key => key.replaceAll("_", " ").replace(/^./, c => c.toUpperCase());

function Content({value}) {
  if (value == null) return null;
  if (Array.isArray(value)) return <ol>{value.map((item,index)=><li key={item?.id || index}><Content value={item}/></li>)}</ol>;
  if (typeof value === "object") return <dl>{Object.entries(value).filter(([key])=>key!=="id").map(([key,item])=><div key={key}><dt><strong>{key==="correct_index" ? "Correct option (1–4)" : label(key)}</strong></dt><dd><Content value={key==="correct_index" ? Number(item)+1 : item}/></dd></div>)}</dl>;
  return <p style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{typeof value === "boolean" ? (value ? "Yes" : "No") : String(value)}</p>;
}

export default function LessonPreview({plan}) {
  return <section aria-label="Full SDL lesson preview">
    <h3>Complete lesson preview</h3>
    <p>Student flow: introduction and study → diagnostic quiz → adaptive practice and feedback → reflection. The practice path depends on the student’s responses.</p>
    <p>This instructor preview includes answer keys and assessment rubrics.</p>
    {Object.entries(plan).map(([key,value])=><details key={key} open={["topic_introduction","objectives","diagnostic_quiz"].includes(key)}><summary><strong>{label(key)}</strong>{Array.isArray(value) ? ` (${value.length})` : ""}</summary><Content value={value}/></details>)}
  </section>;
}

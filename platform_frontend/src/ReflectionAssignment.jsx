import { useEffect, useRef, useState } from "react";
import Chat from "../../reflections-app/frontend/src/Chat";
import { api } from "./api";

export default function ReflectionAssignment({ assignmentId }) {
  const [assignment, setAssignment] = useState(null);
  const [attempt, setAttempt] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const busy = useRef(false);
  const backUrl = assignmentId
    ? `/platform/student/assignments/${encodeURIComponent(assignmentId)}`
    : "/platform/student";

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setAttempt(null);
    setAssignment(null);
    async function load() {
      if (!assignmentId) throw new Error("Open Reflections from your assignment dashboard.");
      const saved = await api(`/platform/assignments/${encodeURIComponent(assignmentId)}`);
      if (saved.tool !== "reflections") throw new Error("This assignment does not use Reflections.");
      if (!active) return;
      setAssignment(saved);
      // Start is idempotent: existing attempts (including completed ones) resume.
      const result = await api(`/platform/assignments/${encodeURIComponent(assignmentId)}/start`, { method: "POST" });
      if (active) setAttempt(result);
    }
    load().catch((e) => { if (active) setError(e.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [assignmentId, retry]);

  async function perform(path, body) {
    if (busy.current) throw new Error("Please wait for your current response to finish.");
    busy.current = true;
    try {
      const result = await api(`/platform/assignments/${encodeURIComponent(assignmentId)}/${path}`, { method: "POST", body });
      setAttempt(result);
    } finally {
      busy.current = false;
    }
  }

  return (
    <div className="app">
      <nav aria-label="Student navigation">
        <span className="logo">Reflection Chatbot</span>
        <span>Student</span>
        <a href={backUrl}>Back to assignment</a>
      </nav>
      {assignment && <header style={{ padding: "0.75rem 1.5rem" }}>
        <strong>{assignment.title}</strong>
        <p style={{ whiteSpace: "pre-wrap" }}>{assignment.instructions}</p>
      </header>}
      {loading ? <p className="empty" role="status">Opening your reflection…</p>
        : error ? <div className="page">
          <p role="alert">{error}</p>
          <button className="btn btn-primary" onClick={() => setRetry((value) => value + 1)}>Retry</button>
        </div>
        : attempt && <Chat key={assignmentId} assignmentSession={{
          attempt,
          config: assignment.student_config,
          send: (body) => perform("messages", body),
          complete: () => perform("complete"),
          back: () => window.location.assign(backUrl),
        }} />}
    </div>
  );
}

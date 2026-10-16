import React, { useState, useEffect } from "react";
import { api } from "../api";
import { useWorkspace } from "./WorkspaceContext";
import { Icon, Pill, PageHead } from "./ApprovedUI";
export default function ApprovedReflection({ assignmentId }) {
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [done, setDone] = useState(false);
  const [assignment, setAssignment] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { user } = useWorkspace();
  const apply = (attempt) => {
    setMessages(attempt.messages || []);
    setDone(attempt.status === "completed");
  };
  const action = async (path, body) => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api(
        `/platform/assignments/${assignmentId}/${path}`,
        { method: "POST", body },
      );
      apply(result);
      if (path === "messages") setText("");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const detail = await api(`/platform/assignments/${assignmentId}`);
        if (detail.tool !== "reflections")
          throw new Error("Open a Reflections assignment.");
        if (active) setAssignment(detail);
        const result = await api(
          `/platform/assignments/${assignmentId}/start`,
          { method: "POST" },
        );
        if (active) apply(result);
      } catch (e) {
        if (active) setError(e.message);
      }
    }
    load();
    return () => {
      active = false;
    };
  }, [assignmentId]);
  return (
    <>
      <PageHead
        eyebrow="REFLECTIONS"
        title={assignment?.title || "Reflections"}
        description="Slow down, make connections, and notice how your thinking has changed."
      />
      {error && (
        <p className="p-feedback" role="alert">
          {error}
        </p>
      )}
      <div className="p-reflection-grid">
        <aside className="p-panel">
          <span className="p-mini-icon violet">
            <Icon name="reflect" />
          </span>
          <h2>A moment to reflect</h2>
          <p>
            There’s no single right answer. Use a specific experience to make
            your thinking visible.
          </p>
          <ol className="p-reflection-steps">
            <li>Describe your experience</li>
            <li>Explore a tradeoff</li>
            <li>Connect to course ideas</li>
            <li>Look ahead</li>
          </ol>
          <button
            className="secondary"
            onClick={() => action("complete")}
            disabled={done || busy || !assignment}
          >
            {done ? "Reflection complete" : "Finish reflection"}
          </button>
        </aside>
        <section className="p-reflection-chat">
          <div className="p-chat-title">
            <span className="p-mini-icon violet">
              <Icon name="reflect" />
            </span>
            <div>
              <strong>Your reflection space</strong>
              <small>Supportive questions · Your own perspective</small>
            </div>
            <Pill value={done ? "completed" : "in_progress"} />
          </div>
          <div className="p-chat-messages">
            {messages.map((m, i) => (
              <article className={`p-chat-message ${m.role}`} key={i}>
                <span className="p-avatar">
                  {m.role === "assistant"
                    ? "R"
                    : (user.display_name || user.username)
                        .split(/\s+/)
                        .map((n) => n[0])
                        .slice(0, 2)
                        .join("")}
                </span>
                <div>
                  <small>
                    {m.role === "assistant" ? "Reflection guide" : "You"}
                  </small>
                  <p>{m.content}</p>
                </div>
              </article>
            ))}
            {done && (
              <p className="p-feedback" role="status">
                Your reflection is complete.
              </p>
            )}
          </div>
          <form
            className="p-composer"
            onSubmit={(e) => {
              e.preventDefault();
              if (text.trim())
                action("messages", {
                  message: text,
                  request_id: crypto.randomUUID(),
                });
            }}
          >
            <label htmlFor="reflection-text">Your reflection</label>
            <textarea
              id="reflection-text"
              placeholder="Start with a moment that stood out…"
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={done || busy || !assignment}
            />
            <div>
              <small>Take your time. Your perspective matters.</small>
              <button disabled={!text.trim() || done || busy || !assignment}>
                Send reflection <Icon name="arrow" size={16} />
              </button>
            </div>
          </form>
        </section>
      </div>
    </>
  );
}

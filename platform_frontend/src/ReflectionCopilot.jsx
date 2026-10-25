import { useEffect, useId, useRef, useState } from "react";
import { api } from "./api";

export default function ReflectionCopilot({
  courseId,
  selected,
  documents,
  draft,
  onApply,
}) {
  const headingId = useId();
  const helpId = useId();
  const [goal, setGoal] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [applied, setApplied] = useState(false);
  const requestId = useRef(0);
  useEffect(
    () => () => {
      requestId.current += 1;
    },
    [],
  );
  const mode = draft.config.module_type || "topic_based";
  const inputKey = JSON.stringify([
    courseId,
    [...selected].map(String).sort(),
    goal.trim(),
    mode,
  ]);
  const stale = !!result && (result.stale || result.inputKey !== inputKey);
  useEffect(() => {
    // Once invalidated, reverting an input must not silently reactivate a proposal.
    setResult((current) =>
      current && !current.stale && current.inputKey !== inputKey
        ? { ...current, stale: true }
        : current,
    );
  }, [inputKey, result?.inputKey]);
  const indexed = new Set(
    documents
      .filter((file) => file.document_id)
      .map((file) => String(file.document_id)),
  );
  const ready =
    !!courseId &&
    selected.length > 0 &&
    selected.every((id) => indexed.has(String(id))) &&
    goal.trim().length >= 10;
  const prepare = async () => {
    const attempt = ++requestId.current;
    setBusy(true);
    setError("");
    setApplied(false);
    setResult(null);
    try {
      const data = await api("/platform/copilot/reflections/propose", {
        method: "POST",
        // Explicit allowlist: historical CSV and all other config stay in the form.
        body: {
          course_id: courseId,
          goal: goal.trim(),
          document_ids: [...selected],
          current: {
            title: draft.title,
            instructions: draft.instructions,
            module_type: mode,
          },
        },
      });
      if (requestId.current === attempt) setResult({ ...data, inputKey });
    } catch (e) {
      if (requestId.current === attempt) setError(e.message);
    } finally {
      if (requestId.current === attempt) setBusy(false);
    }
  };
  return (
    <section className="activity-copilot" aria-labelledby={headingId}>
      <h3 id={headingId}>Assignment Copilot</h3>
      <p className="help" id={helpId}>
        Prepare a Reflections proposal from your selected materials with the
        local copilot. Review and apply it here, then edit the settings below.
        The copilot cannot save or publish.
      </p>
      <label>
        Reflection goal
        <textarea
          rows={3}
          maxLength={2000}
          value={goal}
          aria-describedby={helpId}
          placeholder="Help students reflect on why requirements must be testable and how they applied that idea."
          onChange={(event) => {
            setGoal(event.target.value);
            setApplied(false);
          }}
        />
      </label>
      {!selected.length && (
        <p className="help">
          Select at least one indexed course document to prepare a proposal.
        </p>
      )}
      <button
        type="button"
        className="secondary"
        disabled={busy || !ready}
        onClick={prepare}
      >
        {busy ? "Preparing proposal…" : "Prepare proposal"}
      </button>
      {busy && (
        <p role="status">
          Reading selected materials and preparing a proposal. You can keep
          editing the form.
        </p>
      )}
      {error && (
        <p className="notice error" role="alert">
          {error} You can continue configuring Reflections manually.
        </p>
      )}
      {result && (
        <div
          className="activity-copilot-preview"
          aria-label="Reflections proposal"
        >
          {!stale && !applied && (
            <p role="status">
              Proposal ready. Review it before applying it to the form.
            </p>
          )}
          {stale && (
            <p role="status" className="notice">
              This proposal is out of date because the goal, materials, or
              reflection type changed. Prepare a new proposal or dismiss this
              one.
            </p>
          )}
          <h4>{result.proposal.title}</h4>
          <p className="activity-copilot-text">
            {result.proposal.instructions}
          </p>
          <p>
            <strong>Format:</strong>{" "}
            {result.proposal.config.module_type === "milestone_based"
              ? "Milestone reflection"
              : "Topic-based conversation"}
          </p>
          {result.proposal.config.module_type === "milestone_based" ? (
            <p className="activity-copilot-text">
              {result.proposal.config.milestone_prompt}
            </p>
          ) : (
            <>
              <p>
                <strong>Learning topics:</strong>{" "}
                {result.proposal.config.required_topics.join(", ")}
              </p>
              <ol>
                {result.proposal.config.sub_topics.map((topic, index) => (
                  <li key={index}>{topic}</li>
                ))}
              </ol>
            </>
          )}
          <p>
            <strong>Depth:</strong> {result.proposal.config.expected_depth}.{" "}
            <strong>Probing:</strong> {result.proposal.config.probing_style}.
            {result.proposal.config.must_include_application &&
              " Includes a practical application."}
          </p>
          {result.proposal.config.custom_notes && (
            <p className="activity-copilot-text">
              <strong>Professor notes:</strong>{" "}
              {result.proposal.config.custom_notes}
            </p>
          )}
          <p className="activity-copilot-text">
            <strong>Why this proposal:</strong> {result.proposal.rationale}
          </p>
          <h4>Evidence from selected materials</h4>
          {result.evidence.map((source, index) => (
            <figure
              className="activity-copilot-evidence"
              key={`${source.document_id}-${index}`}
            >
              <figcaption>{source.title}</figcaption>
              <blockquote>{source.excerpt}</blockquote>
            </figure>
          ))}
          <div className="activity-copilot-actions">
            <button
              type="button"
              disabled={stale || busy || applied}
              onClick={() => {
                onApply(result.proposal);
                setApplied(true);
              }}
            >
              Apply proposal
            </button>
            <button
              type="button"
              className="quiet"
              onClick={() => {
                setResult(null);
                setApplied(false);
              }}
            >
              Dismiss proposal
            </button>
          </div>
        </div>
      )}
      {applied && !stale && (
        <p role="status">
          Proposal applied. Review the editable settings, then save a draft or
          publish when ready.
        </p>
      )}
    </section>
  );
}

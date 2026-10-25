import { useEffect, useId, useRef, useState } from "react";
import { api, TOOLS } from "./api";

const withObjectives = (instructions, objectives) =>
  objectives?.length
    ? `${instructions}\n\nLearning objectives:\n${objectives.map((value) => `- ${value}`).join("\n")}`
    : instructions;

// The apply tool is a local form operation. It never calls a save or engine API.
export function applyAssignmentProposal(
  current,
  proposal,
  selected,
  field,
  existingConfig = {},
) {
  if (field === "title") return { ...current, title: proposal.title };
  if (field === "instructions")
    return { ...current, instructions: proposal.instructions };
  if (field === "objectives")
    return {
      ...current,
      instructions: withObjectives(current.instructions, proposal.objectives),
    };
  const config = {
    ...proposal.config,
    document_ids: [...selected],
    ...(proposal.tool === "reflections"
      ? {
          historical_data:
            (current.tool === "reflections" ? current.config : existingConfig)
              .historical_data || "",
        }
      : {}),
  };
  return {
    ...current,
    ...(field === "config"
      ? {}
      : {
          title: proposal.title,
          instructions: withObjectives(
            proposal.instructions,
            proposal.objectives,
          ),
        }),
    tool: proposal.tool,
    config,
    keyword_preparation: null,
  };
}

export default function AssignmentCopilot({
  courseId,
  selected,
  documents,
  draft,
  onApply,
}) {
  const headingId = useId();
  const [goal, setGoal] = useState("");
  const [revision, setRevision] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [applied, setApplied] = useState(false);
  const [appliedFields, setAppliedFields] = useState([]);
  const sequence = useRef(0);
  useEffect(
    () => () => {
      sequence.current += 1;
    },
    [],
  );
  const supported = [
    "socratic",
    "reflections",
    "self-directed-learning",
    "debate",
  ].includes(draft.tool);
  const inputKey = JSON.stringify([
    courseId,
    [...selected].map(String).sort(),
    goal.trim(),
    draft.tool,
    draft.config.module_type || "topic_based",
    revision.trim(),
  ]);
  const stale =
    !!result && !applied && (result.stale || result.inputKey !== inputKey);
  useEffect(() => {
    setResult((current) =>
      current && !applied && current.inputKey !== inputKey
        ? { ...current, stale: true }
        : current,
    );
  }, [inputKey, applied, result?.inputKey]);
  const indexed = new Set(
    documents
      .filter((file) => file.document_id)
      .map((file) => String(file.document_id)),
  );
  const ready =
    !!courseId &&
    selected.length > 0 &&
    selected.every((id) => indexed.has(String(id))) &&
    goal.trim().length >= 10 &&
    (!draft.tool || supported);
  const prepare = async () => {
    const attempt = ++sequence.current;
    setBusy(true);
    setError("");
    setApplied(false);
    setAppliedFields([]);
    setResult(null);
    try {
      const data = await api("/platform/copilot/propose", {
        method: "POST",
        body: {
          request_id: crypto.randomUUID(),
          course_id: courseId,
          goal: goal.trim(),
          revision: revision.trim(),
          document_ids: [...selected],
          // Never send configuration, milestone CSV, student data or audience.
          current: {
            title: draft.title,
            instructions: draft.instructions,
            tool: supported ? draft.tool : null,
            module_type: draft.config.module_type || "topic_based",
          },
        },
      });
      if (sequence.current === attempt) setResult({ ...data, inputKey });
    } catch (failure) {
      if (sequence.current === attempt) setError(failure.message);
    } finally {
      if (sequence.current === attempt) setBusy(false);
    }
  };
  const apply = (field) => {
    if (field && appliedFields.includes(field)) return;
    onApply(result.proposal, field);
    if (!field) setApplied(true);
    else setAppliedFields((current) => [...current, field]);
  };
  const proposal = result?.proposal;
  return (
    <section className="panel activity-copilot" aria-labelledby={headingId}>
      <h3 id={headingId}>Assignment Copilot</h3>
      <p className="help">
        Describe the learning outcome and select course materials. The local
        copilot recommends an activity when none is selected, or uses your
        selected activity. Review the proposal and apply it to the editable
        form, then use the existing save and publish controls.
      </p>
      <label>
        {draft.tool === "reflections" ? "Reflection goal" : "Learning outcome"}
        <textarea
          rows={3}
          maxLength={2000}
          value={goal}
          placeholder="Help students distinguish processes from threads using the operating-systems materials."
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
      {draft.tool === "aiducate" && (
        <p className="help">
          AIducate authoring will be available after its runtime contract is
          finalized.
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
          {error} You can continue configuring the assignment manually.
        </p>
      )}
      {proposal && (
        <div
          className="activity-copilot-preview"
          aria-label="Assignment proposal"
        >
          {stale && (
            <p role="status">
              This proposal is out of date. Prepare a new proposal or dismiss
              this one.
            </p>
          )}
          {!stale && !applied && (
            <p role="status">
              Proposal ready. Review it before applying it to the form.
            </p>
          )}
          <h4>{proposal.title}</h4>
          <p>
            <strong>Recommended activity:</strong> {TOOLS[proposal.tool]?.name}
          </p>
          <p className="activity-copilot-text">
            <strong>Why this proposal:</strong> {proposal.rationale}
          </p>
          <p className="activity-copilot-text">{proposal.instructions}</p>
          <h4>Learning objectives</h4>
          <ol>
            {proposal.objectives.map((objective, index) => (
              <li key={index}>{objective}</li>
            ))}
          </ol>
          <h4>Proposed configuration</h4>
          <dl className="activity-summary">
            {Object.entries(proposal.config)
              .filter(
                ([key]) =>
                  ![
                    "historical_data",
                    "document_ids",
                    "learning_plan",
                    "learning_objective_id",
                  ].includes(key),
              )
              .map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd className="activity-copilot-text">
                    {Array.isArray(value) ? value.join("; ") : String(value)}
                  </dd>
                </div>
              ))}
          </dl>
          {result.warnings?.map((warning, index) => (
            <p className="notice" key={index}>
              {warning}
            </p>
          ))}
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
              disabled={busy || stale || applied}
              onClick={() => apply()}
            >
              Apply proposal
            </button>
            {[
              ["title", "Apply title"],
              ["instructions", "Apply instructions"],
              ["objectives", "Apply objectives"],
              ["config", "Apply activity and settings"],
            ].map(([field, label]) => (
              <button
                type="button"
                className="secondary"
                key={field}
                disabled={
                  busy || stale || applied || appliedFields.includes(field)
                }
                onClick={() => apply(field)}
              >
                {label}
              </button>
            ))}
            <button
              type="button"
              className="quiet"
              onClick={() => {
                sequence.current += 1;
                setResult(null);
                setApplied(false);
              }}
            >
              Dismiss proposal
            </button>
          </div>
          <label>
            Revision request
            <textarea
              rows={2}
              maxLength={2000}
              value={revision}
              onChange={(event) => {
                setRevision(event.target.value);
                setApplied(false);
              }}
            />
          </label>
          <button
            type="button"
            className="secondary"
            disabled={busy || !ready || !revision.trim()}
            onClick={prepare}
          >
            Revise proposal
          </button>
        </div>
      )}
      {applied && (
        <p role="status">
          Proposal applied. Review the editable settings, then save a draft when
          ready.
        </p>
      )}
    </section>
  );
}

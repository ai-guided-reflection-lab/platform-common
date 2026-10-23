import { useState } from "react";

const label = (key) =>
  ({
    url: "URL",
    correct_index: "Correct answer",
    diagnostic_quiz: "Questions",
    prerequisite_knowledge: "Prerequisite assumptions",
    topic_introduction: "Opening study message",
    introductory_example: "Worked example",
    submission_prompt: "Typed response prompt",
  })[key] || key.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
const hidden = new Set([
  "id",
  "objective_id",
  "flow_version",
  "bounded_flow",
  "material_first",
  "auto_generated",
  "content_approved",
]);

function Field({ name, value, editing, onChange }) {
  if (value == null) return null;
  if (Array.isArray(value))
    return (
      <div className="sdl-review-list">
        {value.map((item, index) => (
          <div className="sdl-review-item" key={item?.id || index}>
            <Field
              name={
                typeof item === "string"
                  ? `${name === "Options" ? "Option" : name} ${name === "Options" ? String.fromCharCode(65 + index) : index + 1}`
                  : `${name} ${index + 1}`
              }
              value={item}
              editing={editing}
              onChange={(next) =>
                onChange(value.map((old, i) => (i === index ? next : old)))
              }
            />
          </div>
        ))}
      </div>
    );
  if (typeof value === "object")
    return (
      <fieldset className="sdl-review-fields">
        <legend className={name === "Question" ? "sr-only" : undefined}>{name === "Question" ? "Question details" : name}</legend>
        {Object.entries(value)
          .filter(([key]) => !hidden.has(key))
          .map(([key, item]) => (
            <Field
              key={key}
              name={label(key)}
              value={item}
              editing={editing}
              onChange={(next) => onChange({ ...value, [key]: next })}
            />
          ))}
      </fieldset>
    );
  if (!editing)
    return (
      <div className="sdl-review-value">
        <strong>{name}</strong>
        <p>
          {name === "Correct answer"
            ? `Option ${String.fromCharCode(65 + Number(value))}`
            : String(value)}
        </p>
      </div>
    );
  if (name === "Correct answer")
    return (
      <label>
        {name}
        <select
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
        >
          {[0, 1, 2, 3].map((i) => (
            <option key={i} value={i}>
              Option {String.fromCharCode(65 + i)}
            </option>
          ))}
        </select>
      </label>
    );
  if (name === "Difficulty")
    return (
      <label>
        {name}
        <select value={value} onChange={(e) => onChange(e.target.value)}>
          {[
            "foundational",
            "understanding",
            "application",
            "analysis",
            "challenge",
          ].map((level) => (
            <option key={level} value={level}>
              {label(level)}
            </option>
          ))}
        </select>
      </label>
    );
  if (typeof value === "number")
    return (
      <label>
        {name}
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      </label>
    );
  if (typeof value === "boolean")
    return (
      <label>
        {name}
        <input
          type="checkbox"
          checked={value}
          onChange={(e) => onChange(e.target.checked)}
        />
      </label>
    );
  return (
    <label>
      {name}
      <textarea
        rows={value.length > 180 ? 5 : 2}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function Resources({ name, items = [], editing, onChange }) {
  return (
    <div className="sdl-review-resources">
      <h4>{name}</h4>
      {items.map((item, index) => (
        <div key={index} className="sdl-review-item">
          <Field
            name={`Reading ${index + 1}`}
            value={{ title: item.title, url: item.url, focus: item.focus || "" }}
            editing={editing}
            onChange={(next) =>
              onChange(items.map((old, i) => (i === index ? {...old, ...next} : old)))
            }
          />
          {editing && (
            <button
              type="button"
              className="quiet"
              onClick={() => onChange(items.filter((_, i) => i !== index))}
            >
              Remove reading {index + 1}
            </button>
          )}
          {!editing && /^https:\/\//i.test(item.url) && (
            <a href={item.url} target="_blank" rel="noopener noreferrer">
              Open reading ↗
            </a>
          )}
        </div>
      ))}
      {editing && items.length < 5 && (
        <button
          type="button"
          className="secondary"
          onClick={() =>
            onChange([
              ...items,
              {
                title: "Additional reading",
                url: "",
                provider: "Instructor resource",
                description: "",
                focus: "",
              },
            ])
          }
        >
          Add reading link
        </button>
      )}
      {!items.length && !editing && (
        <p className="help">
          Use the uploaded course material. No supplemental links added.
        </p>
      )}
    </div>
  );
}

export default function LessonPreview({ plan, onChange, onSave }) {
  const [editing, setEditing] = useState({});
  const [saving, setSaving] = useState(null);
  const [saveError, setSaveError] = useState("");
  const [savedSection, setSavedSection] = useState(null);
  const saveSection = async title => {
    setSaving(title);
    setSaveError("");
    try {
      await onSave?.();
      setEditing(old=>({...old,[title]:false}));
      setSavedSection(title);
    } catch (error) {
      setSaveError(error.message || "Changes could not be saved. Please try again.");
    } finally {
      setSaving(null);
    }
  };
  const update = (key, value) => onChange?.({ ...plan, [key]: value });
  const fields = (keys, enabled) =>
    keys
      .filter((key) => key in plan)
      .map((key) => (
        <Field
          key={key}
          name={label(key)}
          value={plan[key]}
          editing={enabled}
          onChange={(next) => update(key, next)}
        />
      ));
  const prerequisiteMessage =
    plan.prerequisite_message ||
    `Today we are learning ${plan.topic}.\n\nStarting point: ${plan.starting_point}\n\nBy the end: ${plan.ending_point}\n\nPrerequisites: ${plan.prerequisite_knowledge}\n\n${plan.prerequisite_resources?.length ? "Read the prerequisite links below if needed. " : "Review these prerequisite assumptions with your course material or instructor if needed. "}Confirm you are familiar with these prerequisites to continue.`;
  const studyMessage =
    plan.study_message ||
    `Let's study ${plan.topic}.\n\n${plan.topic_introduction}\n\nWorked example: ${plan.introductory_example}\n\nExplore the topic readings below. Ask for examples, or start the quiz when ready.`;
  return (
    <section className="sdl-review" aria-label="Full SDL lesson preview">
      <h3>Review activity</h3>
      <p>
        Review the student messages, readings, quiz, and application task. Use
        each pencil to edit the section before publishing.
      </p>
      {saveError && <p className="notice error" role="alert">{saveError}</p>}
      {[
        [
          "Prerequisites",
          (enabled) => (
            <>
              <Field
                name="Opening prerequisite message"
                value={prerequisiteMessage}
                editing={enabled}
                onChange={(next) => update("prerequisite_message", next)}
              />
              <details>
                <summary>Assumptions and lesson bounds</summary>
                {fields(
                  [
                    "topic",
                    "starting_point",
                    "ending_point",
                    "prerequisite_knowledge",
                  ],
                  enabled,
                )}
              </details>
              <Resources
                name="Prerequisite links"
                items={plan.prerequisite_resources}
                editing={enabled}
                onChange={(next) => update("prerequisite_resources", next)}
              />
            </>
          ),
        ],
        [
          "Study",
          (enabled) => (
            <>
              <Field
                name="Study message"
                value={studyMessage}
                editing={enabled}
                onChange={(next) => update("study_message", next)}
              />
              <Resources
                name="Study links"
                items={plan.study_resources}
                editing={enabled}
                onChange={(next) => update("study_resources", next)}
              />
              <details>
                <summary>Teaching material and learning outcomes</summary>
                {fields(
                  [
                    "title",
                    "course_context",
                    "topic_introduction",
                    "introductory_example",
                    "intended_difficulty",
                    "objectives",
                    "approved_material",
                    "supplemental_reading_note",
                  ],
                  enabled,
                )}
                {(plan.learning_assets || []).map((asset, index) => (
                  <Field
                    key={asset.objective_id}
                    name={`Additional study examples ${index + 1}`}
                    value={Object.fromEntries(
                      [
                        "explanation",
                        "worked_example",
                        "analogy",
                        "counterexample",
                      ].map((key) => [key, asset[key]]),
                    )}
                    editing={enabled}
                    onChange={(next) =>
                      update(
                        "learning_assets",
                        plan.learning_assets.map((old) =>
                          old.objective_id === asset.objective_id
                            ? { ...old, ...next }
                            : old,
                        ),
                      )
                    }
                  />
                ))}
              </details>
            </>
          ),
        ],
        [
          "Quiz",
          (enabled) => (
            <>
              {(plan.diagnostic_quiz || []).map((question, index) => (
                <div className="sdl-review-item" key={question.id}>
                  <h4>Question {index + 1}</h4>
                  <Field
                    name="Question"
                    value={{
                      question: question.question,
                      options: question.options,
                      correct_index: question.correct_index,
                      hint: question.hint,
                      worked_example:
                        question.worked_example ||
                        plan.learning_assets?.find(
                          (asset) =>
                            asset.objective_id === question.objective_id,
                        )?.worked_example ||
                        "",
                      explanation: question.explanation,
                      material_reference: question.material_reference,
                    }}
                    editing={enabled}
                    onChange={(next) =>
                      update(
                        "diagnostic_quiz",
                        plan.diagnostic_quiz.map((old, i) =>
                          i === index ? { ...old, ...next } : old,
                        ),
                      )
                    }
                  />
                  <details>
                    <summary>Additional feedback and assessment</summary>
                    <Field
                      name="Assessment settings"
                      value={Object.fromEntries(
                        Object.entries(question).filter(
                          ([key]) =>
                            ![
                              "question",
                              "options",
                              "correct_index",
                              "hint",
                              "worked_example",
                              "explanation",
                              "material_reference",
                            ].includes(key),
                        ),
                      )}
                      editing={enabled}
                      onChange={(next) =>
                        update(
                          "diagnostic_quiz",
                          plan.diagnostic_quiz.map((old, i) =>
                            i === index ? { ...old, ...next } : old,
                          ),
                        )
                      }
                    />
                  </details>
                </div>
              ))}
            </>
          ),
        ],
        [
          "Application",
          (enabled) => (
            <><p className="help">Students answer in a text box. Ask for a written response; file uploads are not available.</p>{fields(["required_task", "application_rubric"], enabled)}</>
          ),
        ],
      ].map(([title, content]) => (
        <section
          className="sdl-review-section"
          key={title}
          aria-label={`${title} review`}
        >
          <header>
            <h3>{title}</h3>
            {onChange && (
              <button
                type="button"
                className={editing[title] ? "" : "secondary"}
                aria-label={`${editing[title] ? "Save" : "Edit"} ${title}`}
                disabled={saving !== null}
                onClick={() => {
                  if (editing[title]) saveSection(title);
                  else {setSavedSection(null);setEditing(old=>({...old,[title]:true}));}
                }}
              >
                {saving === title ? "Saving…" : editing[title] ? "Save" : "✎ Edit"}
              </button>
            )}
          </header>
          {savedSection === title && <p className="help" role="status">Saved.</p>}
          {content(!!onChange && !!editing[title])}
        </section>
      ))}
    </section>
  );
}

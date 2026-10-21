import { useEffect, useId, useState } from "react";
import { api } from "./api";
import { Notice } from "./ui";
import CourseLearningMaterials from "./CourseLearningMaterials";

export const defaults = {
  socratic: {
    keywords: [],
    optional_keywords: [],
    dismissed_keywords: [],
    document_ids: [],
    prompt: "",
    minimum_messages: 1,
  },
  debate: {
    document_ids: [],
    scenario: "",
    opening_prompt: "",
    minimum_messages: 3,
  },
  reflections: {
    module_type: "topic_based",
    required_topics: [],
    sub_topics: [],
    expected_depth: "surface",
    probing_style: "supportive",
    must_include_application: false,
    custom_notes: "",
    milestone_prompt: "",
    historical_data: "",
  },
  "student-agent": { topic: null, provider: "openai", personality: "confused" },
};

function Lines({ label, value = [], onChange, rows = 4, description }) {
  return (
    <label>
      {label}
      <textarea
        rows={rows}
        value={value.join("\n")}
        onChange={(e) => onChange(e.target.value.split("\n"))}
      />
      <span className="help">{description} {"One item per line."}</span>
    </label>
  );
}

export function SocraticConfig({
  value,
  onChange,
  courseId,
  frozen,
  onPendingKeywordChange,
  keywordPreparation,
  onConfirmKeywords,
  onInvalidateKeywordPreparation,
  onMaterialsChange,
  hideConversation = false,
  hideDocuments = false,
  documents,
  hideMaterials = false,
}) {
  const change = (key, next) => onChange({ ...value, [key]: next });
  return (
    <>
      {!hideConversation && (
        <section
          className="socratic-conversation-settings"
          aria-label="Conversation settings"
        >
        {!hideMaterials && <h3>Conversation settings</h3>}
        <label>
          Opening question or prompt
          <textarea
            rows={4}
            value={value.prompt || ""}
            onChange={(e) => change("prompt", e.target.value)}
            placeholder="What assumptions does this design make?"
          />
        </label>
        <label>
          Messages required before completion
          <input
            type="number"
            min={1}
            max={100}
            value={value.minimum_messages ?? 1}
            onChange={(e) =>
              change("minimum_messages", Number(e.target.value))
            }
          />
        </label>
        <p className="help">
          Students mark the assignment complete after the minimum number of
          messages.
        </p>
        </section>
      )}
      {!hideMaterials &&
        (courseId ? (
          <CourseLearningMaterials
            key={courseId}
            courseId={courseId}
            onChange={onMaterialsChange}
            assignmentConfig={value}
            onAssignmentChange={onChange}
            onPendingKeywordChange={onPendingKeywordChange}
            keywordPreparation={keywordPreparation}
            onConfirmKeywords={onConfirmKeywords}
            onInvalidateKeywordPreparation={onInvalidateKeywordPreparation}
            frozen={frozen}
            embedded
            hideDocuments={hideDocuments}
            documents={documents}
          />
        ) : (
          <p>Choose a course to manage its documents and learning objectives.</p>
        ))}
    </>
  );
}

function ReflectionHelp({ text }) {
  const id = useId();
  return (
    <span className="reflection-help" tabIndex={0} role="img" aria-label={text} aria-describedby={id}>
      ⓘ
      <span id={id} role="tooltip" className="reflection-help-content">{text}</span>
    </span>
  );
}

export function ReflectionConfig({ value, onChange }) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const change = (k, v) => onChange({ ...value, [k]: v });
  return (
    <>
      <Notice error={error} />
      <p className="help">Choose a reflection format, then configure the guidance students will receive.</p>
      <label>
        Reflection type
        <select
          value={value.module_type}
          onChange={(e) => change("module_type", e.target.value)}
        >
          <option value="topic_based">Topic-based conversation</option>
          <option value="milestone_based">Milestone reflection</option>
        </select>
      </label>
      <p className="help">
        <strong>Topic-based conversation:</strong> An AI-guided discussion of course concepts using follow-up questions.
        <br />
        <strong>Milestone reflection:</strong> Students reflect on a challenge and their solution; past responses help inform recommendations.
      </p>
      {value.module_type === "topic_based" ? (
        <>
          <div className="form-columns">
            <Lines
              label="Learning topics"
              description="List the main concepts students should reflect on, such as neural networks."
              value={value.required_topics}
              onChange={(v) => change("required_topics", v)}
            />
            <div>
              <Lines
                label="Sub-topics to explore"
                description="Add specific concepts to discuss in order. Generate a draft from your learning topics, then review it."
                value={value.sub_topics}
                onChange={(v) => change("sub_topics", v)}
              />
              <button
                className="secondary compact"
                type="button"
                disabled={busy || !value.required_topics.some((t) => t.trim())}
                onClick={async () => {
                  setBusy(true);
                  setError("");
                  try {
                    const data = await api("/platform/generate-subtopics", {
                      method: "POST",
                      body: {
                        main_topics: value.required_topics.filter((t) =>
                          t.trim(),
                        ),
                      },
                    });
                    change("sub_topics", data.sub_topics);
                  } catch (e) {
                    setError(e.message);
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                {busy ? "Generating…" : "Generate sub-topics"}
              </button>
            </div>
          </div>
          <div className="form-columns">
            <label>
              Expected depth <ReflectionHelp text="Sets the level of detail the AI asks for. Surface: explain the basics. Applied: connect concepts to real situations. Analytical: compare ideas and critically evaluate them." />
              <select
                aria-label="Expected depth"
                value={value.expected_depth}
                onChange={(e) => change("expected_depth", e.target.value)}
              >
                <option value="surface">Surface</option>
                <option value="applied">Applied</option>
                <option value="analytical">Analytical</option>
              </select>
            </label>
            <label>
              Probing style <ReflectionHelp text="Sets how the AI follows up. Supportive: warm encouragement and gentle guidance. Socratic: probing questions that ask students to explain their reasoning and assumptions." />
              <select
                aria-label="Probing style"
                value={value.probing_style}
                onChange={(e) => change("probing_style", e.target.value)}
              >
                <option value="supportive">Supportive</option>
                <option value="socratic">Socratic</option>
              </select>
            </label>
          </div>
          <p className="help">{({surface: "Surface: explain the basics in a brief summary.", applied: "Applied: connect concepts to real situations.", analytical: "Analytical: compare, contrast, and critically evaluate ideas."})[value.expected_depth]} {value.probing_style === "socratic" ? "Socratic: follow-up questions explore reasoning and assumptions." : "Supportive: warm encouragement and gentle guidance."}</p>
          <label className="check">
            <input
              type="checkbox"
              aria-label="Require a practical application"
              checked={value.must_include_application}
              onChange={(e) =>
                change("must_include_application", e.target.checked)
              }
            />
            Require a practical application <ReflectionHelp text="Instructs the AI to ask at least one question where students apply a concept to a real scenario. For example: How would you use this approach in a class project?" />
          </label>
          <label>
            Professor notes <ReflectionHelp text="These notes are sent to the AI as priority instructions for the conversation. Use them to specify concepts to emphasize or misconceptions to revisit; they are not a private reminder pad." />
            <textarea
              rows={3}
              placeholder="For example: Ask students to explain backpropagation before moving to other topics."
              aria-label="Professor notes"
              value={value.custom_notes}
              onChange={(e) => change("custom_notes", e.target.value)}
            />
          </label>
          <p className="help">These notes guide the AI’s questions and feedback, including concepts to emphasize or revisit.</p>
        </>
      ) : (
        <>
          <label>
            Milestone prompt
            <textarea
              rows={5}
              placeholder="What was your biggest challenge this week, and what solution did you try?"
              value={value.milestone_prompt}
              onChange={(e) => change("milestone_prompt", e.target.value)}
            />
          </label>
          <p className="help">Students see this prompt when they open the reflection. Ask them to describe a challenge and the solution they tried.</p>
          <label>
            Historical responses (CSV)
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={async (e) => {
                const f = e.target.files[0];
                if (!f) return;
                if (f.size > 2_000_000) {
                  setError("Use a CSV smaller than 2 MB.");
                  return;
                }
                change("historical_data", await f.text());
                setError("");
              }}
            />
          </label>
          <p className="help">
            Required columns: name, challenge, solution. Historical responses
            are used for recommendations and are not exposed as assignment
            configuration to students.
          </p>
          {value.historical_data && (
            <p className="notice">
              Historical CSV attached (
              {Math.round(value.historical_data.length / 1024)} KB).
            </p>
          )}
        </>
      )}
    </>
  );
}

const blankTopic = () => ({
  id: `topic_${crypto.randomUUID().slice(0, 8)}`,
  name: "",
  resource: { title: "", url: "" },
  alt_resource: { title: "", url: "" },
  practice_label: "",
  practice_prompt: "",
  practice_stages: [{ label: "", focus: "" }],
  practice_options: [],
  check_questions: [],
  final_example: "",
});
function cleanTopic(topic) {
  const allowed = [
    "id",
    "name",
    "resource",
    "alt_resource",
    "practice_label",
    "practice_prompt",
    "practice_stages",
    "practice_options",
    "check_questions",
    "final_example",
    "number",
  ];
  return Object.fromEntries(
    Object.entries(topic).filter(([k]) => allowed.includes(k)),
  );
}
export function TutorConfig({ value, onChange, frozen }) {
  const [templates, setTemplates] = useState([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [topicName, setTopicName] = useState("");
  useEffect(() => {
    api("/platform/topic-templates")
      .then(setTemplates)
      .catch((e) => setError(e.message));
  }, []);
  const topic = value.topic,
    change = (k, v) => onChange({ ...value, [k]: v });
  const editTopic = (k, v) => change("topic", { ...topic, [k]: v });
  return (
    <>
      <Notice error={error} />
      <div className="form-columns">
        <label>
          Model provider
          <select
            value={value.provider}
            onChange={(e) => change("provider", e.target.value)}
          >
            <option value="openai">OpenAI</option>
            <option value="groq">Groq</option>
          </select>
        </label>
        {!frozen && (
          <label>
            Start from a topic
            <select
              value=""
              onChange={(e) => {
                const t = templates.find((t) => t.id === e.target.value);
                if (t) change("topic", cleanTopic(structuredClone(t)));
              }}
            >
              <option value="">Select a template</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {!frozen && (
        <div className="topic-tools">
          <button
            type="button"
            className="secondary"
            onClick={() => change("topic", blankTopic())}
          >
            Create custom topic
          </button>
          <label className="file-input">
            Import topic JSON
            <input
              type="file"
              accept=".json"
              onChange={async (e) => {
                try {
                  const f = e.target.files[0];
                  if (!f) return;
                  if (f.size > 100000)
                    throw new Error("Use a topic file smaller than 100 KB.");
                  const parsed = JSON.parse(await f.text());
                  if (
                    Array.isArray(parsed) ||
                    !parsed?.name ||
                    !parsed?.resource ||
                    !Array.isArray(parsed.practice_stages)
                  )
                    throw new Error(
                      "Import one topic object with a name, resources, and practice stages.",
                    );
                  change("topic", cleanTopic({ ...blankTopic(), ...parsed }));
                  setError("");
                } catch (err) {
                  setError(err.message);
                }
                e.target.value = "";
              }}
            />
          </label>
        </div>
      )}
      {!frozen && (
        <div className="generate-row">
          <label>
            Generate a topic draft
            <input
              value={topicName}
              onChange={(e) => setTopicName(e.target.value)}
              placeholder="e.g. Software requirements"
            />
          </label>
          <button
            type="button"
            className="secondary"
            disabled={busy || !topicName.trim()}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                const data = await api("/platform/generate-topic", {
                  method: "POST",
                  body: { name: topicName, provider: value.provider },
                });
                change("topic", cleanTopic({ ...blankTopic(), ...data.draft }));
              } catch (e) {
                setError(e.message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Generating…" : "Generate draft"}
          </button>
        </div>
      )}
      {topic ? (
        <div className="topic-editor">
          <label>
            Topic name
            <input
              value={topic.name}
              onChange={(e) => editTopic("name", e.target.value)}
            />
          </label>
          <div className="form-columns">
            {["resource", "alt_resource"].map((key, i) => (
              <div key={key}>
                <h3>{i ? "Alternative reading" : "Primary reading"}</h3>
                <label>
                  Resource title
                  <input
                    value={topic[key]?.title || ""}
                    onChange={(e) =>
                      editTopic(key, { ...topic[key], title: e.target.value })
                    }
                  />
                </label>
                <label>
                  Resource URL
                  <input
                    type="url"
                    value={topic[key]?.url || ""}
                    onChange={(e) =>
                      editTopic(key, { ...topic[key], url: e.target.value })
                    }
                  />
                </label>
              </div>
            ))}
          </div>
          <label>
            Practice label
            <input
              value={topic.practice_label || ""}
              onChange={(e) => editTopic("practice_label", e.target.value)}
            />
          </label>
          <label>
            Practice prompt
            <textarea
              rows={4}
              value={topic.practice_prompt || ""}
              onChange={(e) => editTopic("practice_prompt", e.target.value)}
            />
          </label>
          <h3>Practice stages</h3>
          {(topic.practice_stages || []).map((s, i) => (
            <div className="stage-row" key={i}>
              <label>
                Stage {i + 1}
                <input
                  value={s.label}
                  onChange={(e) =>
                    editTopic(
                      "practice_stages",
                      topic.practice_stages.map((x, j) =>
                        j === i ? { ...x, label: e.target.value } : x,
                      ),
                    )
                  }
                />
              </label>
              <label>
                Focus
                <input
                  value={s.focus}
                  onChange={(e) =>
                    editTopic(
                      "practice_stages",
                      topic.practice_stages.map((x, j) =>
                        j === i ? { ...x, focus: e.target.value } : x,
                      ),
                    )
                  }
                />
              </label>
              <button
                type="button"
                className="quiet"
                disabled={topic.practice_stages.length < 2}
                onClick={() =>
                  editTopic(
                    "practice_stages",
                    topic.practice_stages.filter((_, j) => j !== i),
                  )
                }
              >
                Remove
              </button>
            </div>
          ))}
          {!frozen && (
            <button
              type="button"
              className="secondary compact"
              onClick={() =>
                editTopic("practice_stages", [
                  ...topic.practice_stages,
                  { label: "", focus: "" },
                ])
              }
            >
              Add stage
            </button>
          )}
          <div className="form-columns">
            <Lines
              label="Practice scenarios"
              value={topic.practice_options}
              onChange={(v) => editTopic("practice_options", v)}
            />
            <Lines
              label="Check questions"
              value={topic.check_questions}
              onChange={(v) => editTopic("check_questions", v)}
            />
          </div>
          <label>
            Worked example (available at wrap-up)
            <textarea
              rows={5}
              value={topic.final_example || ""}
              onChange={(e) => editTopic("final_example", e.target.value)}
            />
          </label>
        </div>
      ) : (
        <p className="empty">
          Select a topic template, import one, or create your own.
        </p>
      )}
    </>
  );
}

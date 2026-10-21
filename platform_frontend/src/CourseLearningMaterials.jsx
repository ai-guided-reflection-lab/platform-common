import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Notice } from "./ui";

function AssignmentKeywords({
  objectives,
  suggestedKeywords = [],
  assignmentConfig,
  onAssignmentChange,
  onPendingKeywordChange,
  disabled,
  frozen,
  courseId,
  keywordPreparation,
  onConfirmKeywords,
  onGenerateKeywords,
  canGenerateKeywords,
  generatingKeywords,
}) {
  const [localKeywords, setLocalKeywords] = useState([]);
  const [localOptional, setLocalOptional] = useState([]);
  const [localDismissed, setLocalDismissed] = useState([]);
  const [newKeyword, setNewKeyword] = useState("");
  const [error, setError] = useState("");
  const legacy = objectives.find(
    (item) =>
      item.objective_id === assignmentConfig?.learning_objective_id &&
      (frozen || item.status === "approved"),
  );
  const keywords = assignmentConfig
    ? assignmentConfig.keywords?.length ||
      !assignmentConfig.learning_objective_id
      ? assignmentConfig.keywords || []
      : legacy?.keywords || []
    : localKeywords;
  const pending = Boolean(newKeyword.trim());
  useEffect(() => {
    if (
      !frozen &&
      assignmentConfig?.learning_objective_id &&
      legacy &&
      !assignmentConfig.keywords?.length
    ) {
      onAssignmentChange?.({
        ...assignmentConfig,
        keywords: legacy.keywords || [],
        learning_objective_id: null,
        document_ids: [],
        prompt: "",
      });
    }
  }, [legacy, frozen, assignmentConfig, onAssignmentChange]);
  useEffect(() => {
    onPendingKeywordChange?.(pending);
  }, [pending, onPendingKeywordChange]);
  useEffect(
    () => () => onPendingKeywordChange?.(false),
    [onPendingKeywordChange],
  );
  const optionalKeywords = assignmentConfig?.optional_keywords || localOptional;
  const dismissedKeywords = assignmentConfig?.dismissed_keywords || localDismissed;
  const update = (
    next,
    nextOptional = optionalKeywords,
    nextDismissed = dismissedKeywords,
  ) => {
    setLocalKeywords(next);
    setLocalOptional(nextOptional);
    setLocalDismissed(nextDismissed);
    onAssignmentChange?.({
      ...assignmentConfig,
      keywords: next,
      optional_keywords: nextOptional,
      dismissed_keywords: nextDismissed,
      learning_objective_id: null,
    });
    setError("");
  };
  const candidates = [];
  const seen = new Set(keywords.map((item) => item.toLowerCase()));
  const dismissed = new Set(dismissedKeywords.map((item) => item.toLowerCase()));
  for (const word of [
    ...optionalKeywords,
    ...suggestedKeywords,
    ...objectives
      .filter((item) => item.status !== "rejected")
      .flatMap((item) => item.keywords || []),
  ]) {
    if (!seen.has(word.toLowerCase()) && !dismissed.has(word.toLowerCase())) {
      seen.add(word.toLowerCase());
      candidates.push(word);
    }
  }
  const addOptional = () => {
    const keyword = newKeyword.trim().replace(/\s+/g, " ");
    if (!keyword) return;
    if (
      [...keywords, ...candidates].some(
        (item) => item.toLowerCase() === keyword.toLowerCase(),
      )
    ) {
      setError("That keyword is already in Optional or Approved.");
      return;
    }
    if (optionalKeywords.length >= 40) return;
    update(
      keywords,
      [...optionalKeywords, keyword],
      dismissedKeywords.filter((item) => item.toLowerCase() !== keyword.toLowerCase()),
    );
    setNewKeyword("");
  };
  const approve = (word) => {
    if (keywords.length < 8) update([...keywords, word]);
  };
  const remove = (word) => {
    const lower = word.toLowerCase();
    update(
      keywords.filter((item) => item.toLowerCase() !== lower),
      optionalKeywords.filter((item) => item.toLowerCase() !== lower),
      dismissedKeywords.some((item) => item.toLowerCase() === lower)
        ? dismissedKeywords
        : [...dismissedKeywords, word],
    );
  };
  const confirmed =
    keywordPreparation?.ready &&
    keywordPreparation.course_id === courseId &&
    JSON.stringify(keywordPreparation.keywords) === JSON.stringify(keywords);
  return (
    <section className="assignment-keywords" aria-label="Assignment keywords">
      <h3>Assignment keywords</h3>
      <p className="help">
        Move the topics you want students to study from Optional to Approved,
        then confirm the list.
      </p>
      <div className="keyword-approval-grid">
        <section
          className="keyword-bucket keyword-bucket-optional"
          aria-label="Optional keywords"
        >
          <div className="keyword-bucket-heading">
            <div className="keyword-optional-heading">
              <h4>Optional</h4>
              {!frozen && (
                <button
                  type="button"
                  className="secondary keyword-generation"
                  disabled={disabled || !canGenerateKeywords}
                  onClick={onGenerateKeywords}
                >
                  {generatingKeywords
                    ? "Generating keywords…"
                    : "Keywords Generation"}
                </button>
              )}
            </div>
            <span>{candidates.length}</span>
          </div>
          <p className="help">
            Suggestions and your own keywords. These do not guide the chatbot
            yet.
          </p>
          <div className="keyword-candidate-list">
            {candidates.map((keyword) => (
              <div className="keyword-candidate-row" key={keyword}>
                <button
                  type="button"
                  className="keyword-candidate"
                  aria-label={`Approve keyword ${keyword}`}
                  disabled={disabled || frozen || keywords.length >= 8}
                  onClick={() => approve(keyword)}
                >
                  <span>{keyword}</span>
                  <span aria-hidden="true">→</span>
                </button>
                {!frozen && (
                  <button
                    type="button"
                    className="keyword-dismiss"
                    aria-label={`Delete keyword ${keyword}`}
                    title={`Delete ${keyword}`}
                    disabled={disabled}
                    onClick={() => remove(keyword)}
                  >
                    ×
                  </button>
                )}
              </div>
            ))}
            {!candidates.length && (
              <p className="help">
                Generate keywords from the selected documents, or add your own
                below.
              </p>
            )}
          </div>
          {!frozen && (
            <div className="keyword-optional-entry">
              <label className="sr-only" htmlFor="assignment-new-keyword">
                New keyword
              </label>
              <input
                id="assignment-new-keyword"
                value={newKeyword}
                maxLength={120}
                placeholder="Add an optional keyword"
                disabled={disabled || optionalKeywords.length >= 40}
                onChange={(event) => {
                  setNewKeyword(event.target.value);
                  setError("");
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    event.stopPropagation();
                    addOptional();
                  }
                }}
              />
              <button
                type="button"
                className="secondary keyword-add"
                aria-label="Add optional keyword"
                disabled={disabled || !pending || optionalKeywords.length >= 40}
                onClick={addOptional}
              >
                +
              </button>
            </div>
          )}
        </section>
        <section
          className="keyword-bucket keyword-bucket-approved"
          aria-label="Approved keywords"
        >
          <div className="keyword-bucket-heading">
            <h4>Approved</h4>
            <span>
              {keywords.length}/8 ·{" "}
              {frozen ? "Published" : confirmed ? "Confirmed" : "Not confirmed"}
            </span>
          </div>
          <p className="help">
            Only these topics will guide this assignment’s chatbot.
          </p>
          <div className="keyword-approved-list">
            {keywords.map((keyword) => (
              <span key={keyword} className="objective-keyword-chip">
                <span>{keyword}</span>
                <button
                  type="button"
                  className="keyword-remove"
                  aria-label={`Delete keyword ${keyword}`}
                  title={`Delete ${keyword}`}
                  disabled={disabled || frozen}
                  onClick={() => remove(keyword)}
                >
                  ×
                </button>
              </span>
            ))}
            {!keywords.length && (
              <p className="help">Choose keywords from the Optional box.</p>
            )}
          </div>
          {!frozen && (
            <button
              type="button"
              className="confirm-keywords"
              disabled={
                disabled ||
                pending ||
                !keywords.length ||
                confirmed ||
                !onConfirmKeywords
              }
              onClick={onConfirmKeywords}
            >
              {confirmed ? "Keywords confirmed" : "Confirm keywords"}
            </button>
          )}
          {frozen ? (
            <p className="help">
              Published list. Duplicate the assignment to change it.
            </p>
          ) : confirmed ? (
            <p className="keyword-prepared" role="status">
              Confirmed · {keywordPreparation.passage_count} indexed passages
              ready. You can publish the assignment.
            </p>
          ) : (
            <p className="help">
              Confirm to save the list and prepare course materials on the
              server. Confirm again after changing the list.
            </p>
          )}
        </section>
      </div>
      {pending && (
        <p className="help">
          Press + to add the typed keyword to Optional before saving.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

export default function CourseLearningMaterials({
  courseId,
  onChange,
  assignmentConfig,
  onAssignmentChange,
  onPendingKeywordChange,
  keywordPreparation,
  onConfirmKeywords,
  onInvalidateKeywordPreparation,
  frozen = false,
  embedded = false,
  hideDocuments = false,
  documents,
}) {
  const [resources, setResources] = useState({ files: [], objectives: [] });
  const [suggestedKeywords, setSuggestedKeywords] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const alive = useRef(true);
  const uploadInput = useRef(null);
  const prefix = `/courses/${courseId}`;
  async function load() {
    const [docs, objectives] = await Promise.all([
      api(`${prefix}/documents`),
      api(`${prefix}/learning-objectives`),
    ]);
    const value = {
      files: docs.files || [],
      objectives: objectives.objectives || [],
    };
    if (alive.current) {
      setResources(value);
      onChange?.(value);
    }
  }
  useEffect(() => {
    alive.current = true;
    setSuggestedKeywords([]);
    load().catch((e) => alive.current && setError(e.message));
    return () => {
      alive.current = false;
    };
  }, [courseId]);
  useEffect(() => {
    if (!documents) return;
    setResources((current) => ({ ...current, files: documents }));
  }, [documents]);
  useEffect(() => {
    if (!busy) return;
    setElapsed(0);
    const started = Date.now();
    const timer = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    return () => window.clearInterval(timer);
  }, [busy]);
  async function perform(label, action) {
    if (busy) return;
    setBusy(label);
    setError("");
    setNotice("");
    try {
      const result = await action();
      if (!alive.current) return;
      setNotice(result?.message || "Saved.");
      if (
        label === "Uploading and indexing documents" ||
        label.startsWith("Deleting ")
      )
        onInvalidateKeywordPreparation?.();
      await load();
    } catch (e) {
      if (alive.current) setError(e.message);
    } finally {
      if (alive.current) setBusy("");
    }
  }
  const Heading = embedded ? "h3" : "h2";
  const selectedDocumentIds = new Set(
    assignmentConfig?.document_ids || [],
  );
  const keywordFiles = resources.files.filter(
    (file) =>
      file.document_id &&
      (selectedDocumentIds.size
        ? selectedDocumentIds.has(file.document_id)
        : !hideDocuments),
  );
  const generateKeywords = () =>
    perform("Generating keywords", async () => {
      const results = await Promise.all(
        keywordFiles.map((file) =>
          api(`${prefix}/documents/${file.file_id}/keyword-suggestions`, {
            method: "POST",
          }),
        ),
      );
      const generated = results.flatMap((result) => result.keywords || []);
      setSuggestedKeywords((current) => [
        ...new Set([...current, ...generated]),
      ]);
      return {
        message: `Generated keywords from ${keywordFiles.length} selected document${keywordFiles.length === 1 ? "" : "s"}.`,
      };
    });
  return (
    <div
      className={`course-learning-manager${embedded ? " is-embedded" : ""}${hideDocuments ? " keywords-only" : ""}`}
      onKeyDown={(event) => {
        // Objective editing should never submit the surrounding assignment form.
        if (
          event.key === "Enter" &&
          event.target.tagName === "INPUT" &&
          event.target.type !== "file"
        )
          event.preventDefault();
      }}
    >
      {!hideDocuments && (
        <section
          className={`${embedded ? "" : "panel "}course-documents-card`}
          aria-label="Course documents"
        >
        <Heading>Course documents</Heading>
        <p>
          Upload course materials, then suggest keywords for the assignment.
        </p>
        <p className="help">
          Supported formats: TXT, Markdown, PDF, LaTeX, HTML, and HTM. Published
          assignments keep their saved materials.
        </p>
        <div className="course-document-upload">
          <label>
            Choose course documents
            <input
              ref={uploadInput}
              type="file"
              multiple
              accept=".txt,.md,.pdf,.tex,.latex,.html,.htm"
              disabled={Boolean(busy)}
              onChange={(e) => setSelectedFiles([...e.target.files])}
            />
          </label>
          <button
            type="button"
            disabled={Boolean(busy) || !selectedFiles.length}
            onClick={() => {
              if (!selectedFiles.length) return;
              perform("Uploading and indexing documents", async () => {
                const body = new FormData();
                selectedFiles.forEach((file) => body.append("files", file));
                const result = await api(`${prefix}/documents/upload`, {
                  method: "POST",
                  body,
                });
                setSelectedFiles([]);
                if (uploadInput.current) uploadInput.current.value = "";
                return result;
              });
            }}
          >
            Upload documents
          </button>
        </div>
        <div className="course-document-list">
          {!resources.files.length && (
            <p className="course-empty">No course documents uploaded yet.</p>
          )}
          {resources.files.map((file) => (
            <div className="course-document-row" key={file.file_id}>
              <div>
                <strong>{file.filename}</strong>
                <span className="help">
                  {Math.max(1, Math.round(file.file_size / 1024))} KB ·{" "}
                  {file.document_id ? "Indexed" : "Not indexed"}
                </span>
              </div>
              <div className="course-document-actions">
                <button
                  type="button"
                  className="quiet"
                  disabled={Boolean(busy)}
                  onClick={() => {
                    if (
                      window.confirm(
                        `Delete ${file.filename} and its learning objectives from this course? Published assignments keep their saved copy.`,
                      )
                    )
                      perform(`Deleting ${file.filename}`, () =>
                        api(`${prefix}/documents/${file.file_id}`, {
                          method: "DELETE",
                        }),
                      );
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
        </section>
      )}
      <AssignmentKeywords
        objectives={resources.objectives}
        suggestedKeywords={suggestedKeywords}
        assignmentConfig={assignmentConfig}
        onAssignmentChange={onAssignmentChange}
        onPendingKeywordChange={onPendingKeywordChange}
        courseId={courseId}
        keywordPreparation={keywordPreparation}
        onConfirmKeywords={onConfirmKeywords}
        onGenerateKeywords={generateKeywords}
        canGenerateKeywords={keywordFiles.length > 0}
        generatingKeywords={busy === "Generating keywords"}
        disabled={Boolean(busy)}
        frozen={frozen}
      />
      {busy && (
        <p role="status">
          {busy}… {elapsed}s elapsed
        </p>
      )}
      <Notice error={error} />
      <Notice>{notice}</Notice>
    </div>
  );
}

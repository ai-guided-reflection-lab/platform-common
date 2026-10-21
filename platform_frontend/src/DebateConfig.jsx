import { useEffect, useState } from "react";
import { api } from "./api";
import { Notice } from "./ui";

export default function DebateConfig({ value, onChange, courseId, frozen }) {
  const [files, setFiles] = useState([]);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const change = (key, next) => onChange({ ...value, [key]: next });

  function loadDocuments() {
    return api(`/courses/${courseId}/documents`).then((data) =>
      setFiles(data.files),
    );
  }

  useEffect(() => {
    if (courseId) loadDocuments().catch((err) => setError(err.message));
  }, [courseId]);

  return (
    <>
      <Notice error={error} />
      <div className="form-columns">
        <div>
          <label>
            Debate scenario or topic
            <textarea
              rows={8}
              required
              minLength={10}
              maxLength={10000}
              value={value.scenario}
              onChange={(event) => change("scenario", event.target.value)}
              placeholder="Should a city use facial recognition in public transit? Explain the decision context and constraints students should consider."
            />
          </label>
          <p className="help">
            Give students enough context to take a position and defend it.
          </p>
        </div>
        <div>
          <label>
            Opening prompt
            <textarea
              rows={4}
              maxLength={2000}
              value={value.opening_prompt}
              onChange={(event) => change("opening_prompt", event.target.value)}
              placeholder="Take a position and give your strongest reason."
            />
          </label>
          <label>
            Messages required before completion
            <input
              type="number"
              min={1}
              max={100}
              value={value.minimum_messages}
              onChange={(event) =>
                change("minimum_messages", Number(event.target.value))
              }
            />
          </label>
          <p className="help">
            Students can mark the assignment complete after this many responses.
          </p>
        </div>
        <div>
          <h3>Optional course materials</h3>
          <p className="help">
            Debate works without documents. If course materials are available,
            choose specific documents or leave all unchecked to use all current
            materials. Their indexed content is frozen at publication.
          </p>
          {files.map((file) => (
            <label className="check" key={file.file_id}>
              <input
                type="checkbox"
                disabled={!file.document_id}
                checked={(value.document_ids || []).includes(file.document_id)}
                onChange={(event) =>
                  change(
                    "document_ids",
                    event.target.checked
                      ? [...(value.document_ids || []), file.document_id]
                      : (value.document_ids || []).filter(
                          (id) => id !== file.document_id,
                        ),
                  )
                }
              />
              <span>{file.filename}</span>
            </label>
          ))}
          {!files.length && (
            <p>
              No course documents uploaded. Debate will use the scenario only.
            </p>
          )}
          {!frozen && (
            <label className="file-input">
              {uploading ? "Uploading…" : "Upload optional course materials"}
              <input
                type="file"
                accept=".txt,.md,.pdf,.tex,.latex,.html,.htm,.doc,.docx"
                multiple
                disabled={uploading || !courseId}
                onChange={async (event) => {
                  const selected = [...event.target.files];
                  event.target.value = "";
                  if (!selected.length) return;
                  setUploading(true);
                  setError("");
                  try {
                    const body = new FormData();
                    selected.forEach((file) => body.append("files", file));
                    await api(`/courses/${courseId}/documents/upload`, {
                      method: "POST",
                      body,
                    });
                    await loadDocuments();
                  } catch (err) {
                    setError(err.message);
                  } finally {
                    setUploading(false);
                  }
                }}
              />
            </label>
          )}
        </div>
      </div>
    </>
  );
}

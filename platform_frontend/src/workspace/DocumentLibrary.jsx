import React, { useState, useRef } from "react";
import { Link } from "react-router-dom";
import { useWorkspace } from "./WorkspaceContext";
import {
  uploadDocuments,
  downloadDocument as downloadPreviewFile,
} from "./service";
export function CourseDocumentLibrary() {
  const { items, refresh } = useWorkspace();
  const [selected, setSelected] = useState("");
  const [search, setSearch] = useState("");
  const [notice, setNotice] = useState("");
  const upload = useRef(null);
  const course = items.find((c) => c.id === selected);
  const files = items
    .filter((c) => !selected || c.id === selected)
    .flatMap((c) =>
      [...(c.documents || []), ...c.activities.flatMap((a) => a.files || [])]
        .filter(
          (f, i, all) =>
            all.findIndex((x) => x.name === f.name && x.size === f.size) === i,
        )
        .map((f) => ({ ...f, courseCode: c.code, courseId: c.id })),
    )
    .sort(
      (a, b) =>
        a.name.localeCompare(b.name, undefined, {
          numeric: true,
          sensitivity: "base",
        }) || a.courseCode.localeCompare(b.courseCode),
    );
  const visible = files.filter((f) =>
    `${f.name} ${f.courseCode}`.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <div className="course-document-library">
      <p className="p-eyebrow">INSTRUCTOR WORKSPACE</p>
      <h1>Document library</h1>
      <section className="studio-step">
        <div className="course-library-controls">
          <label>
            <span>Select course</span>
            <select
              value={selected}
              onChange={(e) => {
                setSelected(e.target.value);
                setSearch("");
                setNotice("");
              }}
            >
              <option value="">All courses</option>
              {items.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.code} · {c.title}
                </option>
              ))}
            </select>
          </label>
          <button disabled={!course} onClick={() => upload.current?.click()}>
            Add course materials
          </button>
          <input
            ref={upload}
            hidden
            type="file"
            aria-label="Upload materials to selected course"
            multiple
            accept=".pdf,.ppt,.pptx,.docx,.txt,.md"
            onChange={async (e) => {
              const input = e.target;
              if (!course) return;
              const files = Array.from(input.files);
              input.value = "";
              try {
                await uploadDocuments(files, selected);
                await refresh();
                setNotice("Documents indexed and ready to use.");
              } catch (e) {
                setNotice(e.message);
              }
            }}
          />
        </div>
        {!items.length && (
          <p>
            Create a course first to organize your materials.{" "}
            <Link to="/professor">Go to your courses</Link>
          </p>
        )}
        {notice && (
          <p className="studio-notice" role="status">
            {notice}
          </p>
        )}
        <div className="studio-library-toolbar">
          <h2>
            {course?.title || "All documents"}{" "}
            <span>{files.length} documents · A–Z</span>
          </h2>
          <label>
            <span>Search documents</span>
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or course…"
            />
          </label>
        </div>
        <div className="course-library-list course-library-downloads">
          <div className="course-library-list-head">
            <span>Document name</span>
            <span>Course</span>
            <span>Size</span>
            <span className="sr-only">Download</span>
          </div>
          {visible.map((f, i) => (
            <div
              className="course-library-list-row"
              key={`${f.courseId}:${f.id || i}`}
            >
              <strong title={f.name}>{f.name}</strong>
              <span title={f.courseCode}>{f.courseCode}</span>
              <span>{Math.max(1, Math.ceil(f.size / 1024))} KB</span>
              <button
                className="course-document-download"
                aria-label={`Download ${f.name}`}
                title={`Download ${f.name}`}
                onClick={async () => {
                  try {
                    await downloadPreviewFile(f);
                    setNotice("");
                  } catch (error) {
                    setNotice(error.message);
                  }
                }}
              >
                <svg
                  aria-hidden="true"
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 3v16m-6-6 6 6 6-6" />
                </svg>
              </button>
            </div>
          ))}
          {!visible.length && (
            <p className="studio-panel-empty">
              {search
                ? "No documents match your search."
                : "No materials yet. Choose a course above to add documents."}
            </p>
          )}
        </div>
      </section>
    </div>
  );
}

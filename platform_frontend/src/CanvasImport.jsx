import { useState } from "react";
import { api, TOOLS } from "./api";
import { Notice } from "./ui";

export default function CanvasImport({
  defaultTool,
  platformCourseId,
  onCourseCreated,
  onImported,
}) {
  const [accessToken, setAccessToken] = useState("");
  const [canvasCourses, setCanvasCourses] = useState([]);
  const [canvasCourseId, setCanvasCourseId] = useState("");
  const [assignments, setAssignments] = useState([]);
  const [assignmentId, setAssignmentId] = useState("");
  const [selectedTool, setSelectedTool] = useState(defaultTool);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function perform(action) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (caught) {
      setError(caught.message);
    } finally {
      setBusy(false);
    }
  }

  function loadCourses() {
    return perform(async () => {
      const courses = await api("/platform/integrations/canvas/courses", {
        method: "POST",
        body: { access_token: accessToken },
      });
      setCanvasCourses(courses);
      setCanvasCourseId("");
      setAssignments([]);
      setAssignmentId("");
    });
  }

  function loadAssignments() {
    return perform(async () => {
      const visible = await api("/platform/integrations/canvas/assignments", {
        method: "POST",
        body: { access_token: accessToken, course_id: canvasCourseId },
      });
      setAssignments(visible);
      setAssignmentId("");
    });
  }

  function importAssignment() {
    return perform(async () => {
      const draft = await api("/platform/integrations/canvas/import", {
        method: "POST",
        body: {
          access_token: accessToken,
          course_id: canvasCourseId,
          assignment_id: assignmentId,
          platform_course_id: platformCourseId,
          tool: selectedTool,
        },
      });
      setAccessToken("");
      onImported(draft);
    });
  }

  function createPlatformCourse() {
    return perform(async () => {
      const selected = canvasCourses.find(
        (course) => course.id === canvasCourseId,
      );
      if (!selected) throw new Error("Select a Canvas course first.");
      const created = await api("/courses", {
        method: "POST",
        body: {
          course_code: (selected.course_code || `CANVAS-${selected.id}`).slice(
            0,
            40,
          ),
          title: selected.name.slice(0, 160),
          description: `Imported from UNC Charlotte Canvas course ${selected.id}.`,
        },
      });
      onCourseCreated(created);
    });
  }

  return (
    <section className="panel canvas-import">
      <h2>Import from UNC Charlotte Canvas</h2>
      <p>
        Use your Canvas account to read active courses and assignments visible
        to you. Your access token is sent only to this server for the current
        request and is not saved.
      </p>
      <Notice error={error} />
      <div className="canvas-import-grid">
        <label>
          Chatbot for imported assignment
          <select
            value={selectedTool}
            onChange={(event) => setSelectedTool(event.target.value)}
          >
            {Object.entries(TOOLS).map(([id, tool]) => (
              <option key={id} value={id}>
                {tool.name}
              </option>
            ))}
          </select>
        </label>
        <span />
        <label>
          Canvas access token
          <input
            type="password"
            autoComplete="off"
            value={accessToken}
            onChange={(event) => setAccessToken(event.target.value)}
            placeholder="Paste a current Canvas token"
          />
        </label>
        <button
          type="button"
          className="secondary"
          disabled={busy || accessToken.length < 10}
          onClick={loadCourses}
        >
          Load Canvas courses
        </button>
        {canvasCourses.length > 0 && (
          <>
            <label>
              Canvas course
              <select
                value={canvasCourseId}
                onChange={(event) => {
                  setCanvasCourseId(event.target.value);
                  setAssignments([]);
                  setAssignmentId("");
                }}
              >
                <option value="">Select a Canvas course</option>
                {canvasCourses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.course_code
                      ? `${course.course_code} — ${course.name}`
                      : course.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="secondary"
              disabled={busy || !canvasCourseId}
              onClick={loadAssignments}
            >
              Load visible assignments
            </button>
            {!platformCourseId && (
              <button
                type="button"
                className="secondary canvas-create-course"
                disabled={busy || !canvasCourseId}
                onClick={createPlatformCourse}
              >
                Create ClubALL course from Canvas
              </button>
            )}
          </>
        )}
        {assignments.length > 0 && (
          <>
            <label>
              Canvas assignment
              <select
                value={assignmentId}
                onChange={(event) => setAssignmentId(event.target.value)}
              >
                <option value="">Select an assignment</option>
                {assignments.map((assignment) => (
                  <option key={assignment.id} value={assignment.id}>
                    {assignment.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={busy || !assignmentId || !platformCourseId}
              onClick={importAssignment}
            >
              Import as {TOOLS[selectedTool].name} draft
            </button>
          </>
        )}
      </div>
      {!platformCourseId && (
        <p className="help">
          Select a destination ClubALL course above, or create one from the
          selected Canvas course before importing.
        </p>
      )}
      <p className="help">
        Canvas content is copied into a draft. Review it, attach course
        materials, choose recipients, and publish from ClubALL.
      </p>
    </section>
  );
}

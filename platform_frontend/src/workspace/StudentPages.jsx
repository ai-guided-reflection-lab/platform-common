import React, { useState, useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useWorkspace } from "./WorkspaceContext";
import { chatName, dueLabel, CourseCard } from "./presentation";
import StudentDashboardView from "./StudentDashboardView";
export function CourseCodeJoin({ onJoined, compact = false }) {
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  const { refresh } = useWorkspace();
  const [busy, setBusy] = useState(false);
  const join = async (e) => {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const c = await api("/platform/courses/join", {
        method: "POST",
        body: { code: code.trim().toUpperCase() },
      });
      await refresh();
      setMessage(`You joined ${c.title}.`);
      setCode("");
    } catch (e) {
      setMessage(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section
      className={compact ? "student-compact-join" : "studio-student-join"}
      aria-label="Join a course"
    >
      <div>
        {!compact && <p className="p-eyebrow">YOUR LEARNING WORKSPACE</p>}
        {compact ? <h3>Join another course</h3> : <h1>Join a course</h1>}
        {!compact && <p>Enter the code from your instructor to get started.</p>}
      </div>
      <form onSubmit={join}>
        <label>
          <span>
            {compact ? "Enter your 8-character course code" : "Course code"}
          </span>
          <input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="Enter course code"
            minLength={8}
            maxLength={8}
            required
            autoComplete="off"
          />
        </label>
        <button disabled={busy || code.trim().length !== 8}>Join course</button>
      </form>
      {message && (
        <p className="studio-join-feedback" role="status">
          {message}
        </p>
      )}
    </section>
  );
}
function studentAssignments(items) {
  return items.flatMap((c) =>
    c.activities
      .filter((a) => a.status === "published")
      .map((a) => ({
        ...a,
        course_id: c.id,
        course_code: c.code,
        course: c.title,
        chat: chatName(a.tool),
        progress: a.progress || "not_started",
      })),
  );
}
const assignmentPath = (a) =>
  a.tool === "sdl"
    ? `/student/sdl/${a.id}`
    : a.tool === "reflections"
      ? `/student/reflection/${a.id}`
      : `/student/assignments/${a.id}`;
export function StudentOverview() {
  const { items, user } = useWorkspace();
  const courses = items.filter((c) => c.joined);
  const firstName = (user.display_name || user.username || "Student")
    .trim()
    .split(/\s+/)[0];
  return (
    <StudentDashboardView
      firstName={firstName}
      assignments={studentAssignments(items)}
      courses={courses}
      assignmentPath={assignmentPath}
      joinCourse={<CourseCodeJoin />}
      compactJoin={<CourseCodeJoin compact />}
    />
  );
}
export function StudentCoursePage() {
  const { courseId } = useParams();
  const navigate = useNavigate();
  const { items } = useWorkspace();
  const course = items.find((c) => c.id === courseId);
  const all = studentAssignments(items).filter((a) => a.course_id === courseId);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [courseId]);
  return (
    <div className="student-course-page">
      <div className="student-back-actions">
        <button
          className="secondary studio-back-button"
          onClick={() => navigate("/student")}
        >
          ← Back to your assignments
        </button>
      </div>
      {!course ? (
        <section className="studio-empty">
          <h1>Course not found</h1>
          <p>
            Join this course using your instructor’s code to view its
            assignments.
          </p>
        </section>
      ) : (
        <>
          <section className="student-course-heading">
            <p className="p-eyebrow">{course.code}</p>
            <h1>{course.title}</h1>
            <p>
              {course.description ||
                "Your instructor’s assignments and learning activities for this course."}
            </p>
            <span className="p-label">{all.length} ASSIGNMENTS</span>
          </section>
          <section aria-labelledby="course-assignments-title">
            <div className="p-section-title">
              <div>
                <h2 id="course-assignments-title">
                  Assignments in this course
                </h2>
                <p>Open an assignment to view its details and assigned chat.</p>
              </div>
            </div>
            <div className="student-course-assignment-list">
              {all.map((a, i) => (
                <Link
                  className="student-course-assignment"
                  to={assignmentPath(a)}
                  key={a.id}
                >
                  <span className="studio-number">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div className="student-course-assignment-title">
                    <small>{a.chat}</small>
                    <h3>{a.title}</h3>
                    <p>
                      {a.instructions ||
                        "Follow your instructor’s directions for this activity."}
                    </p>
                  </div>
                  <div className="student-course-assignment-meta">
                    <span className={`p-pill ${a.progress}`}>
                      {a.progress === "completed"
                        ? "Completed"
                        : a.progress === "in_progress"
                          ? "In progress"
                          : "New"}
                    </span>
                    <small>{dueLabel(a.due)}</small>
                  </div>
                  <span className="student-course-open">
                    {a.progress === "completed"
                      ? "View assignment"
                      : a.progress === "in_progress"
                        ? "Continue"
                        : "Open assignment"}{" "}
                    <span aria-hidden="true">→</span>
                  </span>
                </Link>
              ))}
              {!all.length && (
                <div className="student-status-empty">
                  Your instructor hasn’t published any assignments for this
                  course yet.
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

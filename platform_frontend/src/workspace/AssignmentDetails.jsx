import React, { useState, useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useWorkspace } from "./WorkspaceContext";
import { activityView } from "./service";
import { chatName, dueLabel } from "./presentation";
export function InstructorAssignmentDetails() {
  const { courseId, assignmentId } = useParams();
  const navigate = useNavigate();
  const { items } = useWorkspace();
  const course = items.find((c) => c.id === courseId);
  const [assignment, setAssignment] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setAssignment(null);
    api(`/platform/assignments/${assignmentId}`)
      .then((a) => {
        if (active) setAssignment(activityView(a, course?.documents || []));
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [assignmentId, course]);
  const students = assignment?.students || [];
  const assigned = students.length;
  const completed = students.filter((s) => s.progress === "completed").length;
  const inProgress = students.filter(
    (s) => s.progress === "in_progress",
  ).length;
  const pending = Math.max(0, assigned - completed);
  const rate = assigned ? Math.round((completed / assigned) * 100) : 0;
  return (
    <div className="instructor-assignment-detail">
      <div className="studio-assignment-navigation">
        <button
          className="secondary"
          onClick={() => navigate(`/professor/courses/${courseId}`)}
        >
          ← Back to course
        </button>
        <button className="secondary" onClick={() => navigate("/professor")}>
          Back to your courses
        </button>
      </div>
      {!assignment ? (
        <section className="studio-empty">
          <h1>{error || "Loading assignment…"}</h1>
        </section>
      ) : (
        <>
          <section className="studio-step">
            <div className="studio-assignment-detail-heading">
              <div>
                <p className="p-eyebrow">
                  {course.code} · {chatName(assignment.tool)}
                </p>
                <h1>{assignment.title}</h1>
                <p>{course.title}</p>
              </div>
              <span className={`p-pill ${assignment.status}`}>
                {assignment.status === "published" ? "Published" : "Draft"}
              </span>
            </div>
            <div className="studio-assignment-facts">
              <div>
                <span>Assigned chat</span>
                <strong>{chatName(assignment.tool)}</strong>
              </div>
              <div>
                <span>Due date</span>
                <strong>{dueLabel(assignment.due)}</strong>
              </div>
              <div>
                <span>Audience</span>
                <strong>All enrolled students</strong>
              </div>
            </div>
            <h2>Assignment instructions</h2>
            <p>
              {assignment.instructions ||
                "No additional instructions provided."}
            </p>
            {assignment.prompt && (
              <>
                <h2>Learning focus</h2>
                <p>{assignment.prompt}</p>
              </>
            )}
            <h2>Course materials</h2>
            {assignment.files?.length ? (
              assignment.files.map((f, i) => (
                <div className="course-library-list-row" key={i}>
                  <strong>{f.name}</strong>
                  <span>{Math.max(1, Math.ceil(f.size / 1024))} KB</span>
                </div>
              ))
            ) : (
              <p>No documents attached.</p>
            )}
            {assignment.status === "draft" && (
              <button
                onClick={() =>
                  navigate(
                    `/professor/courses/${courseId}/activities/${assignment.id}`,
                  )
                }
              >
                Edit activity
              </button>
            )}
          </section>
          <section
            className="studio-quick-analytics"
            aria-labelledby="quick-analytics-title"
          >
            <div className="p-section-title">
              <div>
                <h2 id="quick-analytics-title">At a glance</h2>
                <p>
                  {assignment.status === "draft"
                    ? "Publish this assignment to start collecting progress."
                    : "A quick view of student progress for this assignment."}
                </p>
              </div>
              <Link className="button secondary" to="/professor/analytics">
                Detailed insights →
              </Link>
            </div>
            <div className="studio-quick-stat-grid">
              {[
                ["Students assigned", assigned],
                ["Completed", completed],
                ["Pending", pending],
                ["In progress", inProgress],
              ].map(([label, value]) => (
                <div className="studio-quick-stat" key={label}>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
            <div className="studio-completion-summary">
              <div>
                <strong>{rate}% completed</strong>
                <span>
                  {completed} of {assigned} students · {pending} remaining
                </span>
              </div>
              <progress
                aria-label="Assignment completion rate"
                max="100"
                value={rate}
              />
            </div>
          </section>
        </>
      )}
    </div>
  );
}

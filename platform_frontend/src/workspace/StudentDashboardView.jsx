import React, { useState, useRef, useEffect, useId } from "react";
import { Link } from "react-router-dom";
import CardRail from "./CardRail";
import LearningArtwork from "./LearningArtwork";
import { CourseCard, dueLabel } from "./presentation";

export default function StudentDashboardView({
  firstName,
  assignments,
  courses,
  assignmentPath,
  joinCourse,
  compactJoin,
}) {
  const [query, setQuery] = useState("");
  const [joinOpen, setJoinOpen] = useState(false);
  const joinRef = useRef(null);
  const joinId = useId();
  useEffect(() => {
    if (joinOpen) joinRef.current?.querySelector("input")?.focus();
  }, [joinOpen]);
  const visible = assignments.filter((a) =>
    `${a.title} ${a.course} ${a.course_code} ${a.chat}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <div className="student-overview student-reference-layout">
      <div className="student-welcome-layout">
        {courses.length ? (
          <section className="student-welcome">
            <p className="p-eyebrow">YOUR LEARNING WORKSPACE</p>
            <h1>Welcome, {firstName}.</h1>
            <p>Your assignments and courses, all in one place.</p>
          </section>
        ) : (
          joinCourse
        )}
        <LearningArtwork />
        <div className="student-assignment-search">
          <label className="p-search">
            <SearchIcon />
            <input
              aria-label="Search assignments"
              placeholder="Search assignments, courses…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
        </div>
      </div>
      <section aria-label="Your assignments">
        {[
          ["not_started", "New", "Ready when you are. Start a new assignment."],
          ["in_progress", "In progress", "Pick up where you left off."],
          [
            "completed",
            "Completed",
            "Your finished assignments, all in one place.",
          ],
        ].map(([status, label, help]) => {
          const group = visible.filter((a) => a.progress === status);
          return (
            <section
              className="student-assignment-group"
              key={status}
              aria-label={`${label} assignments`}
            >
              <div className="student-group-heading">
                <div>
                  <h2>
                    {label}{" "}
                    <span className="workspace-count">{group.length}</span>
                  </h2>
                  <p>{help}</p>
                </div>
              </div>
              {group.length ? (
                <CardRail
                  label={`${label} assignments`}
                  className="student-assignment-rail"
                >
                  {group.map((a) => (
                    <Link
                      className={`student-assignment-card ${status}`}
                      key={a.id}
                      to={assignmentPath(a)}
                    >
                      <div className="student-card-top">
                        <span className="studio-chat-label">{a.chat}</span>
                      </div>
                      <h3>{a.title}</h3>
                      <p>
                        {a.instructions ||
                          "Follow your instructor’s directions for this activity."}
                      </p>
                      <div className="student-card-course">
                        <strong>{a.course}</strong>
                        <span>{a.course_code}</span>
                      </div>
                      <div className="student-card-footer">
                        <span>
                          <CalendarIcon />
                          {dueLabel(a.due)}
                        </span>
                        <strong>
                          {status === "completed"
                            ? "View assignment"
                            : status === "in_progress"
                              ? "Continue assignment"
                              : "Open assignment"}{" "}
                          <span aria-hidden="true">→</span>
                        </strong>
                      </div>
                    </Link>
                  ))}
                </CardRail>
              ) : (
                <div className="student-status-empty">
                  {query
                    ? "No matching assignments in this group."
                    : status === "completed"
                      ? "Your completed assignments will appear here."
                      : status === "in_progress"
                        ? "Assignments you start will appear here."
                        : "You’re up to date. New assignments will appear here when your instructor publishes them."}
                </div>
              )}
            </section>
          );
        })}
      </section>
      <section
        className="student-course-section"
        aria-labelledby="student-courses-title"
      >
        <div className="p-section-title">
          <div>
            <h2 id="student-courses-title">
              Your courses{" "}
              <span className="workspace-count">{courses.length}</span>
            </h2>
            <p>View assignments from each of your courses.</p>
          </div>
          {courses.length > 0 && (joinOpen ? (
            <div className="student-inline-join" id={joinId} ref={joinRef}>{compactJoin}</div>
          ) : (
            <button
              className="secondary student-join-toggle"
              aria-expanded={joinOpen}
              aria-controls={joinId}
              onClick={() => setJoinOpen((value) => !value)}
            >
              <span aria-hidden="true">＋</span>Join another course
            </button>
          ))}
        </div>
        {courses.length > 0 && (
          <CardRail label="Your courses" className="course-card-rail">
            {courses.map((c) => (
              <CourseCard
                key={c.id}
                course={c}
                to={`/student/courses/${c.id}`}
              />
            ))}
          </CardRail>
        )}

      </section>
    </div>
  );
}
function SearchIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="m16 16 5 5" />
    </svg>
  );
}
function CalendarIcon() {
  return (
    <svg
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M7 2v6m10-6v6M3 11h18" />
    </svg>
  );
}

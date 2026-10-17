import React from "react";
import { Link } from "react-router-dom";
export const choices = [
  ["socratic", "Socratic", "Explore ideas through guided questions."],
  ["reflections", "Reflections", "Connect experience with understanding."],
  [
    "sdl",
    "Self Directed Learning",
    "Build an adaptive lesson from your materials.",
  ],
  ["dialectic", "Debate", "The debate chatbot. No course materials required."],
  ["aiducate", "AIducate", "Assignment configuration coming soon."],
];
export const chatName = (tool) =>
  choices.find((t) => t[0] === tool)?.[1] ||
  (tool === "self-directed-learning" ? "Self Directed Learning" : tool);

export const dueLabel = (value) =>
  value
    ? new Date(
        value.length === 10 ? value + "T12:00:00" : value,
      ).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "No due date";
export function Step({ number, title, description, children }) {
  return (
    <section className="studio-step">
      <header>
        <span className="studio-number">{number}</span>
        <div>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
      </header>
      {children}
    </section>
  );
}
export function CourseCard({ course, onOpen, selected, to }) {
  const labelParts = course.code.split(/\s*[·•]\s*/);
  const content = (
    <>
      <div className="p-course-cover">
        <svg
          aria-hidden="true"
          width="40"
          height="40"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M12 5C8 2 4 3 2 4v16c4-1 7-1 10 1 3-2 6-2 10-1V4c-2-1-6-2-10 1Zm0 0v16" />
        </svg>
        <span className="studio-cover-code" title={course.code}>
          {labelParts.map((part, i) => (
            <span key={i}>{part}</span>
          ))}
        </span>
      </div>
      <div className="p-course-body">
        <h2>{course.title}</h2>
        <p>
          {course.description ||
            "Your course materials and learning activities, together in one place."}
        </p>
        <div className="p-course-footer">
          <span>
            {course.activities?.filter((a) => a.status === "published")
              .length || 0}{" "}
            published activities
          </span>
          <span className="studio-open-course">
            Open course <span aria-hidden="true">→</span>
          </span>
        </div>
      </div>
    </>
  );
  const className = `p-course teal studio-course-card studio-clickable-course ${selected ? "is-selected" : ""}`;
  return to ? (
    <Link className={className} to={to}>
      {content}
    </Link>
  ) : (
    <article
      className={className}
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
    >
      {content}
    </article>
  );
}

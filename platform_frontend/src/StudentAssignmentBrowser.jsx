import { useState } from "react";
import { Notice } from "./ui";

export default function StudentAssignmentBrowser({ items, error, reload, renderItems }) {
  const [view, setView] = useState(() =>
    localStorage.getItem("platform_student_assignment_view") === "list"
      ? "list"
      : "cards",
  );
  const finished = items?.filter((item) => item.progress === "completed") || [];
  const remaining = items
    ? items
        .filter((item) => item.progress !== "completed")
        .sort(
          (left, right) =>
            Number(right.progress === "in_progress") -
            Number(left.progress === "in_progress"),
        )
    : [];
  const completedPercent = items?.length
    ? Math.round((finished.length / items.length) * 100)
    : 0;

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="context">Your learning workspace</p>
          <h1>Your assignments</h1>
          <p>See what you have finished and what is left to do.</p>
        </div>
      </div>
      <div className="student-view-toolbar">
        <div className="assignment-view-switch" role="group" aria-label="Assignment display">
          {[["list", "List view"], ["cards", "Grid view"]].map(([key, title]) => (
            <button
              type="button"
              key={key}
              aria-label={title}
              title={title}
              aria-pressed={view === key}
              className={view === key ? "active" : ""}
              onClick={() => {
                setView(key);
                localStorage.setItem("platform_student_assignment_view", key);
              }}
            >
              {key === "cards" ? (
                <svg viewBox="0 0 20 20" aria-hidden="true">
                  <path d="M3 3h5v5H3zM12 3h5v5h-5zM3 12h5v5H3zM12 12h5v5h-5z" />
                </svg>
              ) : (
                <svg viewBox="0 0 20 20" aria-hidden="true">
                  <path d="M3 4h14M3 10h14M3 16h14" />
                </svg>
              )}
            </button>
          ))}
        </div>
      </div>
      <Notice error={error} />
      {!items ? (
        !error && <p role="status">Loading assignments…</p>
      ) : (
        <>
          <section className="student-progress-summary" aria-label="Assignment progress">
            <div className="student-progress-count">
              <span>Left to do</span>
              <strong>{remaining.length}</strong>
            </div>
            <div className="student-progress-count">
              <span>Finished</span>
              <strong>{finished.length}</strong>
            </div>
            <div
              className="student-progress-track"
              role="progressbar"
              aria-label="Assignment completion"
              aria-valuenow={finished.length}
              aria-valuemin={0}
              aria-valuemax={items.length || 1}
              aria-valuetext={`${finished.length} of ${items.length} assignments finished`}
            >
              <span style={{ width: `${completedPercent}%` }} />
            </div>
          </section>
          <section className="student-assignment-group" aria-labelledby="assignments-left">
            <h2 id="assignments-left">
              Left to do <span className="student-assignment-count">{remaining.length}</span>
            </h2>
            {remaining.length ? (
              renderItems(remaining, view)
            ) : (
              <p className="student-group-empty">You’re all caught up. No assignments left to do.</p>
            )}
          </section>
          <section className="student-assignment-group" aria-labelledby="assignments-finished">
            <h2 id="assignments-finished">
              Finished <span className="student-assignment-count">{finished.length}</span>
            </h2>
            {finished.length ? (
              renderItems(finished, view)
            ) : (
              <p className="student-group-empty">Finished assignments will appear here.</p>
            )}
          </section>
        </>
      )}
      {error && (
        <button className="secondary compact" onClick={reload}>
          Try again
        </button>
      )}
    </>
  );
}

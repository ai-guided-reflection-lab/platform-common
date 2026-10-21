import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { date, TOOLS } from "./api";
import { Badge } from "./ui";

export default function AssignmentDetails({ item, onClose }) {
  const dialog = useRef(null);
  useEffect(() => {
    const element = dialog.current;
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    element.showModal();
    return () => {
      element.close();
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, []);

  const config = item.config || {};
  return (
    <dialog
      ref={dialog}
      className="assignment-details"
      aria-labelledby="assignment-details-title"
      onCancel={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="assignment-details-content">
        <header>
          <div>
            <p className="context">
              {TOOLS[item.tool]?.name || "Choose a chatbot"} · Assignment
              details
            </p>
            <h2 id="assignment-details-title">{item.title}</h2>
          </div>
          <button
            type="button"
            className="quiet"
            aria-label="Close assignment details"
            onClick={onClose}
          >
            Close
          </button>
        </header>
        <dl className="assignment-details-meta">
          <div>
            <dt>Course</dt>
            <dd>{item.course_title || item.course_code || "Current course"}</dd>
          </div>
          <div>
            <dt>Status</dt>
            <dd>
              <Badge value={item.status} />
            </dd>
          </div>
          <div>
            <dt>Due date</dt>
            <dd>{date(item.due_at)}</dd>
          </div>
          <div>
            <dt>Assigned to</dt>
            <dd>
              {item.audience === "selected"
                ? "Selected students"
                : "All students in this course"}
            </dd>
          </div>
        </dl>
        <section>
          <h3>Instructions</h3>
          <p className="assignment-details-text">
            {item.instructions || "No instructions provided yet."}
          </p>
        </section>
        <section>
          <h3>Chatbot settings</h3>
          {!item.tool ? (
            <p>
              Choose an assigned chatbot in the assignment settings before
              publishing.
            </p>
          ) : item.tool === "socratic" || item.tool === "debate" ? (
            <>
              {item.tool === "debate" && (
                <p className="assignment-details-text">
                  {config.scenario ||
                    "Add a debate scenario in the assignment settings."}
                </p>
              )}
              <p className="assignment-details-text">
                {config.prompt ||
                  config.opening_prompt ||
                  "No custom opening question set."}
              </p>
              <p>
                Messages required:{" "}
                {config.minimum_messages ?? (item.tool === "debate" ? 3 : 1)}
              </p>
              <p>
                {config.document_ids?.length
                  ? `${config.document_ids.length} document(s) selected.`
                  : "Uses available course materials when no documents are selected."}
              </p>
            </>
          ) : item.tool === "reflections" ? (
            <>
              <p>
                {config.module_type === "milestone_based"
                  ? "Milestone reflection"
                  : "Topic reflection"}
              </p>
              <p className="assignment-details-text">
                {config.milestone_prompt ||
                  config.sub_topics?.join("\n") ||
                  "Add reflection topics or a milestone prompt in the assignment settings."}
              </p>
            </>
          ) : (
            <p>
              {config.topic?.name ||
                "Choose a practice topic in the assignment settings."}
            </p>
          )}
        </section>
        {item.status === "draft" && (
          <p className="help">
            Review these details and finish the chatbot settings before
            publishing for students.
          </p>
        )}
        <footer>
          <Link className="button" to={`/professor/assignments/${item.id}`}>
            {item.status === "draft"
              ? "Configure assignment"
              : "Manage assignment"}
          </Link>
        </footer>
      </div>
    </dialog>
  );
}

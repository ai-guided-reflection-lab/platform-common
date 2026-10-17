import React, { useState, useEffect, useRef } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { ReflectionConfig, defaults } from "../ToolConfig";
import { useWorkspace } from "./WorkspaceContext";
import {
  uploadDocuments,
  downloadDocument as downloadPreviewFile,
  saveActivity,
  activityView,
} from "./service";
import ActivityDocuments from "./ActivityDocuments";
import CanvasImport from "../CanvasImport";
import LessonReview from "./LessonReview";
import CardRail from "./CardRail";

import { choices, chatName, dueLabel, Step, CourseCard } from "./presentation";
const fresh = () => ({
  title: "",
  instructions: "",
  tool: "",
  files: [],
  prompt: "",
  due: "",
  reviewed: false,
  minimumMessages: 3,
  openingPrompt: "",
  reflectionType: "topic_based",
  depth: "balanced",
  style: "supportive",
  reflection: structuredClone(defaults.reflections),
  learningPlan: null,
});
export default function InstructorStudio() {
  const { items, refresh, user } = useWorkspace();
  const [busy, setBusy] = useState(false);
  const { courseId, activityId } = useParams();
  const navigate = useNavigate();
  const selected = courseId || "";
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [canvasCode, setCanvasCode] = useState("");
  const [description, setDescription] = useState("");
  const isActivityPage = Boolean(activityId);
  const draftKey = `workspace-draft:${user.user_id || user.id}:${courseId}:${activityId}`;
  const [draft, setDraft] = useState(() => {
    if (!activityId) return null;
    try {
      const cached = JSON.parse(localStorage.getItem(draftKey));
      if (cached) return cached;
    } catch {}
    return (
      items
        .find((c) => c.id === courseId)
        ?.activities.find((a) => a.id === activityId) || fresh()
    );
  });
  const [notice, setNotice] = useState("");
  const [codeExpanded, setCodeExpanded] = useState(false);
  const [copyMessage, setCopyMessage] = useState("");
  const codeDialog = useRef(null);
  useEffect(() => {
    if (!copyMessage) return;
    const timer = setTimeout(() => setCopyMessage(""), 3000);
    return () => clearTimeout(timer);
  }, [copyMessage]);
  useEffect(() => {
    if (!codeExpanded) return;
    const dialog = codeDialog.current;
    if (!dialog) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
      document.body.style.overflow = previousOverflow;
    };
  }, [codeExpanded]);
  const course = items.find((c) => c.id === selected);
  useEffect(() => {
    setCreating(false);
    window.scrollTo(0, 0);
  }, [courseId, activityId]);
  useEffect(() => {
    if (isActivityPage && draft)
      localStorage.setItem(draftKey, JSON.stringify(draft));
  }, [draft, draftKey, isActivityPage]);
  const library = course
    ? [
        ...(course.documents || []),
        ...course.activities.flatMap((a) => a.files || []),
      ].filter(
        (f, i, all) =>
          all.findIndex((x) => x.name === f.name && x.size === f.size) === i,
      )
    : [];
  const perform = async (fn) => {
    if (busy) return;
    setBusy(true);
    setNotice("");
    try {
      return await fn();
    } catch (e) {
      setNotice(e.message);
    } finally {
      setBusy(false);
    }
  };
  const change = (patch) =>
    setDraft((d) => ({
      ...d,
      ...patch,
      reviewed: false,
      ...("files" in patch || "prompt" in patch || "tool" in patch
        ? { learningPlan: null }
        : {}),
    }));
  const openCourse = (id) => {
    setDraft(null);
    setCreating(false);
    setNotice("");
    navigate(`/professor/courses/${id}`);
    window.scrollTo(0, 0);
  };
  const createCourse = (e) => {
    e.preventDefault();
    perform(async () => {
      const c = await api("/platform/courses", {
        method: "POST",
        body: { title: name.trim(), course_code: code.trim(), description },
      });
      await refresh();
      openCourse(c.course_id);
    });
  };
  const storeActivity = (status) =>
    perform(async () => {
      const a = await saveActivity(selected, draft, status, (saved) =>
        setDraft((d) => ({ ...d, id: saved.id })),
      );
      await refresh();
      localStorage.removeItem(draftKey);
      if (status === "published") navigate(`/professor/courses/${courseId}`);
      else {
        setDraft({ ...draft, id: a.id });
        if (activityId === "new")
          navigate(`/professor/courses/${courseId}/activities/${a.id}`, {
            replace: true,
          });
      }
      setNotice(
        status === "published" ? "Activity published." : "Draft saved.",
      );
    });
  const reviewActivity = () =>
    perform(async () => {
      if (draft.tool !== "sdl") {
        setDraft({ ...draft, reviewed: true });
        return;
      }
      const a = await saveActivity(selected, draft, "draft");
      setDraft((d) => ({ ...d, id: a.id }));
      const { learning_plan } = await api(
        `/platform/assignments/${a.id}/prepare-sdl`,
        { method: "POST" },
      );
      setDraft((d) => ({
        ...d,
        id: a.id,
        learningPlan: learning_plan,
        reviewed: true,
      }));
      await refresh();
    });
  const update = () => {
    refresh().catch((error) => setNotice(error.message));
  };
  const keepPreviewFile = async (file, courseId) =>
    (await uploadDocuments([file], courseId))[0];
  const progressRead = () => ({});
  return (
    <div className="instructor-studio">
      {!courseId && (
        <>
          <div className="studio-heading studio-heading-actions">
            <div>
              <p className="p-eyebrow">INSTRUCTOR WORKSPACE</p>
              <h1>Your courses</h1>
            </div>
            <button
              onClick={() => {
                setCreating(true);
                setDraft(null);
                setNotice("");
              }}
            >
              Create course
            </button>
          </div>
          <CardRail label="Your courses" className="course-card-rail">
            {items.map((c) => (
              <CourseCard
                key={c.id}
                course={c}
                to={`/professor/courses/${c.id}`}
              />
            ))}
          </CardRail>
          {!items.length && !creating && (
            <div className="studio-empty">
              <span className="studio-empty-mark" aria-hidden="true">
                01
              </span>
              <h2>A home for your first course.</h2>
              <p>
                Create a course, share its join code, and start building
                activities for your students.
              </p>
              <button onClick={() => setCreating(true)}>
                Create your first course
              </button>
            </div>
          )}

          {creating && (
            <Step
              number="01"
              title="Create a course"
              description="A unique student join code is generated automatically."
            >
              <form onSubmit={createCourse}>
                <div className="studio-fields">
                  <label>
                    Course name
                    <input
                      required
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Introduction to Software Engineering"
                      maxLength={150}
                    />
                  </label>
                  <label>
                    Course label
                    <input
                      required
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      placeholder="ITSC 3155 · Fall 2026"
                      maxLength={70}
                    />
                  </label>
                </div>
                <label>
                  Canvas code{" "}
                  <span className="studio-optional">
                    Optional · connection coming later
                  </span>
                  <input
                    value={canvasCode}
                    onChange={(e) => setCanvasCode(e.target.value)}
                    placeholder="Enter Canvas code"
                    maxLength={150}
                  />
                </label>
                <label>
                  Description <span className="studio-optional">Optional</span>
                  <textarea
                    rows={2}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </label>
                <div className="studio-actions">
                  <button disabled={!name.trim() || !code.trim()}>
                    Create course
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setCreating(false)}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            </Step>
          )}
        </>
      )}
      {courseId && (
        <div className="studio-back-actions">
          {isActivityPage && (
            <button
              className="secondary studio-back-button"
              onClick={() => navigate(`/professor/courses/${courseId}`)}
            >
              ← Back to your assignments
            </button>
          )}
          <button
            className="secondary studio-back-button"
            onClick={() => navigate("/professor")}
          >
            ← Back to your courses
          </button>
        </div>
      )}
      {notice && (
        <p className="studio-notice" role="status">
          {notice}
        </p>
      )}
      {courseId && !course && (
        <div className="studio-empty">
          <h2>Course not found</h2>
          <p>Return to your courses to choose an available course.</p>
        </div>
      )}
      {course && !creating && (
        <section
          className={`studio-opened-course ${!isActivityPage ? "studio-course-detail-reference" : ""}`}
          aria-label="Selected course"
        >
          {!isActivityPage && (
            <>
              <div className="studio-course-topbar">
                <div>
                  <span className="studio-course-label">{course.code}</span>
                  <h1>{course.title}</h1>
                  <p>
                    {course.students.length
                      ? `${course.students.length} student${course.students.length === 1 ? "" : "s"} enrolled`
                      : "No students yet"}{" "}
                    · Students join immediately after signing in.
                  </p>
                </div>
                <div className="studio-course-top-actions studio-code-actions">
                  <div className="studio-code">
                    <small>COURSE CODE</small>
                    <strong>{course.joinCode}</strong>
                  </div>
                  <div className="studio-code-action-stack">
                    <div className="studio-code-icon-buttons">
                      <button
                        className="studio-code-icon-button"
                        aria-label="Copy course code"
                        title="Copy course code"
                        onClick={async () => {
                          try {
                            await navigator.clipboard.writeText(
                              course.joinCode,
                            );
                            setCopyMessage("Course code copied");
                          } catch {
                            setCopyMessage("Select the code to copy it");
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
                          <rect x="8" y="8" width="12" height="13" rx="2" />
                          <path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h3" />
                        </svg>
                      </button>
                      <button
                        className="studio-code-icon-button"
                        aria-label="Expand course code"
                        title="Expand course code"
                        onClick={() => setCodeExpanded(true)}
                      >
                        <svg
                          aria-hidden="true"
                          width="19"
                          height="19"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.8"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <path d="M8 8 3 3m0 5V3h5m8 5 5-5m-5 0h5v5M8 16l-5 5m0-5v5h5m8-5 5 5m-5 0h5v-5" />
                        </svg>
                      </button>
                    </div>
                    <span
                      className="studio-code-copy-feedback"
                      role="status"
                      aria-live="polite"
                    >
                      {copyMessage}
                    </span>
                  </div>
                </div>
              </div>
              <dialog
                ref={codeDialog}
                className="studio-projector-dialog"
                aria-labelledby="projector-code-title"
                onCancel={() => setCodeExpanded(false)}
                onClose={() => setCodeExpanded(false)}
                onClick={(e) => {
                  if (e.target === e.currentTarget) {
                    const r = e.currentTarget.getBoundingClientRect();
                    if (
                      e.clientX < r.left ||
                      e.clientX > r.right ||
                      e.clientY < r.top ||
                      e.clientY > r.bottom
                    )
                      setCodeExpanded(false);
                  }
                }}
              >
                <button
                  className="studio-projector-close"
                  aria-label="Close expanded course code"
                  autoFocus
                  onClick={() => setCodeExpanded(false)}
                >
                  <svg
                    aria-hidden="true"
                    width="24"
                    height="24"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                  >
                    <path d="m6 6 12 12M18 6 6 18" />
                  </svg>
                </button>
                <div className="studio-projector-content">
                  <p className="p-eyebrow">{course.code}</p>
                  <h2 id="projector-code-title">Join this course</h2>
                  <p className="studio-projector-course-name">{course.title}</p>
                  <strong className="studio-projector-code">
                    {course.joinCode}
                  </strong>
                  <p className="studio-projector-instructions">
                    Sign in to your student workspace and enter this course
                    code.
                  </p>
                </div>
              </dialog>
              <section className="studio-activities">
                <div className="studio-activities-heading">
                  <h2>
                    Activities in this course{" "}
                    <span>{course.activities.length}</span>
                  </h2>
                  <button
                    onClick={() =>
                      navigate(`/professor/courses/${courseId}/activities/new`)
                    }
                  >
                    Create new activity{" "}
                    <svg
                      aria-hidden="true"
                      width="20"
                      height="20"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                    >
                      <path d="M12 4v16M4 12h16" />
                    </svg>
                  </button>
                </div>
                {!course.activities.length ? (
                  <p>
                    No activities yet. Create your first activity using the
                    button above.
                  </p>
                ) : (
                  course.activities.map((a) => {
                    const count =
                      a.submission_count ??
                      (progressRead()[a.id] === "completed" ? 1 : 0);
                    return (
                      <Link
                        className="studio-activity-link"
                        to={
                          a.status === "draft"
                            ? `/professor/courses/${courseId}/activities/${a.id}`
                            : `/professor/courses/${courseId}/assignments/${a.id}`
                        }
                        key={a.id}
                      >
                        <div className="studio-activity-main">
                          <div className="studio-activity-title-line">
                            <span className={`p-pill ${a.status}`}>
                              {a.status === "published" ? "Published" : "Draft"}
                            </span>
                            <h3>{a.title}</h3>
                          </div>
                          <small>
                            {chatName(a.tool)} · {dueLabel(a.due)}
                            {a.status === "published" && count > 0
                              ? ` · ${count} submission${count === 1 ? "" : "s"}`
                              : ""}
                          </small>
                        </div>
                        <span className="studio-view-assignment">
                          {a.status === "draft" ? "Edit draft" : "View"}{" "}
                          <span aria-hidden="true">→</span>
                        </span>
                      </Link>
                    );
                  })
                )}
              </section>
            </>
          )}
          {isActivityPage && (
            <div className="studio-activity-page-heading">
              <p className="p-eyebrow">
                {course.code} · {course.title}
              </p>
              <h1>
                {activityId === "new" ? "Create activity" : "Edit activity"}
              </h1>
              <p>
                Set the details, choose your materials and chat, then review and
                publish.
              </p>
              <small>
                Draft changes are saved in this preview as you work.
              </small>
            </div>
          )}
          {isActivityPage && draft && (
            <>
              <Step
                number="01"
                title="Activity details"
                description="Start with the details and materials shared by every activity type."
              >
                <div className="studio-fields">
                  <label>
                    <span className="studio-field-label">Activity title</span>
                    <input
                      required
                      value={draft.title}
                      onChange={(e) => change({ title: e.target.value })}
                      placeholder="Week 1: Exploring the fundamentals"
                    />
                  </label>
                  <label>
                    <span className="studio-field-label">
                      Due date <span className="studio-optional">Optional</span>
                    </span>
                    <input
                      type="date"
                      value={draft.due}
                      onChange={(e) => change({ due: e.target.value })}
                    />
                  </label>
                </div>
                <label>
                  Student instructions{" "}
                  <span className="studio-optional">Optional</span>
                  <textarea
                    rows={3}
                    value={draft.instructions}
                    onChange={(e) => change({ instructions: e.target.value })}
                    placeholder="What should students focus on?"
                  />
                </label>
                <ActivityDocuments
                  library={library}
                  selected={draft.files}
                  onChange={(files) => change({ files })}
                  onUpload={async (files) => {
                    const uploaded = await uploadDocuments(files, selected);
                    await refresh();
                    return uploaded;
                  }}
                  onContinue={() =>
                    document.querySelector(".studio-tools button")?.focus()
                  }
                />
              </Step>
              <Step
                number="02"
                title="Select activity"
                description="You choose the chat. Students open the activity you assign to them."
              >
                <CardRail label="Activity types" className="studio-tools">
                  {choices.map(([id, label, help]) => (
                    <button
                      key={id}
                      className={`studio-tool ${draft.tool === id ? "selected" : ""}`}
                      aria-pressed={draft.tool === id}
                      onClick={() =>
                        change({ tool: id, prompt: "", openingPrompt: "" })
                      }
                    >
                      <span className="studio-tool-symbol" aria-hidden="true">
                        {id === "dialectic"
                          ? "↔"
                          : id === "sdl"
                            ? "↗"
                            : id === "reflections"
                              ? "◎"
                              : "?"}
                      </span>
                      <strong>{label}</strong>
                      <span>{help}</span>
                    </button>
                  ))}
                </CardRail>
                {!draft.tool && (
                  <p className="studio-help">
                    Select a chat to show its configuration below.
                  </p>
                )}
                {draft.tool && (
                  <div className="studio-config" key={draft.tool}>
                    <p className="p-eyebrow">
                      {chatName(draft.tool)} configuration
                    </p>
                    {draft.tool === "aiducate" ? (
                      <div className="studio-callout">
                        <h3>AIducate</h3>
                        <p>
                          Assignment configuration will be added once its flow
                          is defined.
                        </p>
                      </div>
                    ) : draft.tool === "dialectic" ? (
                      <div>
                        <label>
                          Debate scenario or topic
                          <textarea
                            rows={6}
                            required
                            minLength={10}
                            maxLength={10000}
                            value={draft.prompt}
                            onChange={(e) => change({ prompt: e.target.value })}
                            placeholder="Should a city use facial recognition in public transit? Explain the decision context and constraints students should consider."
                          />
                        </label>
                        <p className="studio-help">
                          Give students enough context to take a position and
                          defend it. Course materials are optional.
                        </p>
                        <label>
                          Opening prompt{" "}
                          <span className="studio-optional">Optional</span>
                          <textarea
                            rows={3}
                            maxLength={2000}
                            value={draft.openingPrompt}
                            onChange={(e) =>
                              change({ openingPrompt: e.target.value })
                            }
                            placeholder="Take a position and give your strongest reason."
                          />
                        </label>
                        <label>
                          Messages required before completion
                          <input
                            type="number"
                            min={1}
                            max={100}
                            value={draft.minimumMessages}
                            onChange={(e) =>
                              change({
                                minimumMessages: Math.max(
                                  1,
                                  Math.min(100, Number(e.target.value) || 1),
                                ),
                              })
                            }
                          />
                        </label>
                      </div>
                    ) : (
                      <>
                        <label>
                          {draft.tool === "sdl"
                            ? "Learning topic and objectives"
                            : draft.tool === "socratic"
                              ? "Opening question"
                              : "Reflection topics"}
                          <textarea
                            rows={3}
                            value={draft.prompt}
                            onChange={(e) => change({ prompt: e.target.value })}
                            placeholder="What should students explore?"
                          />
                        </label>
                        {draft.tool === "socratic" && (
                          <label>
                            Messages required before completion
                            <input
                              type="number"
                              min={1}
                              max={100}
                              value={draft.minimumMessages}
                              onChange={(e) =>
                                change({
                                  minimumMessages: Math.max(
                                    1,
                                    Math.min(100, Number(e.target.value) || 1),
                                  ),
                                })
                              }
                            />
                          </label>
                        )}
                        {draft.tool === "reflections" && (
                          <div className="studio-fields">
                            <label>
                              Reflection type
                              <select
                                value={draft.reflectionType}
                                onChange={(e) =>
                                  change({ reflectionType: e.target.value })
                                }
                              >
                                <option value="topic_based">
                                  Topic-based conversation
                                </option>
                                <option value="milestone_based">
                                  Milestone reflection
                                </option>
                              </select>
                            </label>
                            <label>
                              Probing style
                              <select
                                value={draft.style}
                                onChange={(e) =>
                                  change({ style: e.target.value })
                                }
                              >
                                <option value="supportive">Supportive</option>
                                <option value="challenging">Challenging</option>
                                <option value="balanced">Balanced</option>
                              </select>
                            </label>
                          </div>
                        )}
                        {draft.tool === "sdl" && (
                          <div className="studio-callout">
                            <h3>Prepare an adaptive lesson</h3>
                            <p>
                              Your materials support the lesson’s objectives,
                              diagnostic quiz, examples, practice, and final
                              reflection.
                            </p>
                            <small>
                              This design preview shows the review layout; it
                              does not generate or index a lesson.
                            </small>
                          </div>
                        )}
                      </>
                    )}
                    <div className="studio-actions">
                      <button
                        className="secondary"
                        disabled={
                          !draft.title.trim() ||
                          draft.tool === "aiducate" ||
                          (draft.tool === "dialectic" &&
                            draft.prompt.trim().length < 10)
                        }
                        onClick={() => storeActivity("draft")}
                      >
                        Save draft
                      </button>
                      {draft.tool !== "dialectic" &&
                        draft.tool !== "aiducate" && (
                          <button
                            disabled={
                              !draft.title.trim() ||
                              (draft.tool === "sdl" && !draft.files.length)
                            }
                            onClick={reviewActivity}
                          >
                            Review activity
                          </button>
                        )}
                      <button
                        className="studio-text-button"
                        onClick={() =>
                          navigate(`/professor/courses/${courseId}`)
                        }
                      >
                        Back to course
                      </button>
                    </div>
                    {draft.tool === "sdl" && !draft.files.length && (
                      <p className="studio-help">
                        Add course materials above before reviewing the SDL
                        activity.
                      </p>
                    )}
                  </div>
                )}
              </Step>
              {draft.tool && (draft.tool === "dialectic" || draft.reviewed) && (
                <Step
                  number="03"
                  title="Review and publish"
                  description="Published activities appear in this course’s student assignment list."
                >
                  <div className="studio-review">
                    <span className="studio-course-label">
                      {chatName(draft.tool)}
                    </span>
                    <h3>{draft.title || "Add an activity title above"}</h3>
                    <p>
                      {draft.instructions ||
                        "Students open this instructor-assigned activity from their dashboard."}
                    </p>
                    <p>
                      <strong>Course:</strong> {course.title}
                    </p>
                    <p>
                      <strong>Due:</strong> {dueLabel(draft.due)}
                    </p>
                    {draft.prompt && (
                      <p>
                        <strong>
                          {draft.tool === "dialectic"
                            ? "Debate scenario:"
                            : "Learning focus:"}
                        </strong>{" "}
                        {draft.prompt}
                      </p>
                    )}
                    {draft.files.length > 0 && (
                      <p>
                        <strong>Materials:</strong>{" "}
                        {draft.files.map((f) => f.name).join(", ")}
                      </p>
                    )}
                    <p>
                      <strong>Audience:</strong> All enrolled students,
                      including those who join later.
                    </p>
                    <button
                      disabled={
                        !draft.title.trim() ||
                        draft.tool === "aiducate" ||
                        (draft.tool === "dialectic" &&
                          draft.prompt.trim().length < 10)
                      }
                      onClick={() => storeActivity("published")}
                    >
                      Publish activity
                    </button>
                  </div>
                </Step>
              )}
            </>
          )}
          {!isActivityPage && (
            <div className="studio-course-panels">
              <section
                className="studio-course-panel"
                aria-labelledby="enrolled-students-title"
              >
                <div className="studio-panel-heading">
                  <h2 id="enrolled-students-title">Enrolled students</h2>
                  <span className="p-label">
                    {course.students?.length || (course.joined ? 1 : 0)}{" "}
                    STUDENTS
                  </span>
                </div>
                {(course.students?.length
                  ? course.students
                  : course.joined
                    ? [{ name: "Alex Morgan", email: "alex@example.test" }]
                    : []
                ).map((student, i) => (
                  <div
                    className="studio-enrolled-student"
                    key={student.email || i}
                  >
                    <span className="p-avatar">
                      {(student.name || student.display_name || "Student")
                        .split(" ")
                        .map((n) => n[0])
                        .slice(0, 2)
                        .join("")}
                    </span>
                    <div>
                      <strong>
                        {student.name || student.display_name || "Student"}
                      </strong>
                      <small>{student.email}</small>
                    </div>
                    <span className="p-pill approved">Enrolled</span>
                  </div>
                ))}
                {!course.joined && !course.students?.length && (
                  <div className="studio-panel-empty">
                    <p>No students enrolled yet.</p>
                    <small>
                      Share the course code above. Students join immediately
                      after signing in.
                    </small>
                  </div>
                )}
              </section>
              <section
                className="studio-course-panel"
                aria-labelledby="course-library-title"
              >
                <div className="studio-panel-heading">
                  <h2 id="course-library-title">Document library</h2>
                  <label className="button secondary studio-library-upload">
                    Upload documents
                    <input
                      type="file"
                      multiple
                      accept=".pdf,.ppt,.pptx,.docx,.txt,.md"
                      onChange={async (e) => {
                        const input = e.target;
                        let files;
                        try {
                          files = await Promise.all(
                            Array.from(input.files).map((f) =>
                              keepPreviewFile(f, selected),
                            ),
                          );
                        } catch (error) {
                          setNotice(error.message);
                          return;
                        }
                        if (files.length) {
                          update(
                            items.map((c) =>
                              c.id === selected
                                ? {
                                    ...c,
                                    documents: [
                                      ...(c.documents || []),
                                      ...files,
                                    ],
                                  }
                                : c,
                            ),
                          );
                          setNotice(
                            `${files.length} document${files.length === 1 ? "" : "s"} added to this course’s preview library.`,
                          );
                        }
                        e.target.value = "";
                      }}
                    />
                  </label>
                </div>
                {(() => {
                  const files = [
                    ...(course.documents || []),
                    ...course.activities.flatMap((a) => a.files || []),
                  ].filter(
                    (f, i, all) =>
                      all.findIndex(
                        (x) => x.name === f.name && x.size === f.size,
                      ) === i,
                  );
                  return files.length ? (
                    <div className="studio-library-list">
                      {files.map((file, i) => (
                        <div className="studio-library-file" key={file.id || i}>
                          <svg
                            aria-hidden="true"
                            width="24"
                            height="28"
                            viewBox="0 0 24 28"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.5"
                          >
                            <path d="M4 2h10l6 6v18H4zM14 2v6h6M8 14h8M8 19h6" />
                          </svg>
                          <div>
                            <strong>{file.name}</strong>
                            <small>
                              {Math.max(1, Math.ceil(file.size / 1024))} KB ·
                              Course material
                            </small>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="studio-panel-empty">
                      <p>No course documents yet.</p>
                      <small>
                        Upload materials to keep them together in this course.
                      </small>
                    </div>
                  );
                })()}
              </section>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

export function ActivityCreationPage() {
  const { courseId, activityId } = useParams();
  return <InstructorStudio key={`${courseId}:${activityId}`} />;
}

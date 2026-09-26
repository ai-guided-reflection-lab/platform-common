import React, { useEffect, useState } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  Link,
  useNavigate,
  useParams,
} from "react-router-dom";
import { api, session, logout, TOOLS, date, label, SESSION_KEY } from "./api";
import AssignmentEditor from "./AssignmentEditor";
import CanvasImport from "./CanvasImport";
import StudentWorkspace from "./StudentWorkspace";
import "./styles.css";

import { Notice, Badge } from "./ui";

export function App() {
  const [user, setUser] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!session()?.access_token) {
      location.replace("/");
      return;
    }
    api("/auth/me")
      .then(({ user }) => {
        if (!user.onboarding_complete) {
          location.replace("/");
          return;
        }
        setUser(user);
      })
      .catch((e) => setError(e.message));
    const id = setInterval(
      async () => {
        try {
          const refreshed = await api("/auth/session/refresh", {
            method: "POST",
          });
          localStorage.setItem(
            SESSION_KEY,
            JSON.stringify({
              ...session(),
              access_token: refreshed.access_token,
              expires_at: Date.now() + refreshed.expires_in_seconds * 1000,
            }),
          );
        } catch (e) {
          setError(e.message);
        }
      },
      20 * 60 * 1000,
    );
    return () => clearInterval(id);
  }, []);
  if (!user)
    return (
      <main className="loading">
        <h1>ClubALL</h1>
        <Notice error={error}>{!error && "Opening your workspace…"}</Notice>
        {error && <a href="/">Return to sign in</a>}
      </main>
    );
  const isProfessor = user.authority_level <= 1;
  const home = isProfessor ? "/professor" : "/student";
  return (
    <>
      <header className="site-header">
        <Link className="brand" to={home}>
          Club<span>ALL</span>
          <small>Learning workspace</small>
        </Link>
        <nav aria-label="Main navigation">
          {isProfessor ? (
            <>
              <Link to={home}>Professor dashboard</Link>
              <a href="/?manage=1">Courses &amp; access</a>
            </>
          ) : (
            <Link to={home}>Dashboard</Link>
          )}
        </nav>
        <div className="identity">
          <span>{user.display_name || user.username}</span>
          <button className="quiet" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <main className="main">
        <Routes>
          <Route path="/" element={<Navigate to={home} replace />} />
          <Route
            path="/professor"
            element={
              isProfessor ? (
                <Dashboard professor />
              ) : (
                <Navigate to={home} replace />
              )
            }
          />
          <Route
            path="/professor/tools/:tool"
            element={
              isProfessor ? <ToolDashboard /> : <Navigate to={home} replace />
            }
          />
          <Route
            path="/professor/tools/:tool/assignments/:id"
            element={
              isProfessor ? (
                <AssignmentEditor />
              ) : (
                <Navigate to={home} replace />
              )
            }
          />
          <Route
            path="/student"
            element={
              !isProfessor ? (
                <StudentDashboard />
              ) : (
                <Navigate to={home} replace />
              )
            }
          />
          <Route
            path="/student/assignments/:id"
            element={
              !isProfessor ? (
                <StudentWorkspace />
              ) : (
                <Navigate to={home} replace />
              )
            }
          />
          <Route
            path="*"
            element={
              <div className="empty">
                <h1>Page not found</h1>
                <Link to={home}>Return to your dashboard</Link>
              </div>
            }
          />
        </Routes>
      </main>
      <footer>
        ClubALL <span>One workspace. Three ways to learn.</span>
      </footer>
    </>
  );
}

function useAssignments() {
  const [items, setItems] = useState(null),
    [error, setError] = useState("");
  const reload = () =>
    api("/platform/assignments")
      .then(setItems)
      .catch((e) => setError(e.message));
  useEffect(() => {
    reload();
  }, []);
  return { items, error, reload };
}

function useCourses() {
  const [courses, setCourses] = useState(null),
    [error, setError] = useState("");
  const reload = () =>
    api("/courses")
      .then(({ courses: loaded }) => {
        setCourses(loaded);
        setError("");
      })
      .catch((e) => setError(e.message));
  useEffect(() => {
    reload();
  }, []);
  return { courses, error, reload };
}

function AssignmentList({ items, professor }) {
  if (!items.length)
    return (
      <div className="empty">
        <h3>
          {professor
            ? "Your assignments will appear here"
            : "You’re all caught up here"}
        </h3>
        <p>
          {professor
            ? "Choose a tool to configure and publish your first assignment."
            : "Published assignments appear here once your professor assigns them to you. Check Courses & access to join a class."}
        </p>
      </div>
    );
  return (
    <div className="assignment-list">
      {items.map((item) => (
        <article className="assignment-row" key={item.id}>
          <div
            className="tool-mark"
            style={{ "--tool-color": TOOLS[item.tool].color }}
            aria-label={TOOLS[item.tool].name}
          >
            {TOOLS[item.tool].short}
          </div>
          <div className="assignment-name">
            <span className="subtle">
              {item.course_code} · {TOOLS[item.tool].name}
            </span>
            <h3>
              <Link
                to={
                  professor
                    ? `/professor/tools/${item.tool}/assignments/${item.id}`
                    : `/student/assignments/${item.id}`
                }
              >
                {item.title}
              </Link>
            </h3>
            <span className="subtle">
              {item.due_at ? `Due ${date(item.due_at)}` : "No due date"}
            </span>
          </div>
          <div className="assignment-state">
            <Badge value={professor ? item.status : item.progress} />
            {professor && item.status !== "draft" && (
              <small>
                {item.completed_count} of {item.recipient_count} completed
              </small>
            )}
          </div>
          <Link
            className="button secondary compact"
            to={
              professor
                ? `/professor/tools/${item.tool}/assignments/${item.id}`
                : `/student/assignments/${item.id}`
            }
          >
            {professor
              ? "Manage"
              : item.progress === "completed"
                ? "View result"
                : item.progress === "in_progress"
                  ? "Resume"
                  : "Open assignment"}
          </Link>
        </article>
      ))}
    </div>
  );
}

function StudentDashboard() {
  const assignments = useAssignments();
  const courseData = useCourses();
  const [expandedCourse, setExpandedCourse] = useState(
    () => new URLSearchParams(window.location.search).get("course") || "",
  );
  const [requestingCourse, setRequestingCourse] = useState("");
  const [actionError, setActionError] = useState("");

  async function requestAccess(courseId) {
    setRequestingCourse(courseId);
    setActionError("");
    try {
      await api(`/courses/${courseId}/request-access`, { method: "POST" });
      await courseData.reload();
    } catch (error) {
      setActionError(error.message);
    } finally {
      setRequestingCourse("");
    }
  }

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="context">Student workspace</p>
          <h1>Dashboard</h1>
          <p>
            Open a course to see its assignments, or request access to another
            class.
          </p>
        </div>
        <button
          className="quiet"
          onClick={() => {
            assignments.reload();
            courseData.reload();
          }}
        >
          Refresh
        </button>
      </div>
      <Notice error={assignments.error || courseData.error || actionError} />
      <section className="section student-courses">
        <div className="section-heading">
          <h2>Your courses</h2>
        </div>
        {courseData.courses && assignments.items ? (
          courseData.courses.length ? (
            <div className="student-course-grid">
              {courseData.courses.map((course) => {
                const approved = course.membership_status === "approved";
                const expanded =
                  approved && expandedCourse === course.course_id;
                const courseAssignments = assignments.items.filter(
                  (item) => item.course_id === course.course_id,
                );
                return (
                  <article
                    className={`student-course-card${expanded ? " is-expanded" : ""}`}
                    key={course.course_id}
                  >
                    <div className="student-course-summary">
                      <div className="student-course-topline">
                        <span className="course-code">{course.course_code}</span>
                        <Badge
                          value={
                            course.membership_status ||
                            course.membership_role ||
                            "available"
                          }
                        />
                      </div>
                      <h3>{course.title}</h3>
                      <p>
                        {course.description ||
                          "No course description has been added yet."}
                      </p>
                      <div className="student-course-meta">
                        <span>Instructor: {course.instructor_name}</span>
                        <span>{course.document_count} document(s)</span>
                        {approved && (
                          <span>{courseAssignments.length} assignment(s)</span>
                        )}
                      </div>
                      <div className="student-course-actions">
                        {approved ? (
                          <button
                            type="button"
                            aria-expanded={expanded}
                            aria-controls={`course-assignments-${course.course_id}`}
                            onClick={() =>
                              setExpandedCourse((current) =>
                                current === course.course_id
                                  ? ""
                                  : course.course_id,
                              )
                            }
                          >
                            Assignments
                            <span aria-hidden="true">
                              {expanded ? "−" : "+"}
                            </span>
                          </button>
                        ) : course.membership_status === "pending" ? (
                          <button type="button" disabled>
                            Waiting for approval
                          </button>
                        ) : (
                          <button
                            type="button"
                            disabled={requestingCourse === course.course_id}
                            onClick={() => requestAccess(course.course_id)}
                          >
                            {requestingCourse === course.course_id
                              ? "Requesting…"
                              : course.membership_status === "rejected"
                                ? "Request again"
                                : "Request access"}
                          </button>
                        )}
                      </div>
                    </div>
                    {expanded && (
                      <section
                        className="course-assignment-panel"
                        id={`course-assignments-${course.course_id}`}
                        aria-label={`${course.course_code} assignments`}
                      >
                        <div className="course-assignment-heading">
                          <div>
                            <span>{course.course_code}</span>
                            <h3>Assignments</h3>
                          </div>
                          <button
                            type="button"
                            className="quiet compact"
                            onClick={() => setExpandedCourse("")}
                          >
                            Collapse
                          </button>
                        </div>
                        <AssignmentList
                          items={courseAssignments}
                          professor={false}
                        />
                      </section>
                    )}
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="empty">
              <h3>No courses are available yet</h3>
              <p>Your available and enrolled courses will appear here.</p>
            </div>
          )
        ) : (
          !assignments.error &&
          !courseData.error && <p role="status">Loading dashboard…</p>
        )}
      </section>
    </>
  );
}

function Dashboard({ professor = false }) {
  const { items, error, reload } = useAssignments();
  const [course, setCourse] = useState(""),
    [status, setStatus] = useState("");
  const courses = [
    ...new Map(
      (items || []).map((a) => [a.course_id, a.course_code]),
    ).entries(),
  ];
  const filtered = (items || []).filter(
    (a) =>
      (!course || a.course_id === course) &&
      (!status || (professor ? a.status : a.progress) === status),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="context">
            {professor ? "Teaching workspace" : "Student workspace"}
          </p>
          <h1>
            {professor
              ? "Choose how you’ll teach."
              : "Your next steps, all here."}
          </h1>
          <p>
            {professor
              ? "Select a tool to open its professor dashboard and configure assignments."
              : "Open an assignment to continue in the right learning tool."}
          </p>
        </div>
      </div>
      {professor && (
        <div className="tool-grid">
          {Object.entries(TOOLS).map(([id, tool]) => (
            <Link
              className="tool-card"
              to={`/professor/tools/${id}`}
              key={id}
              style={{ "--tool-color": tool.color }}
            >
              <div className="tool-mark">{tool.short}</div>
              <h2>{tool.name}</h2>
              <p>{tool.description}</p>
              <span>
                Open professor dashboard <span aria-hidden="true">↗</span>
              </span>
            </Link>
          ))}
        </div>
      )}
      <section className="section">
        <div className="section-heading">
          <h2>{professor ? "All assignments" : "Assigned to you"}</h2>
          <div className="filters">
            <select
              aria-label="Filter by course"
              value={course}
              onChange={(e) => setCourse(e.target.value)}
            >
              <option value="">All courses</option>
              {courses.map(([id, code]) => (
                <option key={id} value={id}>
                  {code}
                </option>
              ))}
            </select>
            <select
              aria-label="Filter by status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">All statuses</option>
              {(professor
                ? ["draft", "published", "archived"]
                : ["not_started", "in_progress", "completed"]
              ).map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                </option>
              ))}
            </select>
            <button className="quiet" onClick={reload}>
              Refresh
            </button>
          </div>
        </div>
        <Notice error={error} />
        {items ? (
          <AssignmentList items={filtered} professor={professor} />
        ) : (
          !error && <p role="status">Loading assignments…</p>
        )}
      </section>
    </>
  );
}

function ToolDashboard() {
  const { tool } = useParams(),
    navigate = useNavigate();
  const { items, error } = useAssignments();
  const [courses, setCourses] = useState([]),
    [course, setCourse] = useState(""),
    [courseError, setCourseError] = useState("");
  useEffect(() => {
    api("/courses")
      .then(({ courses }) =>
        setCourses(courses.filter((c) => c.membership_role === "instructor")),
      )
      .catch((e) => setCourseError(e.message));
  }, []);
  if (!TOOLS[tool]) return <Navigate to="/professor" replace />;
  return (
    <>
      <Link className="back" to="/professor">
        ← All tools
      </Link>
      <div className="page-heading">
        <div>
          <p className="context">Professor dashboard</p>
          <h1>{TOOLS[tool].name}</h1>
          <p>{TOOLS[tool].description}</p>
        </div>
        <div className="create-controls">
          <label>
            Course
            <select value={course} onChange={(e) => setCourse(e.target.value)}>
              <option value="">Select a course</option>
              {courses.map((c) => (
                <option key={c.course_id} value={c.course_id}>
                  {c.course_code} — {c.title}
                </option>
              ))}
            </select>
          </label>
          <button
            disabled={!course}
            onClick={() =>
              navigate(
                `/professor/tools/${tool}/assignments/new?course=${course}`,
              )
            }
          >
            New assignment
          </button>
        </div>
      </div>
      <Notice error={error || courseError} />
      {!courses.length && !courseError && (
        <p className="notice">
          Create a course and approve student enrollments in{" "}
          <a href="/?manage=1">Courses &amp; access</a> to start assigning work.
        </p>
      )}
      <CanvasImport
        defaultTool={tool}
        platformCourseId={course}
        onCourseCreated={(created) => {
          setCourses((current) => [...current, created]);
          setCourse(created.course_id);
        }}
        onImported={(draft) =>
          navigate(`/professor/tools/${draft.tool}/assignments/${draft.id}`)
        }
      />
      <section className="section">
        <h2>{course ? "Course assignments" : "Assignments in this tool"}</h2>
        {items ? (
          <AssignmentList
            professor
            items={items.filter(
              (a) => a.tool === tool && (!course || a.course_id === course),
            )}
          />
        ) : (
          <p>Loading assignments…</p>
        )}
      </section>
    </>
  );
}

class ErrorBoundary extends React.Component {
  state = { error: null };
  static getDerivedStateFromError(error) {
    return { error };
  }
  render() {
    return this.state.error ? (
      <main className="loading">
        <h1>This view could not load.</h1>
        <p>Your saved work is still available.</p>
        <button onClick={() => location.reload()}>Reload</button>
      </main>
    ) : (
      this.props.children
    );
  }
}

export function Root() {
  return (
    <ErrorBoundary>
      <BrowserRouter basename="/platform">
        <App />
      </BrowserRouter>
    </ErrorBoundary>
  );
}

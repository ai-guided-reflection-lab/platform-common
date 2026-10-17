import React, { lazy, Suspense, useEffect, useRef, useState } from "react";
import {
  BrowserRouter,
  Link,
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import { api, logout, session, SESSION_KEY } from "../api";
import { configureStudentTransport } from "../../../adaptive-learning-app/student-app/src/api";
import { studentTransport } from "../self-directed-api";
import { WorkspaceProvider, useWorkspace } from "./WorkspaceContext";
import InstructorStudio, {
  ActivityCreationPage,
  CourseDocumentLibrary,
  InstructorAssignmentDetails,
  StudentCoursePage,
  StudentOverview,
} from "./Studio";
import { Insights, People, Settings } from "./SupportingPages";
import SignIn from "./SignIn";
import "./approved-base.css";
import "./approved-sdl.css";

import "./workspace.css";
import "./integration.css";
import "./reference-cards.css";

const StudentWorkspace = lazy(() => import("../StudentWorkspace"));
const ReflectionAssignment = lazy(() => import("./ApprovedReflection"));
const LessonWorkspace = lazy(
  () =>
    import("../../../adaptive-learning-app/student-app/src/LessonWorkspace"),
);
configureStudentTransport(studentTransport);

function ChatRoute({ type }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const { refresh } = useWorkspace();
  useEffect(
    () => () => {
      refresh().catch(() => {});
    },
    [refresh],
  );
  return (
    <div className="connected-chat-content">
      <Suspense fallback={<p role="status">Opening your assignment…</p>}>
        {type === "sdl" ? (
          <LessonWorkspace
            key={id}
            assignmentId={id}
            onBack={() => navigate("/student")}
          />
        ) : type === "reflections" ? (
          <ReflectionAssignment key={id} assignmentId={id} />
        ) : (
          <StudentWorkspace key={id} />
        )}
      </Suspense>
    </div>
  );
}

const icons = {
  grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
  book: "M12 5C8 2 4 3 2 4v16c4-1 7-1 10 1 3-2 6-2 10-1V4c-2-1-6-2-10 1Zm0 0v16",
  chat: "M4 4h16v12H9l-5 4V4Zm4 4h8M8 12h5",
  reflect: "M5 3h11l3 3v15H5V3Zm4 5h5M9 12h6M9 16h4",
  folder: "M3 7V4h6l2 3h10v13H3V7Z",
  chart: "M4 20V4M4 20h17M8 16v-5M13 16V7M18 16v-8",
  settings:
    "M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M6 18l2-2M16 8l2-2M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  arrow: "M5 12h14M13 6l6 6-6 6",
  check: "m5 12 4 4L19 6",
  plus: "M12 5v14M5 12h14",
  search: "M16 16l5 5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z",
  bell: "M6 16h12l-2-3V9a4 4 0 0 0-8 0v4l-2 3Zm4 4h4",
  calendar: "M4 5h16v16H4V5ZM8 2v6M16 2v6M4 10h16",
  upload: "M12 16V3M7 8l5-5 5 5M4 16v5h16v-5",
  users:
    "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 10v-3a7 7 0 0 1 14 0v3M17 4a4 4 0 0 1 0 7M20 14a5 5 0 0 1 2 4v3",
};
function Icon({ name, size = 20 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={icons[name] || icons.book} />
    </svg>
  );
}
export function Shell() {
  const { user, professor } = useWorkspace();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobile, setMobile] = useState(false);
  const [switchError, setSwitchError] = useState("");
  const profileMenu = useRef(null);
  const base = professor ? "/professor" : "/student";
  const name = user.display_name || user.username;
  const initials = name
    .split(/\s+/)
    .map((n) => n[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  useEffect(() => {
    const outside = (e) => {
      if (profileMenu.current && !profileMenu.current.contains(e.target))
        profileMenu.current.removeAttribute("open");
    };
    const escape = (e) => {
      if (e.key === "Escape" && profileMenu.current?.open) {
        profileMenu.current.removeAttribute("open");
        profileMenu.current.querySelector("summary")?.focus();
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, []);
  const choose = async (r) => {
    if ((r === "professor") === professor) {
      navigate(base);
      return;
    }
    try {
      const data = await api(session()?.demo_mode ? "/platform/demo/role" : "/platform/testing/role", {
        method: "POST",
        body: { role: r },
      });
      localStorage.setItem(
        SESSION_KEY,
        JSON.stringify({
          ...data,
          expires_at: Date.now() + data.expires_in_seconds * 1000,
        }),
      );
      window.location.assign(`/platform/${r}`);
    } catch (error) {
      setSwitchError(error.message);
    }
  };
  const nav = [
    ["Overview", base, "grid"],
    ...(professor
      ? [
          ["Document library", "/professor/documents", "folder"],
          ["Learning insights", "/professor/analytics", "chart"],
          ["People & access", "/professor/people", "users"],
        ]
      : []),
    ["Settings", `${base}/settings`, "settings"],
  ];
  return (
    <div className={`p-app ${professor ? "" : "p-student-app"}`}>
      <a className="p-skip" href="#preview-content">
        Skip to main content
      </a>
      {professor && (
        <aside className={`p-sidebar ${mobile ? "is-open" : ""}`}>
          <Link className="p-brand" to={base}>
            <span>
              <Icon name="book" size={25} />
            </span>
            CourseLab
            <span className="p-brand-dot" />
          </Link>
          <div className="p-campus">
            <span className="p-campus-seal">U</span>
            <div>
              <strong>University workspace</strong>
              <small>Fall semester · 2026</small>
            </div>
          </div>
          <p className="p-nav-label">YOUR WORKSPACE</p>
          <nav aria-label="Workspace navigation">
            {nav.map(([label, path, icon]) => (
              <NavLink
                key={path}
                to={path}
                end
                onClick={() => setMobile(false)}
              >
                <Icon name={icon} />
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="p-sidebar-bottom">
            <div className="p-preview-note">
              <span className="p-preview-dot" /> Your course workspace
              <p>Courses, materials, and activities</p>
            </div>
            <Link to="/login" className="p-profile">
              <span className="p-avatar">{initials}</span>
              <div>
                <strong>{name}</strong>
                <small>{professor ? "Professor" : "Student"} account</small>
              </div>
              <Icon name="arrow" size={16} />
            </Link>
          </div>
        </aside>
      )}
      <div className="p-main-area">
        <header className="p-topbar">
          {professor && (
            <button
              className="p-menu secondary"
              aria-label="Toggle navigation"
              aria-expanded={mobile}
              onClick={() => setMobile(!mobile)}
            >
              <Icon name="grid" />
            </button>
          )}
          <div className="p-breadcrumb">
            <span>Workspace</span>
            <span>/</span>
            <strong>
              {location.pathname.includes("/activities/new")
                ? "Courses / Create activity"
                : location.pathname.includes("/activities/")
                  ? "Courses / Edit activity"
                  : location.pathname.includes("/activity/") || location.pathname.includes("/assignments/")
                    ? "Assignment details"
                    : location.pathname.includes("sdl")
                ? "Self-Directed Learning"
                : location.pathname.includes("assignments")
                  ? "Assignment workspace"
                  : location.pathname.includes("reflection")
                    ? "Reflections"
                    : location.pathname.includes("documents")
                      ? "Document library"
                      : location.pathname.includes("analytics")
                        ? "Learning insights"
                        : location.pathname.includes("courses")
                          ? "Courses"
                          : location.pathname.includes("settings")
                            ? "Settings"
                            : location.pathname.includes("tools")
                              ? "Teaching toolkit"
                              : "Overview"}
            </strong>
          </div>
          <div className="p-topbar-actions">
            <div className="p-role-switch" aria-label="Preview role">
              <button
                className={!professor ? "active" : ""}
                aria-pressed={!professor}
                onClick={() => choose("student")}
              >
                Student
              </button>
              <button
                className={professor ? "active" : ""}
                aria-pressed={professor}
                onClick={() => choose("professor")}
              >
                Professor
              </button>
            </div>
            <span className="p-term">Fall 2026</span>
            {professor && !session()?.demo_mode ? (
              <span className="p-avatar">{initials}</span>
            ) : (
              <details ref={profileMenu} className="student-profile-menu">
                <summary aria-label={professor ? "Professor account menu" : "Student account menu"} title={name}>
                  <span className="p-avatar">{initials}</span>
                </summary>
                <nav aria-label={professor ? "Professor account navigation" : "Student account navigation"}>
                  <strong>{name}</strong>
                  <Link
                    to={base}
                    onClick={(e) =>
                      e.currentTarget.closest("details").removeAttribute("open")
                    }
                  >
                    <Icon name="grid" size={18} />
                    Overview
                  </Link>
                  <Link
                    to={`${base}/settings`}
                    onClick={(e) =>
                      e.currentTarget.closest("details").removeAttribute("open")
                    }
                  >
                    <Icon name="settings" size={18} />
                    Settings
                  </Link>
                  <button className="studio-text-button" onClick={logout}>
                    {session()?.demo_mode ? "Switch demo profile" : "Sign out"}
                  </button>
                </nav>
              </details>
            )}
          </div>
        </header>
        <main
          id="preview-content"
          className={`p-content ${/^\/student\/(assignments|sdl|reflection)\//.test(location.pathname) ? "student-chat-view" : ""}`}
        >
          {/^\/student\/(assignments|sdl|reflection)\//.test(
            location.pathname,
          ) && (
            <div className="student-back-actions">
              <Link className="button secondary" to="/student">
                ← Back to your assignments
              </Link>
            </div>
          )}
          {switchError && <p role="alert">{switchError}</p>}
          <Routes>
            <Route path="/" element={<Navigate to={base} replace />} />
            {professor ? (
              <>
                <Route path="/professor" element={<InstructorStudio />} />
                <Route
                  path="/professor/courses"
                  element={<Navigate to="/professor" replace />}
                />
                <Route
                  path="/professor/courses/:courseId"
                  element={<InstructorStudio />}
                />
                <Route
                  path="/professor/courses/:courseId/activities/:activityId"
                  element={<ActivityCreationPage />}
                />
                <Route
                  path="/professor/courses/:courseId/assignments/:assignmentId"
                  element={<InstructorAssignmentDetails />}
                />
                <Route
                  path="/professor/documents"
                  element={<CourseDocumentLibrary />}
                />
                <Route path="/professor/analytics" element={<Insights />} />
                <Route path="/professor/people" element={<People />} />
              </>
            ) : (
              <>
                <Route path="/student" element={<StudentOverview />} />
                <Route
                  path="/student/courses/:courseId"
                  element={<StudentCoursePage />}
                />
                <Route
                  path="/student/assignments/:id"
                  element={<ChatRoute type="chat" />}
                />
                <Route
                  path="/student/reflection/:id"
                  element={<ChatRoute type="reflections" />}
                />
                <Route
                  path="/student/sdl/:id"
                  element={<ChatRoute type="sdl" />}
                />
              </>
            )}
            <Route path={`${base}/settings`} element={<Settings />} />
            <Route path="*" element={<Navigate to={base} replace />} />
          </Routes>
          <footer className="p-footer">
            <span>CourseLab · A connected learning experience</span>
            <span>Your connected learning platform</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

function SignedInWorkspace() {
  const [user, setUser] = useState(null);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(true);
  useEffect(() => {
    let active = true;
    const openWorkspace = async () => {
      if (!session()?.access_token) return {};
      return api("/auth/me");
    };
    openWorkspace()
      .then(({ user }) => {
        if (!user) return;
        if (!user.onboarding_complete) {
          window.location.replace("/?manage=1");
          return;
        }
        if (active) setUser(user);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setChecking(false);
      });
    const timer = setInterval(
      () => {
        api("/auth/session/refresh", { method: "POST" })
          .then((data) => {
            localStorage.setItem(
              SESSION_KEY,
              JSON.stringify({
                ...session(),
                access_token: data.access_token,
                expires_at: Date.now() + data.expires_in_seconds * 1000,
              }),
            );
          })
          .catch((e) => {
            if (active) setError(e.message);
          });
      },
      20 * 60 * 1000,
    );
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, []);
  if (!checking && !user && !error) return <SignIn />;
  if (!user)
    return (
      <main className="p-content">
        <h1>CourseLab</h1>
        {error ? (
          <>
            <p role="alert">{error}</p>
            <a href="/">Return to sign in</a>
          </>
        ) : (
          <p role="status">Opening your workspace…</p>
        )}
      </main>
    );
  return (
    <WorkspaceProvider user={user}>
      <Shell />
    </WorkspaceProvider>
  );
}

class WorkspaceErrorBoundary extends React.Component {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <main className="p-content">
        <h1>The workspace could not be opened.</h1>
        <button onClick={() => window.location.reload()}>
          Reload workspace
        </button>
      </main>
    ) : (
      this.props.children
    );
  }
}

export default function WorkspaceRoot() {
  return (
    <WorkspaceErrorBoundary>
      <BrowserRouter basename="/platform">
        <SignedInWorkspace />
      </BrowserRouter>
    </WorkspaceErrorBoundary>
  );
}

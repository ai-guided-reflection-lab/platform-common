const authScreen = document.querySelector("#authScreen");
const onboardingScreen = document.querySelector("#onboardingScreen");
const onboardingForm = document.querySelector("#onboardingForm");
const onboardingIdentity = document.querySelector("#onboardingIdentity");
const onboardingStatus = document.querySelector("#onboardingStatus");
const onboardingLogoutButton = document.querySelector("#onboardingLogoutButton");
const dashboardScreen = document.querySelector("#dashboardScreen");
const dashboardGreeting = document.querySelector("#dashboardGreeting");
const dashboardRoleBadge = document.querySelector("#dashboardRoleBadge");
const dashboardAuthorityLevel = document.querySelector("#dashboardAuthorityLevel");
const dashboardRoleTitle = document.querySelector("#dashboardRoleTitle");
const dashboardRoleDescription = document.querySelector("#dashboardRoleDescription");
const dashboardPendingNotice = document.querySelector("#dashboardPendingNotice");
const dashboardLogoutButton = document.querySelector("#dashboardLogoutButton");
const openWorkspaceButton = document.querySelector("#openWorkspaceButton");
const studentCoursesSection = document.querySelector("#studentCoursesSection");
const studentCoursesList = document.querySelector("#studentCoursesList");
const studentCoursesStatus = document.querySelector("#studentCoursesStatus");
const refreshStudentCoursesButton = document.querySelector("#refreshStudentCoursesButton");
const instructorWorkspaceSection = document.querySelector("#instructorWorkspaceSection");
const courseCreateForm = document.querySelector("#courseCreateForm");
const instructorCoursesList = document.querySelector("#instructorCoursesList");
const instructorCoursesStatus = document.querySelector("#instructorCoursesStatus");
const selectedCoursePanel = document.querySelector("#selectedCoursePanel");
const selectedCourseCode = document.querySelector("#selectedCourseCode");
const selectedCourseTitle = document.querySelector("#selectedCourseTitle");
const previewCourseButton = document.querySelector("#previewCourseButton");
const deleteCourseButton = document.querySelector("#deleteCourseButton");
const courseDocumentForm = document.querySelector("#courseDocumentForm");
const courseDocumentInput = document.querySelector("#courseDocumentInput");
const courseDocumentsList = document.querySelector("#courseDocumentsList");
const courseDocumentsStatus = document.querySelector("#courseDocumentsStatus");
const courseAccessRequestsList = document.querySelector("#courseAccessRequestsList");
const courseAccessRequestsStatus = document.querySelector("#courseAccessRequestsStatus");
const pendingStudentCount = document.querySelector("#pendingStudentCount");
const enrolledStudentsList = document.querySelector("#enrolledStudentsList");
const enrolledStudentsStatus = document.querySelector("#enrolledStudentsStatus");
const enrolledStudentCount = document.querySelector("#enrolledStudentCount");
const adminRequestsSection = document.querySelector("#adminRequestsSection");
const adminRequestsList = document.querySelector("#adminRequestsList");
const adminRequestsStatus = document.querySelector("#adminRequestsStatus");
const appShell = document.querySelector("#appShell");
const loginForm = document.querySelector("#loginForm");
const registerForm = document.querySelector("#registerForm");
const showLoginButton = document.querySelector("#showLoginButton");
const showRegisterButton = document.querySelector("#showRegisterButton");
const authStatus = document.querySelector("#authStatus");
const authCopy = document.querySelector("#authCopy");
const emailAuthDivider = document.querySelector("#emailAuthDivider");
const authTabs = document.querySelector("#authTabs");
const sendEmailCodeButton = document.querySelector("#sendEmailCodeButton");
const verificationCodeField = document.querySelector("#verificationCodeField");
const registerVerificationCode = document.querySelector("#registerVerificationCode");
const googleSignInWrap = document.querySelector("#googleSignInWrap");
const googleSignInButton = document.querySelector("#googleSignInButton");
const githubConnectWrap = document.querySelector("#githubConnectWrap");
const githubConnectMessage = document.querySelector("#githubConnectMessage");
const githubSchoolEmail = document.querySelector("#githubSchoolEmail");
const connectGithubButton = document.querySelector("#connectGithubButton");
const logoutButton = document.querySelector("#logoutButton");
const userIdentity = document.querySelector("#userIdentity");
const userInitial = document.querySelector("#userInitial");
const userName = document.querySelector("#userName");
const userBadge = document.querySelector("#userBadge");
const workspaceRole = document.querySelector("#workspaceRole");
const sessionWarning = document.querySelector("#sessionWarning");
const sessionWarningText = document.querySelector("#sessionWarningText");
const extendSessionButton = document.querySelector("#extendSessionButton");
const sessionLogoutButton = document.querySelector("#sessionLogoutButton");
const messagesEl = document.querySelector("#messages");
const formEl = document.querySelector("#chatForm");
const inputEl = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const composerAttachButton = document.querySelector("#composerAttachButton");
const newChatButton = document.querySelector("#newChatButton");
const dashboardButton = document.querySelector("#dashboardButton");
const scanStatus = document.querySelector("#scanStatus");
const fileInput = document.querySelector("#fileInput");
const attachmentTray = document.querySelector("#attachmentTray");
const chatPanel = document.querySelector("#chatPanel");
const dropOverlay = document.querySelector("#dropOverlay");
const threadList = document.querySelector("#threadList");
const chatFilePanel = document.querySelector("#chatFilePanel");
const themeSelects = [...document.querySelectorAll(".theme-select")];
const themeColorMeta = document.querySelector('meta[name="theme-color"]');
const primarySidebar = document.querySelector("#primarySidebar");
const sidebarToggle = document.querySelector("#sidebarToggle");
const mobileSidebarToggle = document.querySelector("#mobileSidebarToggle");
const sidebarScrim = document.querySelector("#sidebarScrim");
const progressNavButton = document.querySelector("#progressNavButton");
const settingsNavButton = document.querySelector("#settingsNavButton");
const themeToggle = document.querySelector("#themeToggle");
const learningPanel = document.querySelector("#learningPanel");
const learningPanelToggle = document.querySelector("#learningPanelToggle");
const learningPanelClose = document.querySelector("#learningPanelClose");
const currentTopicLabel = document.querySelector("#currentTopicLabel");
const sessionProgressLabel = document.querySelector("#sessionProgressLabel");
const topbarUserInitial = document.querySelector("#topbarUserInitial");
const topbarUserName = document.querySelector("#topbarUserName");
const suggestedResponses = document.querySelector("#suggestedResponses");
const learningObjective = document.querySelector("#learningObjective");
const criticalThinkingStatus = document.querySelector("#criticalThinkingStatus");
const questionTypeTrail = document.querySelector("#questionTypeTrail");
const conceptsDiscussed = document.querySelector("#conceptsDiscussed");
const assumptionsIdentified = document.querySelector("#assumptionsIdentified");
const evidenceUsed = document.querySelector("#evidenceUsed");
const alternativeViewpoints = document.querySelector("#alternativeViewpoints");
const bookmarkCount = document.querySelector("#bookmarkCount");
const bookmarkList = document.querySelector("#bookmarkList");
const reflectionSummary = document.querySelector("#reflectionSummary");
const reflectionButton = document.querySelector("#reflectionButton");

const API_BASE_URL = (window.SOCRATIC_CONFIG?.API_BASE_URL || "").replace(/\/+$/, "");

function apiUrl(path) {
  if (/^https?:\/\//i.test(path)) return path;
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

const CONVERSATION_KEY = "my_rag_chatbot_conversation_id";
const AUTH_USER_KEY = "my_rag_chatbot_user";
const THEME_KEY = "socratic_chat_theme";
const ACTIVE_COURSE_KEY = "socratic_chat_active_course";
const SIDEBAR_STATE_KEY = "socratic_chat_sidebar_collapsed";
const LEARNING_PANEL_STATE_KEY = "socratic_chat_learning_panel_open";
const BOOKMARKS_KEY = "socratic_chat_question_bookmarks";
const AUTH_SESSION_MS = 60 * 60 * 1000;
const SESSION_WARNING_MS = 5 * 60 * 1000;
const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
let renderGoogleSignInButton = null;
let currentUser = readStoredUser();
let conversationId = localStorage.getItem(CONVERSATION_KEY) || createConversationId();
localStorage.setItem(CONVERSATION_KEY, conversationId);
let emailVerificationRequired = true;
let authMode = "open";
let registrationEnabled = true;
let githubAccountRequired = false;
let githubOauthConfigured = false;
let courses = [];
let selectedInstructorCourse = null;
let activeCourse = null;
let isInstructorPreview = false;

const history = [];
const pendingFiles = [];
const messageRecords = [];
let questionTypesSeen = new Set();
let questionBookmarks = readQuestionBookmarks();


function getThemePreference() {
  const storedTheme = localStorage.getItem(THEME_KEY);
  return ["light", "dark", "system"].includes(storedTheme) ? storedTheme : "light";
}

function applyTheme(preference, persist = true) {
  const safePreference = ["light", "dark", "system"].includes(preference) ? preference : "light";
  const resolvedTheme = safePreference === "system"
    ? (systemTheme.matches ? "dark" : "light")
    : safePreference;

  document.documentElement.dataset.theme = resolvedTheme;
  document.documentElement.dataset.themePreference = safePreference;
  themeSelects.forEach((select) => {
    select.value = safePreference;
  });
  if (themeColorMeta) {
    themeColorMeta.content = resolvedTheme === "dark" ? "#0b1020" : "#f4f6fb";
  }
  if (themeToggle) {
    themeToggle.textContent = resolvedTheme === "dark" ? "☀" : "◐";
    themeToggle.setAttribute("aria-label", resolvedTheme === "dark" ? "Switch to light mode" : "Switch to dark mode");
    themeToggle.title = resolvedTheme === "dark" ? "Switch to light mode" : "Switch to dark mode";
  }
  if (persist) localStorage.setItem(THEME_KEY, safePreference);
  renderGoogleSignInButton?.();
}

themeSelects.forEach((select) => {
  select.addEventListener("change", () => applyTheme(select.value));
});
systemTheme.addEventListener("change", () => {
  if (getThemePreference() === "system") applyTheme("system", false);
});
applyTheme(getThemePreference(), false);

themeToggle?.addEventListener("click", () => {
  const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(nextTheme);
});


function readQuestionBookmarks() {
  try {
    const stored = JSON.parse(localStorage.getItem(BOOKMARKS_KEY) || "[]");
    return Array.isArray(stored) ? stored : [];
  } catch {
    return [];
  }
}

function persistQuestionBookmarks() {
  localStorage.setItem(BOOKMARKS_KEY, JSON.stringify(questionBookmarks));
}

function formatClock(date = new Date()) {
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(date);
}

function inferQuestionType(content) {
  const text = String(content || "").toLowerCase();
  if (/\b(?:reflect|understanding changed|would you revise|first response)\b/.test(text)) return "Reflection";
  if (/\b(?:synthesi|combine|bring together|overall explanation)\b/.test(text)) return "Synthesis";
  if (/\b(?:apply|application|new example|new domain|library system)\b/.test(text)) return "Application";
  if (/\b(?:compare|comparison|difference|distinction)\b/.test(text)) return "Comparison";
  if (/\b(?:evidence|support|source|detail|according|how do you know)\b/.test(text)) return "Evidence";
  if (/\b(?:assum|belie|thought|taking for granted)\b/.test(text)) return "Assumption";
  if (/\b(?:impact|implication|consequence|what happens|lead to|affect)\b/.test(text)) return "Implication";
  if (/\b(?:alternative|another|different perspective|other viewpoint|instead)\b/.test(text)) return "Alternative viewpoint";
  return "Clarification";
}

function questionTypeExplanation(type) {
  const explanations = {
    Clarification: "This question helps make the idea precise before the conversation moves deeper.",
    Assumption: "This question surfaces an underlying belief that may be shaping your conclusion.",
    Evidence: "This question asks you to connect your claim to support from the course material.",
    Implication: "This question explores what follows from the idea and why the consequence matters.",
    "Alternative viewpoint": "This question invites another perspective so you can compare possibilities.",
    Synthesis: "This question asks you to combine concepts and evidence into a coherent explanation.",
    Reflection: "This question helps you notice how your understanding changed during the conversation.",
    Application: "This question asks you to transfer the concept to a different situation.",
    Comparison: "This question helps distinguish related ideas by examining how they differ.",
  };
  return explanations[type] || explanations.Clarification;
}

function truncateInsight(text, limit = 110) {
  const clean = String(text || "").replace(/\s+/g, " ").trim();
  return clean.length > limit ? `${clean.slice(0, limit - 1).trim()}…` : clean;
}

function extractConceptPhrase(text) {
  const clean = String(text || "").replace(/\s+/g, " ").trim().replace(/[?.!]+$/, "");
  const match = clean.match(/^(?:what (?:is|are)|define|explain|tell me about|help me understand)\s+(.+)$/i);
  if (!match) return "";
  const concept = match[1].split(/\s+(?:in|from|according to)\s+(?:the|this|our)\b/i)[0].trim();
  return concept.split(" ").slice(0, 7).join(" ");
}


function getDisplayName(user = currentUser) {
  const preferredName = user?.display_name || user?.username || user?.email?.split("@", 1)[0];
  return String(preferredName || "Student").trim();
}

function getRole(user = currentUser) {
  const level = Number(user?.authority_level ?? 2);
  if (level === 0) return "admin";
  if (level === 1) return "instructor";
  return "student";
}

function getRoleLabel(user = currentUser) {
  const role = getRole(user);
  return role.charAt(0).toUpperCase() + role.slice(1);
}

function canManageCourseMaterials(user = currentUser) {
  return Boolean(user?.onboarding_complete) && Number(user?.authority_level ?? 2) <= 1;
}

function setSidebarCollapsed(collapsed) {
  appShell?.classList.toggle("sidebar-collapsed", collapsed);
  sidebarToggle?.setAttribute("aria-expanded", String(!collapsed));
  sidebarToggle?.setAttribute("aria-label", collapsed ? "Expand navigation" : "Collapse navigation");
  sidebarToggle?.setAttribute("title", collapsed ? "Expand navigation" : "Collapse navigation");
  const glyph = sidebarToggle?.querySelector("span");
  if (glyph) glyph.textContent = collapsed ? "›" : "‹";
  localStorage.setItem(SIDEBAR_STATE_KEY, String(collapsed));
}

function setMobileSidebar(open) {
  appShell?.classList.toggle("sidebar-open", open);
  mobileSidebarToggle?.setAttribute("aria-expanded", String(open));
  if (primarySidebar) {
    primarySidebar.inert = window.matchMedia("(max-width: 780px)").matches && !open;
  }
}

function setLearningPanelOpen(open) {
  appShell?.classList.toggle("learning-panel-closed", !open);
  learningPanelToggle?.setAttribute("aria-expanded", String(open));
  learningPanel?.setAttribute("aria-hidden", String(!open));
  if (learningPanel) learningPanel.inert = !open;
  localStorage.setItem(LEARNING_PANEL_STATE_KEY, String(open));
}

function applyWorkspaceChrome() {
  const sidebarCollapsed = localStorage.getItem(SIDEBAR_STATE_KEY) === "true";
  const compactLayout = window.matchMedia("(max-width: 1120px)").matches;
  const panelOpen = !compactLayout && localStorage.getItem(LEARNING_PANEL_STATE_KEY) !== "false";
  setSidebarCollapsed(sidebarCollapsed);
  setMobileSidebar(false);
  setLearningPanelOpen(panelOpen);
}


function formatSessionTime(milliseconds) {
  const safeMilliseconds = Math.max(0, milliseconds);
  const totalSeconds = Math.ceil(safeMilliseconds / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    const restMinutes = minutes % 60;
    return `${hours}h ${restMinutes}m`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function persistCurrentUser() {
  if (currentUser) {
    localStorage.setItem(AUTH_USER_KEY, JSON.stringify(currentUser));
  }
}

async function extendSession() {
  if (!currentUser) return;
  const data = await postJson("/api/auth/session/refresh");
  currentUser.access_token = data.access_token;
  currentUser.expires_at = Date.now() + (data.expires_in_seconds * 1000);
  persistCurrentUser();
  updateSessionStatus();
}

function updateSessionStatus() {
  if (!sessionWarning) return;

  if (!currentUser) {
    if (userIdentity) userIdentity.classList.add("is-hidden");
    if (userName) userName.textContent = "";
    if (userInitial) userInitial.textContent = "";
    userBadge.textContent = "";
    if (workspaceRole) workspaceRole.textContent = "";
    sessionWarning.classList.remove("is-visible");
    sessionWarning.hidden = true;
    return;
  }

  const remaining = currentUser.expires_at - Date.now();
  const shouldWarn = remaining > 0 && remaining <= SESSION_WARNING_MS;
  const displayName = getDisplayName();
  if (userIdentity) userIdentity.classList.remove("is-hidden");
  if (userName) userName.textContent = displayName;
  if (userInitial) userInitial.textContent = displayName.charAt(0).toUpperCase();
  if (topbarUserName) topbarUserName.textContent = displayName;
  if (topbarUserInitial) topbarUserInitial.textContent = displayName.charAt(0).toUpperCase();
  userBadge.textContent = `${currentUser.email || "Signed in"} · ${formatSessionTime(remaining)} left`;
  if (workspaceRole) {
    workspaceRole.textContent = activeCourse
      ? (isInstructorPreview
        ? `Instructor preview · ${activeCourse.course_code}`
        : `Student · ${activeCourse.course_code}`)
      : `${getRoleLabel()} · Authority ${currentUser.authority_level ?? 2}`;
  }
  userBadge.classList.toggle("is-warning", shouldWarn);

  sessionWarning.hidden = !shouldWarn;
  sessionWarning.classList.toggle("is-visible", shouldWarn);
  if (sessionWarningText) {
    sessionWarningText.textContent = `${formatSessionTime(remaining)} left. Do you need more time?`;
  }
}

function readStoredUser() {
  try {
    const storedUser = JSON.parse(localStorage.getItem(AUTH_USER_KEY) || "null");
    if (!storedUser) return null;
    if (isSessionExpired(storedUser)) {
      localStorage.removeItem(AUTH_USER_KEY);
      localStorage.removeItem(CONVERSATION_KEY);
      return null;
    }
    return storedUser;
  } catch {
    return null;
  }
}

function isSessionExpired(user = currentUser) {
  return !user?.expires_at || Date.now() > user.expires_at;
}

function expireSession(message = "Session expired. Please login again.") {
  localStorage.removeItem(AUTH_USER_KEY);
  localStorage.removeItem(CONVERSATION_KEY);
  currentUser = null;
  activeCourse = null;
  selectedInstructorCourse = null;
  isInstructorPreview = false;
  conversationId = createConversationId();
  localStorage.setItem(CONVERSATION_KEY, conversationId);
  clearMessages();
  clearPendingFiles();
  showSignedOut();
  authStatus.textContent = message;
}

function requireActiveSession() {
  if (!currentUser) {
    showSignedOut();
    authStatus.textContent = "Please login first.";
    return false;
  }

  if (isSessionExpired()) {
    expireSession();
    return false;
  }

  return true;
}

function setAuthMode(mode) {
  if (authMode === "unavailable") {
    loginForm.classList.add("is-hidden");
    registerForm.classList.add("is-hidden");
    showLoginButton.classList.remove("is-active");
    showRegisterButton.classList.remove("is-active");
    return;
  }
  const isLogin = mode === "login" || !registrationEnabled;
  loginForm.classList.toggle("is-hidden", !isLogin);
  registerForm.classList.toggle("is-hidden", isLogin);
  showLoginButton.classList.toggle("is-active", isLogin);
  showRegisterButton.classList.toggle("is-active", !isLogin);
  authStatus.textContent = "";
}

function showAuthenticatedApp() {
  authScreen.classList.add("is-hidden");
  onboardingScreen?.classList.add("is-hidden");
  dashboardScreen?.classList.add("is-hidden");
  appShell.classList.remove("is-hidden");
  appShell.dataset.role = "student";
  applyWorkspaceChrome();
  inputEl.placeholder = activeCourse
    ? `Share what you are thinking about ${activeCourse.course_code}…`
    : "Choose an approved course from the dashboard";
  if (currentTopicLabel) {
    currentTopicLabel.textContent = activeCourse
      ? `${activeCourse.course_code} · ${activeCourse.title}`
      : "Guided exploration";
  }
  if (learningObjective) {
    learningObjective.textContent = activeCourse
      ? `Explore ${activeCourse.title} through evidence, assumptions, and guided questions.`
      : "Choose a course to begin a guided exploration.";
  }
  updateSessionStatus();
  if (workspaceRole && activeCourse) {
    workspaceRole.textContent = isInstructorPreview
      ? `Instructor preview · ${activeCourse.course_code}`
      : `Student · ${activeCourse.course_code}`;
  }
}

function showOnboarding() {
  authScreen.classList.add("is-hidden");
  dashboardScreen?.classList.add("is-hidden");
  appShell.classList.add("is-hidden");
  onboardingScreen?.classList.remove("is-hidden");
  if (onboardingIdentity) {
    onboardingIdentity.textContent = `Verified school account: ${currentUser?.email || "UNC Charlotte account"}`;
  }
  const usernameInput = document.querySelector("#onboardingUsername");
  if (usernameInput && !usernameInput.value) usernameInput.value = currentUser?.username || "";
  onboardingStatus.textContent = "";
  usernameInput?.focus();
}

function renderDashboard() {
  const role = getRole();
  const isPending = currentUser?.role_status === "pending";
  dashboardGreeting.textContent = `Welcome, ${getDisplayName()}`;
  dashboardRoleBadge.textContent = getRoleLabel();
  dashboardAuthorityLevel.textContent = `Authority level ${currentUser?.authority_level ?? 2}`;
  dashboardPendingNotice.classList.toggle("is-hidden", !isPending);
  dashboardPendingNotice.textContent = isPending
    ? "Your instructor request is waiting for administrator approval. You currently have student access."
    : "";

  const copy = {
    admin: {
      title: "Administration and course management",
      description: "Review instructor requests and manage courses without entering the student chatbot.",
    },
    instructor: {
      title: "Instructor course management",
      description: "Create courses, publish materials, and approve student access requests.",
    },
    student: {
      title: "Student learning workspace",
      description: "Ask questions, review course concepts, and continue your saved conversations.",
    },
  };
  dashboardRoleTitle.textContent = copy[role].title;
  dashboardRoleDescription.textContent = copy[role].description;
  openWorkspaceButton.textContent = role === "student" ? "View available classes" : "Manage my courses";
  studentCoursesSection?.classList.toggle("is-hidden", role !== "student");
  instructorWorkspaceSection?.classList.toggle("is-hidden", role === "student");
  adminRequestsSection.classList.toggle("is-hidden", role !== "admin");
  if (role === "admin") loadInstructorRequests();
  loadCourses();
}

function showDashboard() {
  authScreen.classList.add("is-hidden");
  onboardingScreen?.classList.add("is-hidden");
  appShell.classList.add("is-hidden");
  dashboardScreen?.classList.remove("is-hidden");
  renderDashboard();
  updateSessionStatus();
}

function courseConversationKey(courseId) {
  const userScope = currentUser?.user_id || "anonymous";
  return `${CONVERSATION_KEY}:${userScope}:${courseId}`;
}

function emptyState(message) {
  const empty = document.createElement("div");
  empty.className = "course-empty";
  empty.textContent = message;
  return empty;
}

function courseBadge(status) {
  const badge = document.createElement("span");
  badge.className = `membership-badge ${status || "available"}`;
  badge.textContent = status ? status.charAt(0).toUpperCase() + status.slice(1) : "Available";
  return badge;
}

function courseCard(course, instructorView = false) {
  const card = document.createElement("article");
  card.className = "course-card";
  if (selectedInstructorCourse?.course_id === course.course_id) card.classList.add("is-selected");

  const topline = document.createElement("div");
  topline.className = "course-card-topline";
  const code = document.createElement("span");
  code.className = "course-code";
  code.textContent = course.course_code;
  topline.append(code, courseBadge(instructorView ? "approved" : course.membership_status));

  const title = document.createElement("h3");
  title.textContent = course.title;
  const description = document.createElement("p");
  description.textContent = course.description || "No course description has been added yet.";
  const meta = document.createElement("div");
  meta.className = "course-meta";
  meta.textContent = instructorView
    ? `${course.document_count} document(s) · ${course.pending_request_count} pending request(s)`
    : `Instructor: ${course.instructor_name} · ${course.document_count} document(s)`;

  const actions = document.createElement("div");
  actions.className = "course-card-actions";
  const action = document.createElement("button");
  action.type = "button";

  if (instructorView) {
    action.textContent = "Manage course";
    action.addEventListener("click", () => selectInstructorCourse(course));
  } else if (course.membership_status === "approved") {
    action.textContent = "Open chatbot";
    action.addEventListener("click", () => openCourseChat(course, false));
  } else if (course.membership_status === "pending") {
    action.textContent = "Waiting for approval";
    action.disabled = true;
  } else {
    action.textContent = course.membership_status === "rejected" ? "Request again" : "Request access";
    action.addEventListener("click", () => requestCoursePermission(course, action));
  }

  actions.appendChild(action);
  card.append(topline, title, description, meta, actions);
  return card;
}

function renderStudentCourses() {
  if (!studentCoursesList) return;
  studentCoursesList.replaceChildren();
  if (!courses.length) {
    studentCoursesList.appendChild(emptyState("No discoverable classes are available yet."));
    return;
  }
  courses.forEach((course) => studentCoursesList.appendChild(courseCard(course)));
}

function renderInstructorCourses() {
  if (!instructorCoursesList) return;
  const managedCourses = courses.filter(
    (course) => course.membership_role === "instructor" && course.membership_status === "approved",
  );
  instructorCoursesList.replaceChildren();
  if (!managedCourses.length) {
    instructorCoursesList.appendChild(emptyState("Create your first course to upload materials and invite students."));
    selectedCoursePanel?.classList.add("is-hidden");
    selectedInstructorCourse = null;
    return;
  }
  managedCourses.forEach((course) => instructorCoursesList.appendChild(courseCard(course, true)));
}

async function loadCourses() {
  const role = getRole();
  const status = role === "student" ? studentCoursesStatus : instructorCoursesStatus;
  if (status) status.textContent = "Loading courses...";
  try {
    const data = await getJson("/api/courses");
    courses = data.courses || [];
    if (role === "student") renderStudentCourses();
    else renderInstructorCourses();
    if (selectedInstructorCourse) {
      const refreshed = courses.find((course) => course.course_id === selectedInstructorCourse.course_id);
      if (refreshed) {
        selectedInstructorCourse = refreshed;
      } else {
        selectedInstructorCourse = null;
        selectedCoursePanel?.classList.add("is-hidden");
      }
    }
    if (status) status.textContent = "";
  } catch (error) {
    if (status) status.textContent = `Could not load courses: ${error.message}`;
  }
}

async function requestCoursePermission(course, button) {
  if (!requireActiveSession()) return;
  button.disabled = true;
  studentCoursesStatus.textContent = `Sending your request for ${course.course_code}...`;
  try {
    const data = await postJson(`/api/courses/${encodeURIComponent(course.course_id)}/request-access`);
    studentCoursesStatus.textContent = data.message;
    await loadCourses();
  } catch (error) {
    button.disabled = false;
    studentCoursesStatus.textContent = `Request failed: ${error.message}`;
  }
}

async function selectInstructorCourse(course) {
  selectedInstructorCourse = course;
  selectedCoursePanel?.classList.remove("is-hidden");
  selectedCourseCode.textContent = course.course_code;
  selectedCourseTitle.textContent = course.title;
  renderInstructorCourses();
  await Promise.all([loadCourseDocuments(), loadCourseAccessRequests(), loadEnrolledStudents()]);
  selectedCoursePanel?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function deleteSelectedCourse() {
  if (!requireActiveSession() || !selectedInstructorCourse) return;
  const course = selectedInstructorCourse;
  const confirmed = confirm(
    `Permanently delete ${course.course_code}: ${course.title}?\n\n`
      + "This removes its documents, conversations, student access, and learning progress. This cannot be undone.",
  );
  if (!confirmed) return;

  deleteCourseButton.disabled = true;
  instructorCoursesStatus.textContent = `Deleting ${course.course_code}...`;
  try {
    const result = await deleteJson(`/api/courses/${encodeURIComponent(course.course_id)}`);
    localStorage.removeItem(courseConversationKey(course.course_id));
    if (activeCourse?.course_id === course.course_id) {
      activeCourse = null;
      localStorage.removeItem(ACTIVE_COURSE_KEY);
      localStorage.removeItem(CONVERSATION_KEY);
    }
    selectedInstructorCourse = null;
    selectedCoursePanel?.classList.add("is-hidden");
    await loadCourses();
    instructorCoursesStatus.textContent = result.message;
  } catch (error) {
    instructorCoursesStatus.textContent = `Could not delete course: ${error.message}`;
  } finally {
    deleteCourseButton.disabled = false;
  }
}

function renderCourseDocuments(files = []) {
  courseDocumentsList.replaceChildren();
  if (!files.length) {
    courseDocumentsList.appendChild(emptyState("No documents have been published for this course."));
    return;
  }
  files.forEach((file) => {
    const row = document.createElement("div");
    row.className = "management-list-row";
    const info = document.createElement("div");
    const name = document.createElement("div");
    name.className = "management-list-primary";
    name.textContent = file.filename;
    const meta = document.createElement("div");
    meta.className = "management-list-secondary";
    meta.textContent = `${formatFileSize(file.file_size)} · Published`;
    info.append(name, meta);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "delete-button";
    remove.textContent = "Delete";
    remove.addEventListener("click", () => removeCourseDocument(file, remove));
    row.append(info, remove);
    courseDocumentsList.appendChild(row);
  });
}

async function loadCourseDocuments() {
  if (!selectedInstructorCourse) return;
  courseDocumentsStatus.textContent = "Loading documents...";
  try {
    const data = await getJson(`/api/courses/${encodeURIComponent(selectedInstructorCourse.course_id)}/documents`);
    renderCourseDocuments(data.files || []);
    courseDocumentsStatus.textContent = "";
  } catch (error) {
    courseDocumentsStatus.textContent = `Could not load documents: ${error.message}`;
  }
}

async function removeCourseDocument(file, button) {
  if (!selectedInstructorCourse) return;
  if (!confirm(`Delete ${file.filename} from this course?`)) return;
  button.disabled = true;
  courseDocumentsStatus.textContent = `Deleting ${file.filename}...`;
  try {
    await deleteJson(
      `/api/courses/${encodeURIComponent(selectedInstructorCourse.course_id)}/documents/${encodeURIComponent(file.file_id)}`,
    );
    courseDocumentsStatus.textContent = `${file.filename} was deleted.`;
    await Promise.all([loadCourseDocuments(), loadCourses()]);
  } catch (error) {
    button.disabled = false;
    courseDocumentsStatus.textContent = `Delete failed: ${error.message}`;
  }
}

function renderCourseAccessRequests(requests = []) {
  courseAccessRequestsList.replaceChildren();
  pendingStudentCount.textContent = String(requests.length);
  if (!requests.length) {
    courseAccessRequestsList.appendChild(emptyState("No students are waiting for access."));
    return;
  }

  requests.forEach((membership) => {
    const row = document.createElement("div");
    row.className = "management-list-row";
    const info = document.createElement("div");
    const name = document.createElement("div");
    name.className = "management-list-primary";
    name.textContent = membership.display_name;
    const email = document.createElement("div");
    email.className = "management-list-secondary";
    email.textContent = membership.email;
    info.append(name, email);

    const actions = document.createElement("div");
    actions.className = "management-list-actions";
    const approve = document.createElement("button");
    approve.type = "button";
    approve.textContent = "Approve";
    const reject = document.createElement("button");
    reject.type = "button";
    reject.className = "reject-button";
    reject.textContent = "Reject";
    approve.addEventListener("click", () => reviewCoursePermission(membership, "approved", approve, reject));
    reject.addEventListener("click", () => reviewCoursePermission(membership, "rejected", approve, reject));
    actions.append(approve, reject);
    row.append(info, actions);
    courseAccessRequestsList.appendChild(row);
  });
}

async function loadCourseAccessRequests() {
  if (!selectedInstructorCourse) return;
  courseAccessRequestsStatus.textContent = "Loading requests...";
  try {
    const requests = await getJson(
      `/api/instructor/access-requests?course_id=${encodeURIComponent(selectedInstructorCourse.course_id)}`,
    );
    renderCourseAccessRequests(requests || []);
    courseAccessRequestsStatus.textContent = "";
  } catch (error) {
    courseAccessRequestsStatus.textContent = `Could not load requests: ${error.message}`;
  }
}

async function reviewCoursePermission(membership, decision, ...buttons) {
  buttons.forEach((button) => { button.disabled = true; });
  courseAccessRequestsStatus.textContent = `${decision === "approved" ? "Approving" : "Rejecting"} ${membership.email}...`;
  try {
    await postJson(`/api/instructor/access-requests/${encodeURIComponent(membership.membership_id)}/review`, {
      decision,
    });
    await Promise.all([loadCourseAccessRequests(), loadEnrolledStudents(), loadCourses()]);
  } catch (error) {
    buttons.forEach((button) => { button.disabled = false; });
    courseAccessRequestsStatus.textContent = `Review failed: ${error.message}`;
  }
}

function renderEnrolledStudents(students = []) {
  enrolledStudentsList.replaceChildren();
  enrolledStudentCount.textContent = String(students.length);
  if (!students.length) {
    enrolledStudentsList.appendChild(emptyState("No students currently have access to this course."));
    return;
  }

  students.forEach((membership) => {
    const row = document.createElement("div");
    row.className = "management-list-row";
    const info = document.createElement("div");
    const name = document.createElement("div");
    name.className = "management-list-primary";
    name.textContent = membership.display_name;
    const email = document.createElement("div");
    email.className = "management-list-secondary";
    email.textContent = membership.email;
    info.append(name, email);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "delete-button";
    remove.textContent = "Remove access";
    remove.addEventListener("click", () => removeEnrolledStudent(membership, remove));
    row.append(info, remove);
    enrolledStudentsList.appendChild(row);
  });
}

async function loadEnrolledStudents() {
  if (!selectedInstructorCourse) return;
  enrolledStudentsStatus.textContent = "Loading enrolled students...";
  try {
    const students = await getJson(
      `/api/instructor/enrolled-students?course_id=${encodeURIComponent(selectedInstructorCourse.course_id)}`,
    );
    renderEnrolledStudents(students || []);
    enrolledStudentsStatus.textContent = "";
  } catch (error) {
    enrolledStudentsStatus.textContent = `Could not load enrolled students: ${error.message}`;
  }
}

async function removeEnrolledStudent(membership, button) {
  if (!selectedInstructorCourse) return;
  const confirmed = confirm(
    `Remove ${membership.display_name} from ${selectedInstructorCourse.course_code}? `
      + "The student will lose course access and can request it again later.",
  );
  if (!confirmed) return;

  button.disabled = true;
  enrolledStudentsStatus.textContent = `Removing ${membership.email}...`;
  try {
    await deleteJson(`/api/instructor/enrolled-students/${encodeURIComponent(membership.membership_id)}`);
    enrolledStudentsStatus.textContent = `${membership.display_name} no longer has access to this course.`;
    await Promise.all([loadEnrolledStudents(), loadCourses()]);
  } catch (error) {
    button.disabled = false;
    enrolledStudentsStatus.textContent = `Could not remove student: ${error.message}`;
  }
}

async function openCourseChat(course, preview = false) {
  if (!requireActiveSession()) return;
  activeCourse = course;
  isInstructorPreview = preview;
  localStorage.setItem(ACTIVE_COURSE_KEY, course.course_id);
  conversationId = localStorage.getItem(courseConversationKey(course.course_id)) || createConversationId();
  localStorage.setItem(courseConversationKey(course.course_id), conversationId);
  localStorage.setItem(CONVERSATION_KEY, conversationId);
  await openChatWorkspace();
}

function showGithubConnection() {
  appShell.classList.add("is-hidden");
  onboardingScreen?.classList.add("is-hidden");
  dashboardScreen?.classList.add("is-hidden");
  authScreen.classList.remove("is-hidden");
  authScreen.classList.add("is-github-linking");
  googleSignInWrap?.classList.add("is-hidden");
  githubConnectWrap?.classList.remove("is-hidden");
  authStatus.textContent = "";
  if (authCopy) authCopy.textContent = "Step 2 of 2: connect the GitHub account you want linked to this school account.";
  if (githubConnectMessage) {
    githubConnectMessage.textContent = githubOauthConfigured
      ? "Your school identity is verified. Link the GitHub account you want to use with Socratic-Chat."
      : "GitHub authentication is not configured on the server yet.";
  }
  if (githubSchoolEmail) {
    githubSchoolEmail.textContent = currentUser?.email || "Verified charlotte.edu account";
  }
  if (connectGithubButton) connectGithubButton.disabled = !githubOauthConfigured;
}

function routeAuthenticatedUser() {
  githubConnectWrap?.classList.add("is-hidden");
  if (!currentUser?.onboarding_complete) {
    showOnboarding();
    return "onboarding";
  }
  if (githubAccountRequired && !currentUser?.github_connected) {
    showGithubConnection();
    return "github";
  }
  showDashboard();
  return "dashboard";
}

function showSignedOut() {
  appShell.classList.add("is-hidden");
  onboardingScreen?.classList.add("is-hidden");
  dashboardScreen?.classList.add("is-hidden");
  authScreen.classList.remove("is-hidden");
  authScreen.classList.remove("is-github-linking");
  authStatus.textContent = "";
  githubConnectWrap?.classList.add("is-hidden");
  googleSignInWrap?.classList.remove("is-hidden");
  updateSessionStatus();
  setAuthMode("login");
}

function saveUser(user, accessToken, expiresInSeconds = AUTH_SESSION_MS / 1000) {
  currentUser = {
    ...user,
    access_token: accessToken,
    expires_at: Date.now() + (expiresInSeconds * 1000),
  };
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(currentUser));
}

function authHeaders(headers = {}) {
  const nextHeaders = { ...headers };
  if (currentUser?.access_token) {
    nextHeaders.Authorization = `Bearer ${currentUser.access_token}`;
  } else if (currentUser?.user_id) {
    nextHeaders["X-User-Id"] = currentUser.user_id;
  }
  return nextHeaders;
}

function createConversationId() {
  return crypto.randomUUID();
}

function clearMessages() {
  messagesEl.replaceChildren();
  history.length = 0;
  messageRecords.length = 0;
  questionTypesSeen = new Set();
  renderSuggestedResponses();
  updateLearningPanel();
}

function showWelcome() {
  messagesEl.replaceChildren();
  const emptyState = document.createElement("section");
  emptyState.className = "conversation-empty";

  const visual = document.createElement("div");
  visual.className = "empty-orbit";
  visual.setAttribute("aria-hidden", "true");
  visual.innerHTML = "<span></span><span></span><strong>?</strong>";

  const eyebrow = document.createElement("span");
  eyebrow.className = "empty-eyebrow";
  eyebrow.textContent = activeCourse?.course_code || "Socratic learning";

  const title = document.createElement("h2");
  title.textContent = "Let’s examine an idea together.";

  const copy = document.createElement("p");
  copy.textContent = isInstructorPreview
    ? "Preview how the tutor guides students through your published course material with focused questions."
    : "Your tutor will help you clarify assumptions, examine evidence, and build an answer—without immediately giving it away.";

  const starters = document.createElement("div");
  starters.className = "starter-grid";
  const prompts = [
    ["Clarify a concept", "What concept from this course should we examine first?"],
    ["Test an assumption", "Help me examine an assumption in software engineering."],
    ["Follow the evidence", "How can I evaluate evidence for a technical decision?"],
  ];
  prompts.forEach(([label, prompt]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "starter-card";
    button.innerHTML = `<span>${label}</span><small>${prompt}</small><b aria-hidden="true">→</b>`;
    button.addEventListener("click", () => {
      inputEl.value = prompt;
      resizeComposer();
      inputEl.focus();
    });
    starters.appendChild(button);
  });

  emptyState.append(visual, eyebrow, title, copy, starters);
  messagesEl.appendChild(emptyState);
  updateLearningPanel();
}

function renderSuggestedResponses(content = "") {
  if (!suggestedResponses) return;
  suggestedResponses.replaceChildren();
  if (!String(content).trim().endsWith("?")) return;

  ["I’m not sure yet", "My reasoning is…", "Could you guide me?"].forEach((suggestion) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "suggestion-chip";
    button.textContent = suggestion;
    button.addEventListener("click", () => {
      inputEl.value = suggestion;
      resizeComposer();
      inputEl.focus();
    });
    suggestedResponses.appendChild(button);
  });
}

function renderInsightList(container, items, emptyText) {
  if (!container) return;
  container.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("span");
    empty.className = "empty-insight";
    empty.textContent = emptyText;
    container.appendChild(empty);
    return;
  }
  items.slice(-3).forEach((item) => {
    const row = document.createElement("span");
    row.className = "insight-item";
    row.textContent = truncateInsight(item);
    container.appendChild(row);
  });
}

function renderBookmarks() {
  if (!bookmarkList || !bookmarkCount) return;
  const courseBookmarks = questionBookmarks.filter((item) => !activeCourse || item.course_id === activeCourse.course_id);
  bookmarkCount.textContent = String(courseBookmarks.length);
  bookmarkList.replaceChildren();
  if (!courseBookmarks.length) {
    const empty = document.createElement("span");
    empty.className = "empty-insight";
    empty.textContent = "Bookmark a tutor question to revisit it.";
    bookmarkList.appendChild(empty);
    return;
  }
  courseBookmarks.slice(-4).reverse().forEach((bookmark) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "bookmark-item";
    button.textContent = truncateInsight(bookmark.content, 90);
    button.addEventListener("click", () => {
      inputEl.value = `I want to revisit this question: ${bookmark.content}`;
      resizeComposer();
      inputEl.focus();
    });
    bookmarkList.appendChild(button);
  });
}

function updateLearningPanel() {
  const userRecords = messageRecords.filter((record) => record.role === "user");
  const tutorQuestions = messageRecords.filter((record) => record.role === "assistant" && record.isQuestion);
  const concepts = [...new Set(userRecords.map((record) => extractConceptPhrase(record.content)).filter(Boolean))];
  const assumptions = userRecords.filter((record) => /\b(?:assum|i thought|i believe|i think)\b/i.test(record.content)).map((record) => record.content);
  const evidence = userRecords.filter((record) => /\b(?:because|evidence|source|according|supports?)\b/i.test(record.content)).map((record) => record.content);
  const alternatives = userRecords.filter((record) => /\b(?:alternative|another|instead|on the other hand|different)\b/i.test(record.content)).map((record) => record.content);

  if (sessionProgressLabel) {
    sessionProgressLabel.textContent = userRecords.length
      ? `${userRecords.length} reflection${userRecords.length === 1 ? "" : "s"} · exploring`
      : "Ready to explore";
  }
  if (criticalThinkingStatus) {
    criticalThinkingStatus.textContent = tutorQuestions.length
      ? `${tutorQuestions.length} guided question${tutorQuestions.length === 1 ? "" : "s"}`
      : "Not started";
  }

  if (questionTypeTrail) {
    questionTypeTrail.replaceChildren();
    if (!questionTypesSeen.size) {
      const empty = document.createElement("span");
      empty.className = "empty-insight";
      empty.textContent = "Question types will appear here as you explore.";
      questionTypeTrail.appendChild(empty);
    } else {
      [...questionTypesSeen].forEach((type) => {
        const chip = document.createElement("span");
        chip.className = "question-trail-chip";
        chip.textContent = type;
        questionTypeTrail.appendChild(chip);
      });
    }
  }

  renderInsightList(conceptsDiscussed, concepts, "Concepts will appear as you ask focused questions.");
  renderInsightList(assumptionsIdentified, assumptions, "No assumptions identified yet.");
  renderInsightList(evidenceUsed, evidence, "No evidence statements yet.");
  renderInsightList(alternativeViewpoints, alternatives, "No alternatives considered yet.");
  renderBookmarks();

  if (reflectionButton) reflectionButton.disabled = userRecords.length === 0;
  if (reflectionSummary && userRecords.length === 0) {
    reflectionSummary.textContent = "A reflection summary becomes available after you begin the conversation.";
  }
}

function resizeComposer() {
  if (!inputEl) return;
  inputEl.style.height = "auto";
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 176)}px`;
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isImageFile(file) {
  return file.type.startsWith("image/");
}

function clearPendingFiles() {
  pendingFiles.forEach((item) => {
    if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
  });
  pendingFiles.length = 0;
  renderAttachmentTray();
}

function removePendingFile(id) {
  const index = pendingFiles.findIndex((item) => item.id === id);
  if (index === -1) return;
  const [removed] = pendingFiles.splice(index, 1);
  if (removed.previewUrl) URL.revokeObjectURL(removed.previewUrl);
  renderAttachmentTray();
}

function addPendingFiles(files) {
  Array.from(files || []).forEach((file) => {
    pendingFiles.push({
      id: crypto.randomUUID(),
      file,
      previewUrl: isImageFile(file) ? URL.createObjectURL(file) : "",
    });
  });
  renderAttachmentTray();
}

function renderAttachmentTray() {
  attachmentTray.replaceChildren();
  attachmentTray.classList.toggle("has-attachments", pendingFiles.length > 0);

  pendingFiles.forEach((item) => {
    const chip = document.createElement("div");
    chip.className = "attachment-chip";

    if (item.previewUrl) {
      const image = document.createElement("img");
      image.className = "attachment-thumb";
      image.src = item.previewUrl;
      image.alt = item.file.name;
      chip.appendChild(image);
    } else {
      const icon = document.createElement("div");
      icon.className = "attachment-icon";
      icon.textContent = item.file.name.split(".").pop()?.slice(0, 3).toUpperCase() || "FILE";
      chip.appendChild(icon);
    }

    const info = document.createElement("div");
    info.className = "attachment-info";

    const name = document.createElement("div");
    name.className = "attachment-name";
    name.textContent = item.file.name;

    const meta = document.createElement("div");
    meta.className = "attachment-meta";
    meta.textContent = formatFileSize(item.file.size);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "attachment-remove";
    remove.setAttribute("aria-label", `Remove ${item.file.name}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => removePendingFile(item.id));

    info.append(name, meta);
    chip.append(info, remove);
    attachmentTray.appendChild(chip);
  });
}




async function downloadChatFile(file) {
  if (!requireActiveSession()) return;

  const response = await fetch(apiUrl(`/api/documents/files/${encodeURIComponent(file.file_id)}/download`), {
    headers: authHeaders(),
  });

  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = file.filename || "download";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function renderChatFiles(files = []) {
  chatFilePanel.replaceChildren();

  const header = document.createElement("div");
  header.className = "chat-file-header";

  const title = document.createElement("span");
  title.textContent = "Files";

  const count = document.createElement("span");
  count.className = "chat-file-count";
  count.textContent = String(files.length);

  header.append(title, count);
  chatFilePanel.appendChild(header);

  if (!files.length) {
    const empty = document.createElement("div");
    empty.className = "chat-file-empty";
    empty.textContent = "No files in this chat";
    chatFilePanel.appendChild(empty);
    return;
  }

  const list = document.createElement("div");
  list.className = "chat-file-list";

  files.slice(0, 6).forEach((file) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "chat-file-item";
    item.title = `Download ${file.filename}`;
    item.setAttribute("aria-label", `Download ${file.filename}`);

    const icon = document.createElement("span");
    icon.className = "chat-file-icon";
    icon.textContent = (file.filename.split(".").pop() || "file").slice(0, 3).toUpperCase();

    const name = document.createElement("span");
    name.className = "chat-file-name";
    name.textContent = file.filename;

    item.append(icon, name);
    item.addEventListener("click", async () => {
      scanStatus.textContent = `Downloading ${file.filename}...`;
      try {
        await downloadChatFile(file);
        scanStatus.textContent = `Downloaded ${file.filename}.`;
      } catch (error) {
        scanStatus.textContent = `Download failed: ${error.message}`;
      }
    });
    list.appendChild(item);
  });

  chatFilePanel.appendChild(list);
}

async function loadChatFiles() {
  renderChatFiles([]);
}

function formatThreadDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function renderThreadList(conversations = []) {
  threadList.replaceChildren();

  if (!conversations.length) {
    const empty = document.createElement("div");
    empty.className = "thread-empty";
    empty.textContent = "No saved chats yet.";
    threadList.appendChild(empty);
    return;
  }

  conversations.forEach((conversation) => {
    const row = document.createElement("div");
    row.className = "thread-row";
    if (conversation.conversation_id === conversationId) {
      row.classList.add("is-active");
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = "thread-item";

    const title = document.createElement("span");
    title.className = "thread-title";
    title.textContent = conversation.title || "New conversation";

    const meta = document.createElement("span");
    meta.className = "thread-meta";
    meta.textContent = `${conversation.message_count || 0} messages · ${formatThreadDate(conversation.updated_at)}`;

    const settings = document.createElement("button");
    settings.type = "button";
    settings.className = "thread-settings";
    settings.title = "Chat settings";
    settings.setAttribute("aria-label", "Chat settings");
    settings.textContent = "⋯";

    const menu = document.createElement("div");
    menu.className = "thread-menu";

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "thread-delete";
    deleteButton.textContent = "Delete chat";

    button.append(title, meta);
    menu.appendChild(deleteButton);
    row.append(button, settings, menu);

    button.addEventListener("click", () => selectConversation(conversation.conversation_id));
    settings.addEventListener("click", (event) => {
      event.stopPropagation();
      row.classList.toggle("is-menu-open");
    });
    deleteButton.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteConversation(conversation.conversation_id);
    });

    threadList.appendChild(row);
  });
}

async function loadThreadList() {
  if (!activeCourse) {
    renderThreadList([]);
    return;
  }
  try {
    const data = await getJson(`/api/conversations?course_id=${encodeURIComponent(activeCourse.course_id)}`);
    renderThreadList(data.conversations || []);
  } catch (error) {
    renderThreadList([]);
  }
}

async function selectConversation(nextConversationId) {
  conversationId = nextConversationId;
  localStorage.setItem(CONVERSATION_KEY, conversationId);
  if (activeCourse) localStorage.setItem(courseConversationKey(activeCourse.course_id), conversationId);
  scanStatus.textContent = "";
  await loadConversation();
  await loadChatFiles();
  await loadThreadList();
  inputEl.focus();
}

async function deleteConversation(targetConversationId) {
  const ok = confirm("Delete this chat? This will remove it from PostgreSQL.");
  if (!ok) return;

  try {
    const result = await deleteJson(`/api/conversations/${targetConversationId}`);
    if (!result.deleted) {
      scanStatus.textContent = "Chat was not found in the database.";
      await loadThreadList();
      return;
    }

    if (targetConversationId === conversationId) {
      conversationId = createConversationId();
      localStorage.setItem(CONVERSATION_KEY, conversationId);
      if (activeCourse) localStorage.setItem(courseConversationKey(activeCourse.course_id), conversationId);
      clearMessages();
      showWelcome();
    }

    scanStatus.textContent = "Chat deleted from database.";
    await loadThreadList();
  } catch (error) {
    scanStatus.textContent = `Delete failed: ${error.message}`;
  }
}

function markdownTableCells(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function isMarkdownTableSeparator(line) {
  const cells = markdownTableCells(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function appendInlineEmphasis(container, content) {
  const text = String(content || "");
  const boldPattern = /\*\*([^*\n]+)\*\*/g;
  let cursor = 0;
  let match;

  while ((match = boldPattern.exec(text)) !== null) {
    if (match.index > cursor) {
      container.appendChild(document.createTextNode(text.slice(cursor, match.index)));
    }
    const keyword = document.createElement("strong");
    keyword.className = "concept-emphasis";
    keyword.textContent = match[1];
    container.appendChild(keyword);
    cursor = boldPattern.lastIndex;
  }

  if (cursor < text.length) {
    container.appendChild(document.createTextNode(text.slice(cursor)));
  }
}

function splitFinalSocraticQuestion(content) {
  const text = String(content || "").trim();
  if (!text.endsWith("?")) return { lead: text, question: "" };

  const paragraphBreaks = [...text.matchAll(/\n\s*\n/g)];
  const paragraphBreak = paragraphBreaks.at(-1);
  if (paragraphBreak) {
    const question = text.slice(paragraphBreak.index + paragraphBreak[0].length).trim();
    if (question.endsWith("?")) {
      return { lead: text.slice(0, paragraphBreak.index).trim(), question };
    }
  }

  const sentenceBreaks = [...text.matchAll(/[.!]\s+(?=[A-Z*])/g)];
  const sentenceBreak = sentenceBreaks.at(-1);
  if (sentenceBreak) {
    const questionStart = sentenceBreak.index + sentenceBreak[0].length;
    const question = text.slice(questionStart).trim();
    if (question.endsWith("?")) {
      return {
        lead: text.slice(0, sentenceBreak.index + 1).trim(),
        question,
      };
    }
  }

  return { lead: "", question: text };
}

function appendAssistantContent(container, content) {
  const lines = String(content || "").split("\n");
  let index = 0;
  let textLines = [];

  const flushText = () => {
    if (!textLines.length) return;
    const textBlock = document.createElement("div");
    textBlock.className = "message-text";
    const textContent = textLines.join("\n").trim();
    appendInlineEmphasis(textBlock, textContent);
    if (textContent) container.appendChild(textBlock);
    textLines = [];
  };

  while (index < lines.length) {
    const headerCells = markdownTableCells(lines[index]);
    const hasTable = lines[index].includes("|")
      && index + 1 < lines.length
      && isMarkdownTableSeparator(lines[index + 1]);
    if (!hasTable) {
      textLines.push(lines[index]);
      index += 1;
      continue;
    }

    flushText();
    const wrapper = document.createElement("div");
    wrapper.className = "message-table-wrap";
    const table = document.createElement("table");
    table.className = "message-table";
    const head = document.createElement("thead");
    const headRow = document.createElement("tr");
    headerCells.forEach((cell) => {
      const heading = document.createElement("th");
      heading.scope = "col";
      appendInlineEmphasis(heading, cell);
      headRow.appendChild(heading);
    });
    head.appendChild(headRow);
    table.appendChild(head);

    const body = document.createElement("tbody");
    index += 2;
    while (index < lines.length && lines[index].includes("|")) {
      const rowCells = markdownTableCells(lines[index]);
      if (rowCells.length !== headerCells.length) break;
      const row = document.createElement("tr");
      rowCells.forEach((cell) => {
        const data = document.createElement("td");
        appendInlineEmphasis(data, cell);
        row.appendChild(data);
      });
      body.appendChild(row);
      index += 1;
    }
    table.appendChild(body);
    wrapper.appendChild(table);
    container.appendChild(wrapper);
  }
  flushText();
}

function appendMessage(role, content, sources = [], options = {}) {
  messagesEl.querySelector(".conversation-empty")?.remove();
  const item = document.createElement("article");
  item.className = `message ${role}`;
  const isQuestion = role === "assistant" && String(content).trim().endsWith("?");
  const questionType = isQuestion ? inferQuestionType(content) : "";

  const header = document.createElement("header");
  header.className = "message-header";

  const identity = document.createElement("div");
  identity.className = "message-identity";
  const avatar = document.createElement("span");
  avatar.className = "message-avatar";
  avatar.textContent = role === "assistant" ? "S" : (getDisplayName().charAt(0).toUpperCase() || "Y");
  avatar.setAttribute("aria-hidden", "true");
  const roleLabel = document.createElement("strong");
  roleLabel.textContent = role === "assistant" ? "Socratic tutor" : "You";
  identity.append(avatar, roleLabel);

  if (isQuestion) {
    const typeBadge = document.createElement("span");
    typeBadge.className = "question-type-badge";
    typeBadge.textContent = questionType;
    identity.appendChild(typeBadge);
    questionTypesSeen.add(questionType);
  }

  const meta = document.createElement("div");
  meta.className = "message-meta";
  if (!options.saved) {
    const time = document.createElement("time");
    time.textContent = formatClock();
    time.dateTime = new Date().toISOString();
    meta.appendChild(time);
  }

  if (isQuestion) {
    const bookmarkKey = `${activeCourse?.course_id || "general"}:${content}`;
    const bookmarkButton = document.createElement("button");
    bookmarkButton.type = "button";
    bookmarkButton.className = "message-bookmark";
    bookmarkButton.title = "Bookmark this question";
    bookmarkButton.setAttribute("aria-label", "Bookmark this tutor question");
    const refreshBookmarkState = () => {
      const bookmarked = questionBookmarks.some((bookmark) => bookmark.key === bookmarkKey);
      bookmarkButton.classList.toggle("is-bookmarked", bookmarked);
      bookmarkButton.setAttribute("aria-pressed", String(bookmarked));
      bookmarkButton.textContent = bookmarked ? "◆" : "◇";
    };
    bookmarkButton.addEventListener("click", () => {
      const index = questionBookmarks.findIndex((bookmark) => bookmark.key === bookmarkKey);
      if (index >= 0) {
        questionBookmarks.splice(index, 1);
      } else {
        questionBookmarks.push({
          key: bookmarkKey,
          course_id: activeCourse?.course_id || null,
          conversation_id: conversationId,
          content,
          question_type: questionType,
          created_at: new Date().toISOString(),
        });
      }
      persistQuestionBookmarks();
      refreshBookmarkState();
      renderBookmarks();
    });
    refreshBookmarkState();
    meta.appendChild(bookmarkButton);
  }

  header.append(identity, meta);
  item.appendChild(header);

  const body = document.createElement("div");
  body.className = "message-body";
  if (role === "assistant") {
    const { lead, question } = splitFinalSocraticQuestion(content);
    if (isQuestion && question) {
      body.classList.add("has-question-focus");
      if (lead) appendAssistantContent(body, lead);

      const questionFocus = document.createElement("section");
      questionFocus.className = "socratic-question-focus";
      questionFocus.setAttribute("aria-label", "Your next thinking step");
      const questionLabel = document.createElement("span");
      questionLabel.className = "socratic-question-label";
      questionLabel.textContent = "Your next thinking step";
      const questionContent = document.createElement("div");
      questionContent.className = "socratic-question-content";
      appendAssistantContent(questionContent, question);
      questionFocus.append(questionLabel, questionContent);
      body.appendChild(questionFocus);
    } else {
      appendAssistantContent(body, content);
    }
  } else {
    body.textContent = content;
  }
  item.appendChild(body);

  if (isQuestion) {
    const why = document.createElement("details");
    why.className = "question-rationale";
    const summary = document.createElement("summary");
    summary.textContent = "Why am I being asked this?";
    const explanation = document.createElement("p");
    explanation.textContent = questionTypeExplanation(questionType);
    why.append(summary, explanation);
    item.appendChild(why);
  }

  if (sources.length) {
    const sourceBlock = document.createElement("div");
    sourceBlock.className = "sources";
    const sourceLabel = document.createElement("strong");
    sourceLabel.textContent = "Evidence context";
    const sourceNames = document.createElement("span");
    sourceNames.textContent = [...new Set(sources.map((source) => source.title))].join(" · ");
    sourceBlock.append(sourceLabel, sourceNames);
    item.appendChild(sourceBlock);
  }

  messageRecords.push({ role, content, sources, isQuestion, questionType, saved: Boolean(options.saved) });
  messagesEl.appendChild(item);
  renderSuggestedResponses(isQuestion ? content : "");
  updateLearningPanel();
  messagesEl.scrollTop = messagesEl.scrollHeight;
}



function showThinkingIndicator() {
  const steps = [
    "Reading your question",
    "Searching uploaded documents",
    "Tracing the strongest evidence",
    "Preparing your next question",
  ];
  let stepIndex = 0;

  const item = document.createElement("article");
  item.className = "message assistant thinking-message";
  item.setAttribute("aria-live", "polite");
  item.setAttribute("aria-label", "Socratic tutor is thinking");

  const mark = document.createElement("span");
  mark.className = "thinking-mark";
  mark.setAttribute("aria-hidden", "true");
  mark.innerHTML = `
    <svg viewBox="0 0 44 44" focusable="false">
      <circle class="thinking-orbit-track" cx="22" cy="22" r="16"></circle>
      <g class="thinking-orbit-particles">
        <circle class="thinking-particle thinking-particle-primary" cx="22" cy="6" r="3.2"></circle>
        <circle class="thinking-particle thinking-particle-secondary" cx="22" cy="38" r="2.4"></circle>
      </g>
      <circle class="thinking-mark-center" cx="22" cy="22" r="10"></circle>
      <text class="thinking-mark-letter" x="22" y="22">S</text>
    </svg>`;

  const statusWrap = document.createElement("div");
  statusWrap.className = "thinking-copy";
  const tutor = document.createElement("strong");
  tutor.textContent = "Socratic tutor";
  const status = document.createElement("span");
  status.className = "thinking-status";
  status.textContent = steps[stepIndex];
  statusWrap.append(tutor, status);

  item.append(mark, statusWrap);
  messagesEl.appendChild(item);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  const timer = window.setInterval(() => {
    stepIndex = (stepIndex + 1) % steps.length;
    status.textContent = steps[stepIndex];
  }, 1400);

  return {
    remove() {
      window.clearInterval(timer);
      item.remove();
    },
  };
}

function setBusy(isBusy) {
  sendButton.disabled = isBusy;
  inputEl.disabled = isBusy;
  suggestedResponses?.classList.toggle("is-busy", isBusy);
}

async function responseErrorMessage(response) {
  const rawMessage = (await response.text()).trim();
  if (!rawMessage) return `The request could not be completed (${response.status}).`;

  try {
    const payload = JSON.parse(rawMessage);
    if (typeof payload.detail === "string") return payload.detail;
    if (typeof payload.message === "string") return payload.message;
  } catch {
    if (rawMessage.startsWith("<")) {
      return "The server could not complete the request. Please try again.";
    }
  }

  return rawMessage;
}

async function getJson(url) {
  const response = await fetch(apiUrl(url), { headers: authHeaders() });

  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }

  return response.json();
}

async function postJson(url, payload = {}) {
  const response = await fetch(apiUrl(url), {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }

  return response.json();
}

async function postForm(url, formData) {
  const response = await fetch(apiUrl(url), {
    method: "POST",
    headers: authHeaders(),
    body: formData,
  });

  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }

  return response.json();
}

async function uploadPendingFiles() {
  if (!pendingFiles.length) return null;
  if (!requireActiveSession()) return null;
  if (activeCourse) {
    clearPendingFiles();
    scanStatus.textContent = "Course documents are managed from the instructor dashboard.";
    return null;
  }
  if (!canManageCourseMaterials()) {
    clearPendingFiles();
    scanStatus.textContent = "Only instructors can upload course materials.";
    return null;
  }

  composerAttachButton.disabled = true;
  scanStatus.textContent = "Uploading and indexing...";

  const formData = new FormData();
  formData.append("conversation_id", conversationId);
  pendingFiles.forEach((item) => formData.append("files", item.file));

  try {
    const data = await postForm("/api/documents/upload", formData);
    const skipped = data.skipped_files?.length
      ? ` Skipped unsupported file(s): ${data.skipped_files.join(", ")}.`
      : "";
    scanStatus.textContent = `${data.message} Processed ${data.documents_scanned} file(s), stored ${data.files_stored || 0} in PostgreSQL, added ${data.chunks_added} chunk(s).${skipped}`;
    clearPendingFiles();
    await loadChatFiles();
    await loadThreadList();
    return data;
  } finally {
    fileInput.value = "";
    composerAttachButton.disabled = false;
  }
}

function supportedFiles(files) {
  return Array.from(files || []).filter((file) => /\.(txt|md|pdf|tex|html|htm)$/i.test(file.name));
}

async function uploadFiles(files) {
  if (!requireActiveSession()) return;
  if (activeCourse) {
    scanStatus.textContent = "Return to the instructor dashboard to publish course documents.";
    return;
  }
  if (!canManageCourseMaterials()) {
    scanStatus.textContent = "Only instructors can upload course materials.";
    return;
  }
  const accepted = supportedFiles(files);
  if (!accepted.length) {
    scanStatus.textContent = "Use .txt, .md, .pdf, .tex, .html, or .htm files.";
    return;
  }

  composerAttachButton.disabled = true;
  scanStatus.textContent = "Uploading and indexing...";

  const formData = new FormData();
  formData.append("conversation_id", conversationId);
  accepted.forEach((file) => formData.append("files", file));

  try {
    const data = await postForm("/api/documents/upload", formData);
    const skipped = data.skipped_files?.length
      ? ` Skipped unsupported file(s): ${data.skipped_files.join(", ")}.`
      : "";
    scanStatus.textContent = `${data.message} Processed ${data.documents_scanned} file(s), stored ${data.files_stored || 0} in PostgreSQL, added ${data.chunks_added} chunk(s).${skipped}`;
    await loadChatFiles();
    await loadThreadList();
  } catch (error) {
    scanStatus.textContent = `Upload failed: ${error.message}`;
  } finally {
    fileInput.value = "";
    composerAttachButton.disabled = false;
  }
}

async function deleteJson(url) {
  const response = await fetch(apiUrl(url), { method: "DELETE", headers: authHeaders() });

  if (!response.ok) {
    throw new Error(await responseErrorMessage(response));
  }

  return response.json();
}


async function loadConversation() {
  if (!requireActiveSession()) return;
  clearMessages();

  try {
    const data = await getJson(`/api/conversations/${conversationId}`);
    if (!data.messages?.length) {
      showWelcome();
      return;
    }

    data.messages.forEach((message) => {
      appendMessage(message.role, message.content, [], { saved: true });
      history.push({ role: message.role, content: message.content });
    });
  } catch (error) {
    showWelcome();
  }
}

async function startNewChat() {
  if (!requireActiveSession() || !activeCourse) return;
  conversationId = createConversationId();
  localStorage.setItem(CONVERSATION_KEY, conversationId);
  localStorage.setItem(courseConversationKey(activeCourse.course_id), conversationId);
  scanStatus.textContent = "New chat started.";
  clearMessages();
  clearPendingFiles();
  renderChatFiles([]);
  showWelcome();
  await loadChatFiles();
  await loadThreadList();
  inputEl.focus();
}


showLoginButton.addEventListener("click", () => setAuthMode("login"));
showRegisterButton.addEventListener("click", () => setAuthMode("register"));

async function finishAuth(data) {
  saveUser(data.user, data.access_token, data.expires_in_seconds);
  routeAuthenticatedUser();
}

async function openChatWorkspace() {
  if (!requireActiveSession() || !activeCourse) {
    showDashboard();
    return;
  }
  showAuthenticatedApp();
  await loadConversation();
  await loadChatFiles();
  await loadThreadList();
  inputEl.focus();
}

async function loadInstructorRequests() {
  if (getRole() !== "admin") return;
  adminRequestsStatus.textContent = "Loading instructor requests...";
  try {
    const requests = await getJson("/api/admin/instructor-requests");
    adminRequestsList.replaceChildren();
    if (!requests.length) {
      const empty = document.createElement("div");
      empty.className = "admin-request-empty";
      empty.textContent = "No pending instructor requests.";
      adminRequestsList.appendChild(empty);
    }

    requests.forEach((user) => {
      const row = document.createElement("div");
      row.className = "admin-request-row";

      const identity = document.createElement("div");
      const name = document.createElement("div");
      name.className = "admin-request-name";
      name.textContent = user.display_name || user.username;
      const email = document.createElement("div");
      email.className = "admin-request-email";
      email.textContent = user.email;
      identity.append(name, email);

      const actions = document.createElement("div");
      actions.className = "admin-request-actions";
      const approve = document.createElement("button");
      approve.type = "button";
      approve.textContent = "Approve";
      const reject = document.createElement("button");
      reject.type = "button";
      reject.className = "reject-button";
      reject.textContent = "Keep as student";

      const updateAuthority = async (authorityLevel) => {
        approve.disabled = true;
        reject.disabled = true;
        adminRequestsStatus.textContent = authorityLevel === 1
          ? `Approving ${user.email}...`
          : `Keeping ${user.email} as a student...`;
        try {
          await postJson(`/api/admin/users/${encodeURIComponent(user.user_id)}/authority`, {
            authority_level: authorityLevel,
          });
          await loadInstructorRequests();
        } catch (error) {
          approve.disabled = false;
          reject.disabled = false;
          adminRequestsStatus.textContent = error.message;
        }
      };
      approve.addEventListener("click", () => updateAuthority(1));
      reject.addEventListener("click", () => updateAuthority(2));
      actions.append(approve, reject);
      row.append(identity, actions);
      adminRequestsList.appendChild(row);
    });
    adminRequestsStatus.textContent = "";
  } catch (error) {
    adminRequestsStatus.textContent = `Could not load requests: ${error.message}`;
  }
}

onboardingForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const password = document.querySelector("#onboardingPassword").value;
  const passwordConfirmation = document.querySelector("#onboardingPasswordConfirmation").value;
  if (password !== passwordConfirmation) {
    onboardingStatus.textContent = "Password and password confirmation must match.";
    return;
  }

  const submitButton = onboardingForm.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  onboardingStatus.textContent = "Saving your account...";
  try {
    const data = await postJson("/api/auth/onboarding", {
      username: document.querySelector("#onboardingUsername").value.trim(),
      password,
      password_confirmation: passwordConfirmation,
      position: onboardingForm.elements.position.value,
    });
    currentUser = { ...currentUser, ...data.user };
    persistCurrentUser();
    onboardingForm.reset();
    routeAuthenticatedUser();
  } catch (error) {
    onboardingStatus.textContent = `Account setup failed: ${error.message}`;
  } finally {
    submitButton.disabled = false;
  }
});

openWorkspaceButton?.addEventListener("click", () => {
  const target = getRole() === "student" ? studentCoursesSection : instructorWorkspaceSection;
  target?.scrollIntoView({ behavior: "smooth", block: "start" });
});
dashboardButton?.addEventListener("click", showDashboard);
refreshStudentCoursesButton?.addEventListener("click", loadCourses);

courseCreateForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!requireActiveSession()) return;
  const submit = courseCreateForm.querySelector('button[type="submit"]');
  submit.disabled = true;
  instructorCoursesStatus.textContent = "Creating course...";
  try {
    const course = await postJson("/api/courses", {
      course_code: document.querySelector("#courseCodeInput").value.trim(),
      title: document.querySelector("#courseTitleInput").value.trim(),
      description: document.querySelector("#courseDescriptionInput").value.trim(),
    });
    courseCreateForm.reset();
    instructorCoursesStatus.textContent = `${course.course_code} was created.`;
    await loadCourses();
    const created = courses.find((item) => item.course_id === course.course_id) || course;
    await selectInstructorCourse(created);
  } catch (error) {
    instructorCoursesStatus.textContent = `Could not create course: ${error.message}`;
  } finally {
    submit.disabled = false;
  }
});

courseDocumentForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedInstructorCourse || !courseDocumentInput.files?.length) return;
  const submit = courseDocumentForm.querySelector('button[type="submit"]');
  submit.disabled = true;
  courseDocumentsStatus.textContent = "Uploading and indexing course documents...";
  const formData = new FormData();
  Array.from(courseDocumentInput.files).forEach((file) => formData.append("files", file));
  try {
    const data = await postForm(
      `/api/courses/${encodeURIComponent(selectedInstructorCourse.course_id)}/documents/upload`,
      formData,
    );
    courseDocumentsStatus.textContent = data.message;
    courseDocumentForm.reset();
    await Promise.all([loadCourseDocuments(), loadCourses()]);
  } catch (error) {
    courseDocumentsStatus.textContent = `Upload failed: ${error.message}`;
  } finally {
    submit.disabled = false;
  }
});

previewCourseButton?.addEventListener("click", () => {
  if (selectedInstructorCourse) openCourseChat(selectedInstructorCourse, true);
});

deleteCourseButton?.addEventListener("click", deleteSelectedCourse);

async function connectGitHubAccount() {
  if (!currentUser?.access_token) {
    expireSession("Sign in with your school account first.");
    return;
  }
  connectGithubButton.disabled = true;
  authStatus.textContent = "Opening GitHub...";
  try {
    const data = await postJson("/api/auth/github/start");
    window.location.assign(data.authorize_url);
  } catch (error) {
    connectGithubButton.disabled = false;
    authStatus.textContent = `GitHub connection failed: ${error.message}`;
  }
}

connectGithubButton?.addEventListener("click", connectGitHubAccount);

async function handleGoogleCredential(response) {
  authStatus.textContent = "Signing in with Google...";
  try {
    const data = await postJson("/api/auth/google", { credential: response.credential });
    await finishAuth(data);
  } catch (error) {
    authStatus.textContent = error.message.includes("UNC Charlotte")
      ? error.message
      : `We couldn't complete Google sign-in. ${error.message}`;
  }
}

async function setupGoogleSignIn() {
  if (!googleSignInWrap || !googleSignInButton) return;

  try {
    const config = await getJson("/api/auth/google/config");
    if (!config.client_id) {
      googleSignInWrap.classList.add("is-hidden");
      return;
    }

    const initialize = () => {
      if (!window.google?.accounts?.id) {
        window.setTimeout(initialize, 200);
        return;
      }

      window.google.accounts.id.initialize({
        client_id: config.client_id,
        callback: handleGoogleCredential,
        hd: config.hosted_domain || undefined,
      });

      renderGoogleSignInButton = () => {
        googleSignInButton.replaceChildren();
        window.google.accounts.id.renderButton(googleSignInButton, {
          theme: document.documentElement.dataset.theme === "dark" ? "filled_black" : "outline",
          size: "large",
          width: 360,
          text: "continue_with",
          shape: "rectangular",
        });
      };
      renderGoogleSignInButton();
    };
    initialize();
  } catch {
    googleSignInWrap.classList.add("is-hidden");
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authStatus.textContent = "Signing in...";
  try {
    const data = await postJson("/api/auth/login", {
      identifier: document.querySelector("#loginIdentifier").value.trim(),
      password: document.querySelector("#loginPassword").value,
    });
    await finishAuth(data);
  } catch (error) {
    authStatus.textContent = `Login failed: ${error.message}`;
  }
});

function applyAuthenticationMode(config) {
  const required = Boolean(config.email_verification_required);
  authMode = config.auth_mode || "open";
  registrationEnabled = config.registration_enabled !== false;
  githubAccountRequired = Boolean(config.github_account_required);
  githubOauthConfigured = Boolean(config.github_oauth_configured);
  emailVerificationRequired = required;
  sendEmailCodeButton?.classList.toggle("is-hidden", !required);
  verificationCodeField?.classList.toggle("is-hidden", !required);
  if (registerVerificationCode) {
    registerVerificationCode.required = required;
    if (!required) registerVerificationCode.value = "";
  }

  const passwordAuthEnabled = config.password_auth_enabled !== false;
  if (!passwordAuthEnabled && currentUser && !currentUser.access_token) {
    expireSession("Please sign in again with your school Google account.");
  }
  emailAuthDivider?.classList.toggle("is-hidden", !passwordAuthEnabled);
  authTabs?.classList.toggle("is-hidden", !passwordAuthEnabled);
  showRegisterButton?.classList.toggle("is-hidden", !registrationEnabled);
  loginForm?.classList.toggle("is-hidden", !passwordAuthEnabled);
  registerForm?.classList.add("is-hidden");

  const domain = config.school_domain || "your school";
  if (authCopy && authMode === "school_google") {
    authCopy.textContent = passwordAuthEnabled
      ? `New users: verify your ${domain} Google account. Returning users: sign in with your Socratic-Chat ID and password.`
      : `Sign in with your ${domain} Google account to use the chatbot.`;
  }
}

async function setupAuthenticationMode() {
  try {
    const config = await getJson("/api/auth/config");
    applyAuthenticationMode(config);
  } catch {
    applyAuthenticationMode({
      email_verification_required: false,
      auth_mode: "unavailable",
      password_auth_enabled: false,
      registration_enabled: false,
      school_domain: "charlotte.edu",
      github_account_required: false,
      github_oauth_configured: false,
    });
    authStatus.textContent = "Authentication server unavailable. Check the Render API address.";
  }
}

async function restoreLinkedAccount() {
  if (!currentUser?.access_token) return;
  try {
    const data = await getJson("/api/auth/me");
    currentUser = { ...currentUser, ...data.user };
    persistCurrentUser();
  } catch {
    expireSession("Your session ended. Please sign in again.");
  }
}

async function requestEmailVerificationCode() {
  const email = document.querySelector("#registerEmail").value.trim();
  if (!email) {
    authStatus.textContent = "Enter your email first.";
    return;
  }

  sendEmailCodeButton.disabled = true;
  authStatus.textContent = "Sending verification code...";
  try {
    const data = await postJson("/api/auth/send-verification-code", { email });
    authStatus.textContent = `${data.message} It expires in ${data.expires_in_minutes} minutes.`;
    registerVerificationCode?.focus();
  } catch (error) {
    authStatus.textContent = `Could not send code: ${error.message}`;
  } finally {
    sendEmailCodeButton.disabled = false;
  }
}

sendEmailCodeButton?.addEventListener("click", requestEmailVerificationCode);

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authStatus.textContent = "Creating account...";
  try {
    const data = await postJson("/api/auth/register", {
      username: document.querySelector("#registerUsername").value.trim(),
      email: document.querySelector("#registerEmail").value.trim(),
      password: document.querySelector("#registerPassword").value,
      verification_code: emailVerificationRequired ? registerVerificationCode.value.trim() : null,
    });
    await finishAuth(data);
  } catch (error) {
    authStatus.textContent = `Register failed: ${error.message}`;
  }
});

logoutButton.addEventListener("click", () => {
  expireSession("");
});

dashboardLogoutButton?.addEventListener("click", () => expireSession(""));
onboardingLogoutButton?.addEventListener("click", () => expireSession(""));

extendSessionButton?.addEventListener("click", async () => {
  try {
    await extendSession();
    scanStatus.textContent = "Session extended.";
  } catch {
    expireSession("Your session ended. Please sign in again.");
  }
});

sessionLogoutButton?.addEventListener("click", () => {
  expireSession("");
});

newChatButton.addEventListener("click", startNewChat);

sidebarToggle?.addEventListener("click", () => {
  setSidebarCollapsed(!appShell.classList.contains("sidebar-collapsed"));
});

mobileSidebarToggle?.addEventListener("click", () => {
  setMobileSidebar(!appShell.classList.contains("sidebar-open"));
});

sidebarScrim?.addEventListener("click", () => setMobileSidebar(false));

progressNavButton?.addEventListener("click", () => {
  setLearningPanelOpen(true);
  setMobileSidebar(false);
  learningPanel?.focus({ preventScroll: true });
});

settingsNavButton?.addEventListener("click", () => {
  setMobileSidebar(false);
  themeToggle?.focus();
});

learningPanelToggle?.addEventListener("click", () => {
  setLearningPanelOpen(appShell.classList.contains("learning-panel-closed"));
});

learningPanelClose?.addEventListener("click", () => setLearningPanelOpen(false));

reflectionButton?.addEventListener("click", () => {
  const userTurns = messageRecords.filter((record) => record.role === "user").length;
  const tutorQuestions = messageRecords.filter((record) => record.role === "assistant" && record.isQuestion).length;
  const types = [...questionTypesSeen];
  reflectionSummary.replaceChildren();

  const lead = document.createTextNode("You contributed ");
  const reflectionCount = document.createElement("strong");
  reflectionCount.textContent = `${userTurns} reflection${userTurns === 1 ? "" : "s"}`;
  const middle = document.createTextNode(` across ${tutorQuestions} guided question${tutorQuestions === 1 ? "" : "s"}. `);
  const focus = document.createElement("strong");
  focus.textContent = types.length ? types.join(", ") : "Clarification";
  const end = document.createTextNode(" shaped this exploration. Which idea would you explain differently now?");
  reflectionSummary.append(lead, reflectionCount, middle, focus, end);
});

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    formEl.requestSubmit();
  }
});

inputEl.addEventListener("input", resizeComposer);

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!requireActiveSession()) return;
  if (!activeCourse) {
    showDashboard();
    return;
  }
  const message = inputEl.value.trim();
  if (!message && !pendingFiles.length) return;

  inputEl.value = "";
  resizeComposer();
  renderSuggestedResponses();
  if (message) {
    appendMessage("user", message);
    history.push({ role: "user", content: message });
  }
  setBusy(true);
  let thinkingIndicator = null;

  try {
    await uploadPendingFiles();

    if (!message) {
      appendMessage("assistant", "File attached to this chat. Ask me a question about it when you are ready.");
      return;
    }

    thinkingIndicator = showThinkingIndicator();
    const data = await postJson("/api/chat", {
      message,
      conversation_id: conversationId,
      course_id: activeCourse?.course_id || null,
      history: history.slice(-8),
      top_k: 4,
    });
    if (data.conversation_id) {
      conversationId = data.conversation_id;
      localStorage.setItem(CONVERSATION_KEY, conversationId);
      if (activeCourse) localStorage.setItem(courseConversationKey(activeCourse.course_id), conversationId);
    }
    thinkingIndicator?.remove();
    thinkingIndicator = null;
    appendMessage("assistant", data.answer, data.sources || []);
    history.push({ role: "assistant", content: data.answer });
    await loadThreadList();
  } catch (error) {
    thinkingIndicator?.remove();
    thinkingIndicator = null;
    appendMessage("assistant", `Request failed: ${error.message}`);
  } finally {
    setBusy(false);
    inputEl.focus();
  }
});

composerAttachButton.addEventListener("click", () => {
  scanStatus.textContent = "Course documents are uploaded from the instructor dashboard.";
});

fileInput.addEventListener("change", () => {
  addPendingFiles(fileInput.files || []);
  fileInput.value = "";
});

chatPanel.addEventListener("dragover", (event) => {
  if (activeCourse) return;
});

chatPanel.addEventListener("dragleave", (event) => {
  if (!chatPanel.contains(event.relatedTarget)) {
    chatPanel.classList.remove("is-dragging");
  }
});

chatPanel.addEventListener("drop", (event) => {
  if (activeCourse) return;
});

setInterval(() => {
  if (currentUser && isSessionExpired()) {
    expireSession();
    return;
  }
  updateSessionStatus();
}, 1000);

await setupAuthenticationMode();
await setupGoogleSignIn();

const githubResult = new URLSearchParams(window.location.search).get("github");
if (githubResult) {
  window.history.replaceState({}, "", window.location.pathname + window.location.hash);
  if (githubResult !== "connected") {
    authStatus.textContent = "GitHub connection was not completed. Please try again.";
  }
}

await restoreLinkedAccount();

if (currentUser) {
  routeAuthenticatedUser();
} else {
  renderChatFiles([]);
  showSignedOut();
}

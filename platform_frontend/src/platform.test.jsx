import React from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "./main";
import { SESSION_KEY } from "./api";
import { resetCourseContext } from "./courseContext";
beforeEach(resetCourseContext);

const course = "8b71218d-71f3-436e-a4a6-1b279c4fda79";
const assignment = {
  id: "assignment-1",
  course_id: course,
  course_code: "SE101",
  tool: "socratic",
  title: "Discuss requirements",
  instructions: "Connect your ideas.",
  due_at: null,
  status: "published",
  progress: "not_started",
  student_config: { minimum_messages: 1 },
};
const attempt = {
  id: "attempt-1",
  status: "in_progress",
  engine_state: {},
  messages: [
    { role: "assistant", content: "What makes a requirement useful?" },
  ],
};

function mockApi(role = "instructor", override = {}) {
  localStorage.setItem(
    SESSION_KEY,
    JSON.stringify({
      access_token: "test-session",
      expires_at: Date.now() + 3600000,
    }),
  );
  const responses = {
    "/api/auth/me": {
      user: {
        username: "Alex",
        display_name: "Alex Rivera",
        authority_level: role === "instructor" ? 1 : 2,
        onboarding_complete: true,
      },
    },
    "/api/platform/context": {
      course_id: course,
      course_code: "SE101",
      title: "Software Engineering",
    },
    "/api/platform/assignments": [assignment],
    "/api/courses": {
      courses: [
        {
          course_id: course,
          course_code: "SE101",
          title: "Software Engineering",
          description: "Build software collaboratively.",
          instructor_name: "Professor Rivera",
          document_count: 2,
          membership_role: role === "instructor" ? "instructor" : "student",
          membership_status: "approved",
        },
      ],
    },
    [`/api/instructor/enrolled-students?course_id=${course}`]: [
      {
        user_id: "student-1",
        display_name: "Jordan",
        email: "jordan@example.test",
      },
    ],
    [`/api/courses/${course}/documents`]: { files: [] },
    [`/api/courses/${course}/learning-objectives`]: { objectives: [] },
    "/api/platform/topic-templates": [],
    "/api/platform/assignments/assignment-1": assignment,
    "/api/platform/assignments/assignment-1/attempt": null,
    "/api/platform/assignments/assignment-1/start": attempt,
    ...override,
  };
  const fetch = vi.fn(async (url, options = {}) => {
    if (url.startsWith("/api/platform/context")) url = "/api/platform/context";
    if (url.startsWith("/api/platform/assignments?"))
      url = "/api/platform/assignments";
    const entry =
      responses[`${options.method || "GET"} ${url}`] ?? responses[url];
    if (entry === undefined) throw new Error("Unexpected API call: " + url);
    const data = typeof entry === "function" ? await entry(options) : entry;
    return {
      ok: !data?.error,
      status: data?.error ? 422 : 200,
      json: async () => (data?.error ? { detail: data.error } : data),
    };
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
function open(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

test("user selects and persists the platform color theme", async () => {
  mockApi("student");
  open("/student");
  const user = userEvent.setup();

  const theme = await screen.findByLabelText("Choose color theme");
  expect(theme).toHaveValue("light");

  await user.selectOptions(theme, "dark");

  expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  expect(localStorage.getItem("socratic_chat_theme")).toBe("dark");
});

test("professor opens activity creation from assignments rather than the teaching toolkit", async () => {
  mockApi();
  open("/professor");
  const user = userEvent.setup();
  expect(
    await screen.findByRole("heading", { level: 1, name: "All assignments" }),
  ).toBeInTheDocument();
  expect(screen.queryByText("Your teaching toolkit")).not.toBeInTheDocument();
  await user.click(
    screen.getByRole("link", { name: "Analytics", exact: true }),
  );
  expect(
    screen.getByRole("link", { name: "Analytics", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  expect(screen.getByText("Analytics will come here.")).toBeInTheDocument();
  await user.click(
    screen.getByRole("link", { name: "Professor dashboard", exact: true }),
  );
  await user.click(screen.getByRole("link", { name: /Create New Activity/ }));
  expect(
    await screen.findByRole("heading", { name: "Activity details" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Course materials" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Select activity" }),
  ).toBeInTheDocument();
  expect(screen.queryByText("Student Agent Bot")).not.toBeInTheDocument();
});

test("student sees mixed assignments and opens the assigned tool without selecting configuration", async () => {
  mockApi("student", {
    "/api/platform/assignments": [
      assignment,
      {
        ...assignment,
        id: "reflection-1",
        tool: "reflections",
        title: "Reflect on the sprint",
        progress: "in_progress",
      },
      {
        ...assignment,
        id: "tutor-1",
        tool: "student-agent",
        title: "Practice a use case",
        progress: "completed",
      },
    ],
  });
  open("/student");
  const user = userEvent.setup();
  expect(
    await screen.findByRole("heading", { name: "Your assignments" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Courses & access" }),
  ).not.toBeInTheDocument();
  const ongoing = await screen.findByRole("region", { name: /^Left to do/ });
  expect(
    await within(ongoing).findByRole("link", { name: "Resume" }),
  ).toHaveAttribute("href", "/student/assignments/reflection-1");
  expect(
    screen.queryByRole("link", { name: "View result" }),
  ).not.toBeInTheDocument();
  await user.click(
    within(screen.getByRole("region", { name: /^Left to do/ })).getByRole("link", {
      name: "Open assignment",
    }),
  );
  await user.click(
    await screen.findByRole("button", { name: "Start assignment" }),
  );
  expect(
    await screen.findAllByText("What makes a requirement useful?"),
  ).not.toHaveLength(0);
  expect(screen.queryByLabelText("Student ID")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Reflection type")).not.toBeInTheDocument();
});

test("dashboard link shows the student's finished and remaining assignments", async () => {
  mockApi("student", {
    "/api/platform/assignments": [
      { ...assignment, progress: "in_progress" },
      { ...assignment, id: "finished-1", title: "Completed discussion", progress: "completed" },
    ],
    "/api/platform/assignments/assignment-1/attempt": attempt,
  });
  open("/student/assignments/assignment-1");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("link", { name: "Dashboard", exact: true }));

  const left = await screen.findByRole("region", { name: /^Left to do/ });
  const finished = screen.getByRole("region", { name: /^Finished/ });
  expect(within(left).getByText("Discuss requirements")).toBeInTheDocument();
  expect(within(left).getByText("In progress")).toBeInTheDocument();
  expect(within(left).getByRole("link", { name: "Resume" })).toBeInTheDocument();
  expect(within(finished).getByText("Completed discussion")).toBeInTheDocument();
  expect(within(finished).getByText("Completed")).toBeInTheDocument();
  expect(within(finished).getByRole("link", { name: "View result" })).toBeInTheDocument();
});

test("keyword-based Socratic assignments begin with an example and no starter choices", async () => {
  const newAttempt = {
    ...attempt,
    messages: [{ role: "assistant", content: "Let's begin with **code review**. For example, your course material describes this situation: ‘A reviewer checks a proposed change.’ What is happening here?" }],
    engine_state: {
      socratic: { objective_keywords: ["code review", "correctness"] },
    },
  };
  mockApi("student", {
    "/api/platform/assignments/assignment-1/start": newAttempt,
  });
  open("/student/assignments/assignment-1");
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Start assignment" }));
  expect(await screen.findByText(/A reviewer checks a proposed change/)).toBeInTheDocument();
  expect(screen.queryByLabelText("Ways to begin")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Show me an example" })).not.toBeInTheDocument();
});

test("Canvas student landing shows assignments without course selection or enrollment controls", async () => {
  mockApi("student");
  open("/student");
  expect(
    await screen.findByRole("heading", { level: 1, name: "Your assignments" }),
  ).toBeInTheDocument();
  expect(
    (await screen.findAllByRole("link", { name: "Open assignment" }))[0],
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("combobox", { name: "Filter by course" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Request access" }),
  ).not.toBeInTheDocument();
});

test("failed publish retains a saved draft and shows an actionable error", async () => {
  const saved = {
    ...assignment,
    status: "draft",
    audience: "course",
    recipient_ids: [],
    config: { document_ids: ["doc1"], prompt: "", minimum_messages: 1 },
  };
  const fetch = mockApi("instructor", {
    "POST /api/platform/assignments": saved,
    "/api/platform/assignments/assignment-1": saved,
    [`/api/platform/courses/${course}/documents`]: {
      files: [
        { file_id: "f1", document_id: "doc1", filename: "Requirements.txt" },
      ],
    },
    [`/api/courses/${course}/documents`]: {
      files: [
        { file_id: "f1", document_id: "doc1", filename: "Requirements.txt" },
      ],
    },
    [`/api/courses/${course}/learning-objectives`]: { objectives: [] },
    "/api/platform/assignments/assignment-1/publish": {
      error: "Upload course materials first.",
    },
  });
  open("/professor/activities/new");
  const user = userEvent.setup();
  await user.type(
    await screen.findByLabelText("Assignment title"),
    "Discuss requirements",
  );
  await user.click(
    await screen.findByRole("checkbox", { name: /Requirements.txt/ }),
  );
  await user.click(screen.getByRole("button", { name: /Socratic Chat/ }));
  await user.click(
    screen.getByRole("button", { name: "Review activity", exact: true }),
  );
  await user.click(
    screen.getByRole("button", { name: "Publish activity", exact: true }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Upload course materials first.",
  );
  expect(screen.getByRole("button", { name: "Save draft" })).toBeEnabled();
  expect(
    fetch.mock.calls.filter(
      ([url, opt]) =>
        url === "/api/platform/assignments" && opt.method === "POST",
    ),
  ).toHaveLength(1);
});

test("retrying a failed student message reuses its idempotency key", async () => {
  let count = 0;
  const fetch = mockApi("student", {
    "/api/platform/assignments/assignment-1/attempt": attempt,
    "/api/platform/assignments/assignment-1/messages": () =>
      ++count === 1
        ? { error: "Engine unavailable. Retry shortly." }
        : {
            ...attempt,
            messages: [
              ...attempt.messages,
              { role: "user", content: "My answer" },
              { role: "assistant", content: "Good example" },
            ],
          },
  });

  open("/student/assignments/assignment-1");
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Expand chat" }));
  expect(document.querySelector(".workspace-grid")).toHaveClass(
    "chat-expanded",
  );
  await user.click(screen.getByRole("button", { name: "Show assignment" }));
  expect(document.querySelector(".workspace-grid")).not.toHaveClass(
    "chat-expanded",
  );
  await user.type(await screen.findByLabelText("Your message"), "My answer");
  await user.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Engine unavailable",
  );
  expect(screen.getByLabelText("Your message")).toHaveValue("My answer");
  expect(
    document.querySelector(".socratic-message-card.user.is-pending"),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findAllByText("Good example")).not.toHaveLength(0);
  const requests = fetch.mock.calls
    .filter(([url]) => url.endsWith("/messages"))
    .map(([, opts]) => JSON.parse(opts.body));
  expect(requests[0].request_id).toBe(requests[1].request_id);
});

test("Socratic response shows a generation timer, thinking step, and clickable evidence", async () => {
  let resolveMessage;
  mockApi("student", {
    "/api/platform/assignments/assignment-1/attempt": attempt,
    "/api/platform/assignments/assignment-1/messages": () =>
      new Promise((resolve) => {
        resolveMessage = resolve;
      }),
  });
  open("/student/assignments/assignment-1");
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Your message"), "My answer");
  await user.click(screen.getByRole("button", { name: "Send message" }));

  expect(screen.getByLabelText("Your message")).toHaveValue("");
  expect(
    document.querySelector(".socratic-message-card.user.is-pending"),
  ).toHaveTextContent("My answer");
  expect(await screen.findByRole("status")).toHaveAccessibleName(
    "Socratic tutor is thinking through your response",
  );
  expect(
    screen.getByText("Thinking through your response"),
  ).toBeInTheDocument();
  expect(screen.getByText(/\d+\.\ds elapsed/)).toBeInTheDocument();
  await act(async () => {
    resolveMessage({
      ...attempt,
      engine_state: {
        socratic: {
          active_concept: "version control",
          keywords: ["version control"],
          last_score: 76,
          next_thinking_step:
            "How does version control help two developers collaborate?",
        },
        sources: [
          {
            document_id: "doc",
            chunk_id: "chunk-2",
            title: "Version Control Notes",
            text: "Version control preserves revision history for a team.",
            page_number: 2,
          },
        ],
      },
      messages: [
        ...attempt.messages,
        { role: "user", content: "My answer" },
        {
          role: "assistant",
          content:
            "That identifies revision history. How does version control help two developers collaborate?",
        },
      ],
    });
  });

  expect(
    (await screen.findAllByText("Your next thinking step")).length,
  ).toBeGreaterThan(0);
  expect(
    screen.getByText("version control", { selector: "strong" }),
  ).toBeInTheDocument();
  expect(screen.getByText(/Generated in \d+\.\ds/)).toBeInTheDocument();
  expect(screen.getByText("Score 76/100")).toBeInTheDocument();
  expect(
    document.querySelector(".socratic-message-card.user.is-pending"),
  ).not.toBeInTheDocument();
  expect(within(document.querySelector(".messages")).getAllByText("My answer")).toHaveLength(1);
  expect(screen.queryByText("Why am I being asked this?")).not.toBeInTheDocument();
  await user.click(
    screen.getByRole("button", {
      name: "Version Control Notes · page 2",
    }),
  );
  const drawer = screen.getByRole("dialog", {
    name: "Evidence document: Version Control Notes",
  });
  expect(drawer).toBeInTheDocument();
  expect(document.querySelector(".workspace-grid")).toHaveClass(
    "evidence-open",
  );
  expect(document.body).toHaveClass("evidence-workspace-open");
  const resizer = screen.getByRole("separator", {
    name: "Resize evidence document",
  });
  expect(resizer).toHaveAttribute("aria-valuenow", "420");
  resizer.focus();
  await user.keyboard("{ArrowLeft}");
  expect(resizer).toHaveAttribute("aria-valuenow", "444");
  expect(
    screen.getByText(/preserves revision history for a team/),
  ).toBeInTheDocument();
  expect(screen.getByText("Page 2")).toBeInTheDocument();
  expect(screen.getByText("Passage chunk-2")).toBeInTheDocument();
  await user.click(
    screen.getByRole("button", {
      name: "Version Control Notes · page 2",
    }),
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(document.querySelector(".workspace-grid")).not.toHaveClass(
    "evidence-open",
  );
  expect(document.body).not.toHaveClass("evidence-workspace-open");
  await user.click(
    screen.getByRole("button", {
      name: "Version Control Notes · page 2",
    }),
  );
  await user.click(
    screen.getByRole("button", { name: "Close evidence document" }),
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Could you guide me?" }));
  expect(screen.getByLabelText("Your message")).toHaveValue(
    "Could you guide me through this step?",
  );
});

test("Enter sends a student message and Shift Enter inserts a new line", async () => {
  const fetch = mockApi("student", {
    "/api/platform/assignments/assignment-1/attempt": attempt,
    "/api/platform/assignments/assignment-1/messages": {
      ...attempt,
      messages: [
        ...attempt.messages,
        { role: "user", content: "First line\nSecond line" },
        { role: "assistant", content: "What evidence supports that?" },
      ],
    },
  });
  open("/student/assignments/assignment-1");
  const user = userEvent.setup();
  const input = await screen.findByLabelText("Your message");

  await user.type(input, "First line{Shift>}{Enter}{/Shift}Second line");
  expect(input).toHaveValue("First line\nSecond line");
  expect(
    fetch.mock.calls.filter(([url]) => url.endsWith("/messages")),
  ).toHaveLength(0);

  await user.type(input, "{Enter}");
  expect(
    await screen.findAllByText("What evidence supports that?"),
  ).not.toHaveLength(0);
  const requests = fetch.mock.calls.filter(([url]) =>
    url.endsWith("/messages"),
  );
  expect(requests).toHaveLength(1);
  expect(JSON.parse(requests[0][1].body).message).toBe(
    "First line\nSecond line",
  );
});

test("student returns to the message box after the tutor replies", async () => {
  mockApi("student", {
    "/api/platform/assignments/assignment-1/attempt": attempt,
    "/api/platform/assignments/assignment-1/messages": {
      ...attempt,
      messages: [
        ...attempt.messages,
        { role: "user", content: "My answer" },
        { role: "assistant", content: "What would you try next?" },
      ],
    },
  });
  open("/student/assignments/assignment-1");
  const user = userEvent.setup();
  const input = await screen.findByLabelText("Your message");

  await user.type(input, "My answer");
  await user.click(screen.getByRole("button", { name: "Send message" }));

  expect(await screen.findByText("What would you try next?")).toBeInTheDocument();
  await waitFor(() => expect(input).toHaveFocus());
  expect(input).toHaveValue("");
  expect(input.scrollIntoView).toHaveBeenCalled();
});

test("earlier tutor questions keep their question-card design after a new reply", async () => {
  mockApi("student", {
    "/api/platform/assignments/assignment-1/attempt": attempt,
    "POST /api/platform/assignments/assignment-1/messages": {
      ...attempt,
      messages: [
        ...attempt.messages,
        { role: "user", content: "A requirement should be clear." },
        {
          role: "assistant",
          content: "That helps the team. What else makes it useful?",
        },
      ],
    },
  });
  open("/student/assignments/assignment-1");
  const user = userEvent.setup();
  const input = await screen.findByLabelText("Your message");

  expect(screen.getAllByRole("region", { name: "Your next thinking step" })).toHaveLength(1);
  await user.type(input, "A requirement should be clear.");
  await user.click(screen.getByRole("button", { name: "Send message" }));

  await waitFor(() => {
    const questions = screen.getAllByRole("region", { name: "Your next thinking step" });
    expect(questions).toHaveLength(2);
    expect(questions[0]).toHaveTextContent("What makes a requirement useful?");
    expect(questions[1]).toHaveTextContent("What else makes it useful?");
  });
});

test("student cannot enter professor configuration routes", async () => {
  mockApi("student");
  open("/professor/tools/reflections");
  expect(
    await screen.findByRole("heading", { name: "Your assignments" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "New assignment" }),
  ).not.toBeInTheDocument();
});

test("Reflections launches its student interface in a new tab without starting inline", async () => {
  const tab = { opener: {}, location: { replace: vi.fn() }, close: vi.fn() };
  vi.spyOn(window, "open").mockReturnValue(tab);
  const fetch = mockApi("student", {
    "/api/platform/assignments/assignment-1": {
      ...assignment,
      tool: "reflections",
      student_config: { module_type: "topic_based" },
    },
    "/api/platform/assignments/assignment-1/reflection-launch": {
      code: "launch-code",
    },
  });
  open("/student/assignments/assignment-1");
  const link = await screen.findByRole("link", { name: "Start assignment" });
  expect(link).toHaveAttribute(
    "href",
    "/platform/reflections.html?assignment=assignment-1",
  );
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
  await userEvent.setup().click(link);
  await waitFor(() =>
    expect(tab.location.replace).toHaveBeenCalledWith(
      "/platform/reflections.html?assignment=assignment-1#code=launch-code",
    ),
  );
  expect(tab.opener).toBeNull();
  expect(fetch.mock.calls.some(([url]) => url.endsWith("/start"))).toBe(false);
});

test("professor catalog loads all courses without requiring Canvas context", async () => {
  const fetch = mockApi("instructor", {
    "/api/platform/context": { error: "No Canvas course context" },
    "/api/platform/assignments": [
      { ...assignment, can_manage: true },
      { ...assignment, id: "other-course-activity", course_code: "CS202", title: "Another instructor's activity", can_manage: false },
    ],
  });
  open("/professor");
  expect(await screen.findByText("Another instructor's activity")).toBeInTheDocument();
  expect(screen.getByText("Course instructor access required to open")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Another instructor's activity" })).not.toBeInTheDocument();
  expect(fetch.mock.calls.some(([url]) => url === "/api/platform/assignments")).toBe(true);
  expect(fetch.mock.calls.some(([url]) => url.startsWith("/api/platform/assignments?"))).toBe(false);
});

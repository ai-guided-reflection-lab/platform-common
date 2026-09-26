import React from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { App } from "./main";
import { SESSION_KEY } from "./api";

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
    "/api/platform/topic-templates": [],
    "/api/platform/assignments/assignment-1": assignment,
    "/api/platform/assignments/assignment-1/attempt": null,
    "/api/platform/assignments/assignment-1/start": attempt,
    ...override,
  };
  const fetch = vi.fn(async (url, options = {}) => {
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

test("professor selects each explicit tool dashboard", async () => {
  mockApi();
  open("/professor");
  const user = userEvent.setup();
  expect(
    await screen.findByRole("heading", { name: "Choose how you’ll teach." }),
  ).toBeInTheDocument();
  const reflection = screen.getByRole("link", { name: /RF Reflections/ });
  expect(
    screen.getByRole("link", { name: /SC Socratic Chat/ }),
  ).toHaveAttribute("href", "/professor/tools/socratic");
  expect(
    screen.getByRole("link", { name: /SA Student Agent Bot/ }),
  ).toHaveAttribute("href", "/professor/tools/student-agent");
  await user.click(reflection);
  expect(
    await screen.findByRole("heading", { level: 1, name: "Reflections" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "New assignment" })).toBeDisabled();
  await user.selectOptions(screen.getByLabelText("Course"), course);
  await user.click(screen.getByRole("button", { name: "New assignment" }));
  expect(
    await screen.findByRole("heading", { name: "Reflections settings" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Reflection type")).toHaveValue("topic_based");
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
    await screen.findByRole("heading", { name: "Dashboard" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Courses & access" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Resume" })).not.toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Assignments" }));
  expect(
    screen.getByRole("region", { name: "SE101 assignments" }).closest("article"),
  ).toHaveClass("is-expanded");
  expect(await screen.findByRole("link", { name: "Resume" })).toHaveAttribute(
    "href",
    "/student/assignments/reflection-1",
  );
  expect(screen.getByRole("link", { name: "View result" })).toHaveAttribute(
    "href",
    "/student/assignments/tutor-1",
  );
  await user.click(screen.getByRole("link", { name: "Open assignment" }));
  await user.click(
    await screen.findByRole("button", { name: "Start assignment" }),
  );
  expect(
    await screen.findAllByText("What makes a requirement useful?"),
  ).not.toHaveLength(0);
  expect(screen.queryByLabelText("Student ID")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Reflection type")).not.toBeInTheDocument();
});

test("student requests course access from the integrated dashboard", async () => {
  const availableCourse = {
    course_id: "available-course",
    course_code: "ITCS2000",
    title: "Discoverable Course",
    description: "Request access from this dashboard.",
    instructor_name: "Professor Morgan",
    document_count: 1,
    membership_role: null,
    membership_status: null,
  };
  const fetch = mockApi("student", {
    "/api/courses": { courses: [availableCourse] },
    "POST /api/courses/available-course/request-access": {
      membership: { status: "pending" },
      message: "Your access request is pending.",
    },
  });
  open("/student");
  const user = userEvent.setup();

  await user.click(await screen.findByRole("button", { name: "Request access" }));

  expect(
    fetch.mock.calls.some(
      ([url, options]) =>
        url === "/api/courses/available-course/request-access" &&
        options.method === "POST",
    ),
  ).toBe(true);
});

test("professor imports a visible UNC Charlotte Canvas assignment as a Socratic draft", async () => {
  const imported = {
    ...assignment,
    id: "canvas-draft",
    title: "Canvas architecture reflection",
    instructions: "Explain one tradeoff.",
    status: "draft",
    audience: "course",
    recipient_ids: [],
    config: {
      document_ids: [],
      prompt: "Use the published course materials.",
      minimum_messages: 1,
    },
  };
  const fetch = mockApi("instructor", {
    "POST /api/platform/integrations/canvas/courses": [
      {
        id: "77",
        name: "Software Engineering",
        course_code: "ITSC 3155",
      },
    ],
    "POST /api/platform/integrations/canvas/assignments": [
      {
        id: "88",
        name: "Canvas architecture reflection",
        due_at: null,
      },
    ],
    "POST /api/platform/integrations/canvas/import": imported,
    "/api/platform/assignments/canvas-draft": imported,
  });
  open("/professor/tools/socratic");
  const user = userEvent.setup();

  await screen.findByRole("option", { name: /SE101/ });
  await user.selectOptions(screen.getByLabelText("Course"), course);
  await user.type(screen.getByLabelText("Canvas access token"), "canvas-token-value");
  await user.click(screen.getByRole("button", { name: "Load Canvas courses" }));
  await user.selectOptions(await screen.findByLabelText("Canvas course"), "77");
  await user.click(screen.getByRole("button", { name: "Load visible assignments" }));
  await user.selectOptions(
    await screen.findByLabelText("Canvas assignment"),
    "88",
  );
  await user.click(
    screen.getByRole("button", { name: "Import as Socratic Chat draft" }),
  );

  expect(
    await screen.findByDisplayValue("Canvas architecture reflection"),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Assigned chatbot")).toHaveValue(
    "Socratic Chat",
  );
  const importCall = fetch.mock.calls.find(
    ([url]) => url === "/api/platform/integrations/canvas/import",
  );
  expect(JSON.parse(importCall[1].body)).toMatchObject({
    access_token: "canvas-token-value",
    course_id: "77",
    assignment_id: "88",
    platform_course_id: course,
    tool: "socratic",
  });
  expect(localStorage.length).toBe(1);
  expect(localStorage.getItem(SESSION_KEY)).not.toContain("canvas-token-value");
});

test("professor can create the destination ClubALL course from Canvas", async () => {
  const createdCourse = {
    course_id: "canvas-platform-course",
    course_code: "ITSC 3155",
    title: "Software Engineering",
    membership_role: "instructor",
  };
  const fetch = mockApi("instructor", {
    "/api/courses": { courses: [] },
    "POST /api/courses": createdCourse,
    "POST /api/platform/integrations/canvas/courses": [
      {
        id: "77",
        name: "Software Engineering",
        course_code: "ITSC 3155",
      },
    ],
  });
  open("/professor/tools/socratic");
  const user = userEvent.setup();

  await user.type(
    await screen.findByLabelText("Canvas access token"),
    "canvas-token-value",
  );
  await user.click(screen.getByRole("button", { name: "Load Canvas courses" }));
  await user.selectOptions(await screen.findByLabelText("Canvas course"), "77");
  await user.click(
    screen.getByRole("button", {
      name: "Create ClubALL course from Canvas",
    }),
  );

  expect(await screen.findByLabelText("Course")).toHaveValue(
    "canvas-platform-course",
  );
  const createCall = fetch.mock.calls.find(
    ([url, options]) => url === "/api/courses" && options.method === "POST",
  );
  expect(JSON.parse(createCall[1].body)).toEqual({
    course_code: "ITSC 3155",
    title: "Software Engineering",
    description: "Imported from UNC Charlotte Canvas course 77.",
  });
});

test("failed publish retains a saved draft and shows an actionable error", async () => {
  const saved = {
    ...assignment,
    status: "draft",
    audience: "course",
    recipient_ids: [],
    config: { document_ids: [], prompt: "", minimum_messages: 1 },
  };
  const fetch = mockApi("instructor", {
    "POST /api/platform/assignments": saved,
    "/api/platform/assignments/assignment-1": saved,
    "/api/platform/assignments/assignment-1/publish": {
      error: "Upload course materials first.",
    },
  });
  open(`/professor/tools/socratic/assignments/new?course=${course}`);
  const user = userEvent.setup();
  await user.type(
    await screen.findByLabelText("Title"),
    "Discuss requirements",
  );
  await user.click(screen.getByRole("button", { name: "Publish assignment" }));
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

  expect(await screen.findByRole("status")).toHaveAccessibleName(
    "Socratic tutor is thinking through your response",
  );
  expect(screen.getByText("Thinking through your response")).toBeInTheDocument();
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

  expect(await screen.findByText("Your next thinking step")).toBeInTheDocument();
  expect(
    screen.getByText("version control", { selector: "strong" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Generated in \d+\.\ds/),
  ).toBeInTheDocument();
  expect(screen.getByText("Score 76/100")).toBeInTheDocument();
  expect(
    screen.getByText("Why am I being asked this?"),
  ).toBeInTheDocument();
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
  expect(fetch.mock.calls.filter(([url]) => url.endsWith("/messages"))).toHaveLength(0);

  await user.type(input, "{Enter}");
  expect(
    await screen.findAllByText("What evidence supports that?"),
  ).not.toHaveLength(0);
  const requests = fetch.mock.calls.filter(([url]) => url.endsWith("/messages"));
  expect(requests).toHaveLength(1);
  expect(JSON.parse(requests[0][1].body).message).toBe(
    "First line\nSecond line",
  );
});

test("student cannot enter professor configuration routes", async () => {
  mockApi("student");
  open("/professor/tools/reflections");
  expect(
    await screen.findByRole("heading", { name: "Dashboard" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "New assignment" }),
  ).not.toBeInTheDocument();
});

test("Reflections launches its student interface in a new tab without starting inline", async () => {
  const fetch = mockApi("student", {
    "/api/platform/assignments/assignment-1": { ...assignment, tool: "reflections", student_config: { module_type: "topic_based" } },
  });
  open("/student/assignments/assignment-1");
  const link = await screen.findByRole("link", { name: "Start assignment" });
  expect(link).toHaveAttribute("href", "/platform/reflections.html?assignment=assignment-1");
  expect(link).toHaveAttribute("target", "_blank");
  expect(link).toHaveAttribute("rel", "noopener noreferrer");
  expect(fetch.mock.calls.some(([url]) => url.endsWith("/start"))).toBe(false);
});

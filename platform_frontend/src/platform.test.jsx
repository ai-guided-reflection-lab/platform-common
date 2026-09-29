import React from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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
          membership_role: "instructor",
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
    "/api/platform/adaptive-plans": [],
    "/api/platform/assignments/assignment-1": assignment,
    "/api/platform/assignments/assignment-1/attempt": null,
    "/api/platform/assignments/assignment-1/start": attempt,
    ...override,
  };
  const fetch = vi.fn(async (url, options = {}) => {
    const entry =
      responses[`${options.method || "GET"} ${url}`] ?? responses[url];
    if (entry === undefined) throw new Error("Unexpected API call: " + url);
    const data = typeof entry === "function" ? entry(options) : entry;
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
    screen.getByRole("link", { name: /SDL Self-Directed Learning/ }),
  ).toHaveAttribute("href", "/professor/tools/self-directed-learning");
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
    await screen.findByRole("heading", { name: "Your next steps, all here." }),
  ).toBeInTheDocument();
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
    await screen.findByText("What makes a requirement useful?"),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText("Student ID")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Reflection type")).not.toBeInTheDocument();
});

test("student starts a standalone self-directed assignment inside the platform", async () => {
  const selfDirected = {
    id: "sdl-1",
    title: "Large Language Models",
    instructions: "Prepare, complete the diagnostic, and follow your path.",
    documents: [],
    learning_plan: {
      objectives: [{ id: "LLM-1", title: "Explain LLMs" }],
      study_resources: [{ title: "LLM introduction", provider: "Google", url: "https://example.test/llm" }],
      diagnostic_quiz: Array.from({ length: 5 }, (_, index) => ({
        id: `Q-${index + 1}`,
        question: `Question ${index + 1}`,
        options: ["A", "B", "C", "D"],
      })),
      required_task: { title: "LLM analysis", description: "Analyze one use.", submission_prompt: "Submit your analysis." },
    },
  };
  const started = {
    id: "attempt-sdl-1",
    status: "in_progress",
    phase: "study_resources",
    learning_path: null,
    quiz_score: null,
    required_task_status: "not_started",
    objective_progress: [{ objective_id: "LLM-1", title: "Explain LLMs", status: "not_started" }],
    messages: [],
  };
  mockApi("student", {
    "/api/platform/self-directed/assignments/sdl-1": selfDirected,
    "/api/platform/self-directed/assignments/sdl-1/attempt": null,
    "POST /api/platform/self-directed/assignments/sdl-1/start": started,
  });
  open("/student/self-directed-learning/sdl-1");
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Start learning" }));
  expect(await screen.findByRole("heading", { name: "Study these resources first" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /LLM introduction/ })).toHaveAttribute("href", "https://example.test/llm");
});

test("student sees adaptive objectives and required task status", async () => {
  const learningPlan = {
    title: "Object-Oriented Programming",
    objectives: [
      { id: "OBJ-1", description: "Explain classes and objects." },
      { id: "OBJ-2", description: "Create a class with methods." },
    ],
    required_task: { title: "Implement a BankAccount class" },
  };
  const adaptiveAssignment = {
    ...assignment,
    tool: "student-agent",
    student_config: {
      topic_name: learningPlan.title,
      learning_plan: learningPlan,
      resources: [],
    },
  };
  const adaptiveAttempt = {
    ...attempt,
    required_task_status: "in_progress",
    engine_state: {
      adaptive: true,
      current_objective_id: "OBJ-2",
      required_task_status: "in_progress",
      objective_progress: [
        { objective_id: "OBJ-1", status: "demonstrated" },
        { objective_id: "OBJ-2", status: "developing" },
      ],
    },
  };
  mockApi("student", {
    "/api/platform/assignments/assignment-1": adaptiveAssignment,
    "/api/platform/assignments/assignment-1/attempt": adaptiveAttempt,
  });
  open("/student/assignments/assignment-1");

  expect(await screen.findByText("Implement a BankAccount class")).toBeInTheDocument();
  expect(screen.getByText(/Current objective:/)).toBeInTheDocument();
  expect(screen.getAllByText("Create a class with methods.").length).toBeGreaterThan(0);
  expect(screen.getByText("demonstrated")).toBeInTheDocument();
  expect(screen.getByText("developing")).toBeInTheDocument();
  expect(screen.getAllByText(/in progress/i).length).toBeGreaterThan(0);
});

test("student sees the current software engineering focus and authored diagnostic", async () => {
  const learningPlan = {
    title: "Requirements Engineering",
    objectives: [
      {
        id: "SE-REQ-TYPES",
        description: "Distinguish functional and non-functional requirements and justify the classification.",
      },
      {
        id: "SE-REQ-QUALITY",
        description: "Identify ambiguity or incompleteness in a requirement and improve it.",
      },
    ],
    required_task: { title: "Review and revise a small requirements set" },
  };
  const adaptiveAssignment = {
    ...assignment,
    tool: "student-agent",
    title: "Requirements engineering practice",
    student_config: {
      topic_name: learningPlan.title,
      learning_plan: learningPlan,
      resources: [],
    },
  };
  const adaptiveAttempt = {
    ...attempt,
    messages: [
      {
        role: "assistant",
        content: "Classify each requirement as functional or non-functional and justify each choice.",
      },
    ],
    engine_state: {
      adaptive: true,
      assessment_phase: "initial_diagnostic",
      phase_label: "Initial diagnostic",
      current_objective_id: "SE-REQ-TYPES",
      current_assessment_id: "SE-DIAG-TYPES",
      latest_decision: { action: "ASSESS" },
      required_task_status: "not_started",
      objective_progress: [
        { objective_id: "SE-REQ-TYPES", status: "not_observed" },
        { objective_id: "SE-REQ-QUALITY", status: "not_observed" },
      ],
    },
  };
  mockApi("student", {
    "/api/platform/assignments/assignment-1": adaptiveAssignment,
    "/api/platform/assignments/assignment-1/attempt": adaptiveAttempt,
  });

  open("/student/assignments/assignment-1");

  expect(await screen.findByText("Current focus")).toBeInTheDocument();
  expect(screen.getAllByText(learningPlan.objectives[0].description).length).toBeGreaterThan(0);
  expect(screen.getAllByText("Initial diagnostic").length).toBeGreaterThan(0);
  expect(screen.getByText("Answer the question on your own.")).toBeInTheDocument();
  expect(screen.getByText(adaptiveAttempt.messages[0].content)).toBeInTheDocument();
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
  await user.type(await screen.findByLabelText("Your message"), "My answer");
  await user.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Engine unavailable",
  );
  await user.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByText("Good example")).toBeInTheDocument();
  const requests = fetch.mock.calls
    .filter(([url]) => url.endsWith("/messages"))
    .map(([, opts]) => JSON.parse(opts.body));
  expect(requests[0].request_id).toBe(requests[1].request_id);
});

test("student cannot enter professor configuration routes", async () => {
  mockApi("student");
  open("/professor/tools/reflections");
  expect(
    await screen.findByRole("heading", { name: "Your next steps, all here." }),
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

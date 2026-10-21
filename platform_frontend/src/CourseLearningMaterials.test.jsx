import { useState } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import CourseLearningMaterials from "./CourseLearningMaterials";
import { SocraticConfig } from "./ToolConfig";

const doc = {
  file_id: "file-1",
  document_id: "doc-1",
  filename: "review.html",
  file_size: 900,
};
const plans = [
  {
    objective_id: "goal-1",
    file_id: doc.file_id,
    keywords: ["code review", "correctness"],
    status: "draft",
    objective: "Hidden first goal",
    diagnostic_question: "Hidden first question?",
  },
  {
    objective_id: "goal-2",
    file_id: doc.file_id,
    keywords: ["Code Review", "maintainability"],
    status: "approved",
    objective: "Hidden second goal",
  },
  {
    objective_id: "goal-3",
    file_id: doc.file_id,
    keywords: ["rejected keyword"],
    status: "rejected",
  },
];
function setup(initial = plans) {
  let objectives = initial;
  let generate = async () => ({
    keywords: ["code review", "correctness"],
    message: "Suggested keywords.",
  });
  const fetch = vi.fn(async (url, options = {}) => {
    let data;
    if (url.endsWith("/keyword-suggestions")) data = await generate();
    else if (url.endsWith("/documents/upload")) data = { message: "Uploaded." };
    else if (url.endsWith("/documents")) data = { files: [doc] };
    else if (url.endsWith("/learning-objectives")) data = { objectives };
    else throw new Error("Unexpected request: " + url);
    return { ok: true, json: async () => data };
  });
  vi.stubGlobal("fetch", fetch);
  return {
    fetch,
    setGenerate: (callback) => {
      generate = callback;
    },
  };
}
function Config({
  initial = { keywords: [] },
  frozen = false,
  onChange = () => {},
  onPendingKeywordChange,
  keywordPreparation,
  onConfirmKeywords = () => {},
}) {
  const [value, setValue] = useState(initial);
  return (
    <SocraticConfig
      courseId="course-1"
      value={value}
      frozen={frozen}
      onPendingKeywordChange={onPendingKeywordChange}
      keywordPreparation={keywordPreparation}
      onConfirmKeywords={onConfirmKeywords}
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
    />
  );
}

test("shows optional and approved boxes with combined suggestions instead of objective cards", async () => {
  setup();
  render(<Config />);
  await screen.findByRole("button", { name: "Approve keyword code review" });
  expect(
    screen.getByRole("region", { name: "Optional keywords" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("region", { name: "Approved keywords" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("textbox", { name: "New keyword" }),
  ).toBeInTheDocument();
  expect(screen.queryByText("Hidden first goal")).not.toBeInTheDocument();
  expect(screen.queryByText("Hidden second goal")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /rejected keyword/ }),
  ).not.toBeInTheDocument();
  expect(
    screen.getAllByRole("button", { name: "Approve keyword code review" }),
  ).toHaveLength(1);
  expect(
    screen.getByRole("button", { name: "Confirm keywords" }),
  ).toBeDisabled();
});

test("only explicitly added keywords enter the assignment config, and X deletes them", async () => {
  const { fetch } = setup();
  const onChange = vi.fn();
  const user = userEvent.setup();
  render(<Config onChange={onChange} />);
  await screen.findByRole("button", { name: "Approve keyword correctness" });
  expect(onChange).not.toHaveBeenCalled();
  await user.click(
    screen.getByRole("button", { name: "Approve keyword correctness" }),
  );
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({
      keywords: ["correctness"],
      learning_objective_id: null,
    }),
  );
  await user.type(
    screen.getByRole("textbox", { name: "New keyword" }),
    "team conventions{Enter}",
  );
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({
      keywords: ["correctness"],
      optional_keywords: ["team conventions"],
    }),
  );
  await user.click(
    screen.getByRole("button", { name: "Approve keyword team conventions" }),
  );
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ keywords: ["correctness", "team conventions"] }),
  );
  await user.click(screen.getByRole("button", { name: "Delete keyword correctness" }));
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({
      keywords: ["team conventions"],
      dismissed_keywords: ["correctness"],
    }),
  );
  expect(screen.queryByRole("button", { name: "Approve keyword correctness" })).not.toBeInTheDocument();
  expect(
    fetch.mock.calls.some(([, options]) => options.method === "PATCH"),
  ).toBe(false);
});

test("teachers can dismiss optional suggestions without losing course materials", async () => {
  setup();
  const onChange = vi.fn();
  const user = userEvent.setup();
  const initial = {
    keywords: ["code review"],
    optional_keywords: ["team conventions"],
    document_ids: ["doc-1"],
    prompt: "How do reviews help?",
  };
  const view = render(<Config initial={initial} onChange={onChange} />);
  await user.click(
    await screen.findByRole("button", { name: "Delete keyword correctness" }),
  );
  const saved = onChange.mock.lastCall[0];
  expect(saved).toEqual(expect.objectContaining({
    keywords: ["code review"],
    dismissed_keywords: ["correctness"],
    document_ids: ["doc-1"],
    prompt: "How do reviews help?",
  }));
  expect(screen.queryByRole("button", { name: "Approve keyword correctness" })).not.toBeInTheDocument();

  view.unmount();
  render(<Config initial={saved} />);
  await screen.findByRole("button", { name: "Approve keyword team conventions" });
  expect(screen.queryByRole("button", { name: "Approve keyword correctness" })).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Delete keyword team conventions" }));
  expect(screen.queryByRole("button", { name: "Approve keyword team conventions" })).not.toBeInTheDocument();
  await user.type(screen.getByRole("textbox", { name: "New keyword" }), "team conventions{Enter}");
  expect(screen.getByRole("button", { name: "Approve keyword team conventions" })).toBeInTheDocument();
});

test("duplicate keywords are rejected and pending input is reported to the assignment form", async () => {
  setup();
  const pending = vi.fn();
  const user = userEvent.setup();
  render(
    <Config
      initial={{ keywords: ["code review"] }}
      onPendingKeywordChange={pending}
    />,
  );
  await user.type(
    screen.getByRole("textbox", { name: "New keyword" }),
    "CODE REVIEW",
  );
  await waitFor(() => expect(pending).toHaveBeenLastCalledWith(true));
  await user.click(
    screen.getByRole("button", { name: "Add optional keyword" }),
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "already in Optional or Approved",
  );
  await user.clear(screen.getByRole("textbox", { name: "New keyword" }));
  await waitFor(() => expect(pending).toHaveBeenLastCalledWith(false));
});

test("suggesting keywords adds no assignment scope until an instructor selects a suggestion", async () => {
  setup([]);
  const onChange = vi.fn();
  const user = userEvent.setup();
  render(<Config onChange={onChange} />);
  await user.click(
    await screen.findByRole("button", { name: "Keywords Generation" }),
  );
  expect(
    await screen.findByRole("button", { name: "Approve keyword correctness" }),
  ).toBeInTheDocument();
  expect(onChange).not.toHaveBeenCalled();
});

test("uses the fast keyword endpoint without objective-generation polling", async () => {
  const state = setup([]);
  const user = userEvent.setup();
  render(<Config />);
  await user.click(
    await screen.findByRole("button", { name: "Keywords Generation" }),
  );
  expect(
    await screen.findByRole("button", { name: "Approve keyword correctness" }),
  ).toBeInTheDocument();
  expect(state.fetch).toHaveBeenCalledWith(
    expect.stringContaining("/keyword-suggestions"),
    expect.any(Object),
  );
  expect(
    state.fetch.mock.calls.some(([url]) =>
      url.includes("/learning-objectives/generation-status"),
    ),
  ).toBe(false);
});

test("legacy selected goal becomes the initial single keyword list in an editable draft", async () => {
  setup();
  const onChange = vi.fn();
  render(
    <Config
      initial={{ learning_objective_id: "goal-2", document_ids: ["doc-1"] }}
      onChange={onChange}
    />,
  );
  await screen.findByRole("button", { name: "Delete keyword maintainability" });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({
      keywords: ["Code Review", "maintainability"],
      learning_objective_id: null,
    }),
  );
});

test("published assignment keywords are displayed read-only", async () => {
  setup();
  render(<Config initial={{ keywords: ["code review"] }} frozen />);
  expect(
    await screen.findByRole("button", { name: "Delete keyword code review" }),
  ).toBeDisabled();
  expect(
    screen.queryByRole("textbox", { name: "New keyword" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText(/Suggested keywords from your documents/),
  ).not.toBeInTheDocument();
});

test("failed suggestions preserve the assignment's saved keywords", async () => {
  const state = setup();
  state.setGenerate(async () => {
    throw new Error("Model unavailable");
  });
  const user = userEvent.setup();
  render(<Config initial={{ keywords: ["code review"] }} />);
  await user.click(
    await screen.findByRole("button", { name: "Keywords Generation" }),
  );
  expect(await screen.findByText("Model unavailable")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Delete keyword code review" }),
  ).toBeInTheDocument();
});

test("upload does not submit the assignment form", async () => {
  const { fetch } = setup();
  const submit = vi.fn((e) => e.preventDefault());
  const user = userEvent.setup();
  render(
    <form onSubmit={submit}>
      <CourseLearningMaterials courseId="course-1" />
    </form>,
  );
  await user.upload(
    await screen.findByLabelText("Choose course documents"),
    new File(["Lesson"], "lesson.txt", { type: "text/plain" }),
  );
  await user.click(screen.getByRole("button", { name: "Upload documents" }));
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(([url]) => url.endsWith("/documents/upload")),
    ).toBe(true),
  );
  expect(submit).not.toHaveBeenCalled();
});

test("confirmation saves through the parent handler and changes invalidate the confirmed state", async () => {
  setup();
  const confirm = vi.fn();
  const user = userEvent.setup();
  render(
    <Config
      initial={{ keywords: ["code review"] }}
      keywordPreparation={{
        ready: true,
        keywords: ["code review"],
        course_id: "course-1",
        passage_count: 4,
      }}
      onConfirmKeywords={confirm}
    />,
  );
  expect(
    screen.getByRole("button", { name: "Keywords confirmed" }),
  ).toBeDisabled();
  expect(screen.getByText(/4 indexed passages ready/)).toBeInTheDocument();
  await user.click(
    await screen.findByRole("button", { name: "Approve keyword correctness" }),
  );
  expect(
    screen.getByRole("button", { name: "Confirm keywords" }),
  ).toBeEnabled();
  await user.click(screen.getByRole("button", { name: "Confirm keywords" }));
  expect(confirm).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("button", { name: "Delete keyword correctness" }));
  expect(
    screen.queryByRole("button", { name: "Approve keyword correctness" }),
  ).not.toBeInTheDocument();
});

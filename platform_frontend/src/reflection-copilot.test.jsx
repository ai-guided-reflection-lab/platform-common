import React from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReflectionCopilot from "./ReflectionCopilot";
import { defaults } from "./ToolConfig";
import { api } from "./api";

vi.mock("./api", async (original) => ({ ...(await original()), api: vi.fn() }));
const proposal = {
  title: "Testable requirements reflection",
  instructions: "Connect a requirement to a concrete verification method.",
  config: {
    ...defaults.reflections,
    document_ids: ["d1"],
    required_topics: ["Testability"],
    sub_topics: ["How can you verify this requirement?"],
    expected_depth: "applied",
    probing_style: "socratic",
    must_include_application: true,
  },
  rationale: "Connects the definition to practical decisions.",
};
const response = {
  proposal,
  evidence: [
    {
      document_id: "d1",
      title: "Requirements.pdf",
      excerpt: "Requirements should be verifiable.",
    },
  ],
};
const base = {
  courseId: "course-1",
  selected: ["d1"],
  documents: [{ document_id: "d1" }],
  draft: {
    title: "Original title",
    instructions: "Original instructions",
    config: {
      ...defaults.reflections,
      historical_data: "PRIVATE CSV NEVER SENT",
    },
  },
};
beforeEach(() => {
  api.mockReset();
  api.mockResolvedValue(response);
});
const enterGoal = () =>
  fireEvent.change(screen.getByLabelText("Reflection goal"), {
    target: { value: "Reflect on testable requirements." },
  });

test("requires selected indexed documents and a sufficient goal", () => {
  const { rerender } = render(
    <ReflectionCopilot {...base} onApply={vi.fn()} />,
  );
  expect(
    screen.getByRole("button", { name: "Prepare proposal" }),
  ).toBeDisabled();
  enterGoal();
  expect(
    screen.getByRole("button", { name: "Prepare proposal" }),
  ).toBeEnabled();
  rerender(<ReflectionCopilot {...base} selected={[]} onApply={vi.fn()} />);
  expect(
    screen.getByRole("button", { name: "Prepare proposal" }),
  ).toBeDisabled();
  rerender(<ReflectionCopilot {...base} documents={[]} onApply={vi.fn()} />);
  expect(
    screen.getByRole("button", { name: "Prepare proposal" }),
  ).toBeDisabled();
});

test("sends only safe fields and previews evidence before applying", async () => {
  const onApply = vi.fn();
  render(<ReflectionCopilot {...base} onApply={onApply} />);
  enterGoal();
  await userEvent.click(
    screen.getByRole("button", { name: "Prepare proposal" }),
  );
  expect(api).toHaveBeenCalledExactlyOnceWith(
    "/platform/copilot/reflections/propose",
    {
      method: "POST",
      body: {
        course_id: "course-1",
        document_ids: ["d1"],
        goal: "Reflect on testable requirements.",
        current: {
          title: "Original title",
          instructions: "Original instructions",
          module_type: "topic_based",
        },
      },
    },
  );
  expect(JSON.stringify(api.mock.calls)).not.toContain("PRIVATE CSV");
  expect(JSON.stringify(api.mock.calls)).not.toContain("historical_data");
  expect(
    await screen.findByText("Requirements should be verifiable."),
  ).toBeInTheDocument();
  expect(screen.getByText(proposal.rationale)).toBeInTheDocument();
  expect(onApply).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Apply proposal" }));
  expect(onApply).toHaveBeenCalledExactlyOnceWith(proposal);
  expect(api).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("status")).toHaveTextContent("Proposal applied");
});

test.each(["selection", "goal", "mode"])(
  "changes to %s make the proposal stale until regeneration",
  async (kind) => {
    const onApply = vi.fn();
    const { rerender } = render(
      <ReflectionCopilot {...base} onApply={onApply} />,
    );
    enterGoal();
    await userEvent.click(
      screen.getByRole("button", { name: "Prepare proposal" }),
    );
    await screen.findByRole("button", { name: "Apply proposal" });
    if (kind === "selection")
      rerender(
        <ReflectionCopilot
          {...base}
          selected={["d2"]}
          documents={[{ document_id: "d2" }]}
          onApply={onApply}
        />,
      );
    if (kind === "goal")
      fireEvent.change(screen.getByLabelText("Reflection goal"), {
        target: { value: "Reflect on a different learning goal." },
      });
    if (kind === "mode")
      rerender(
        <ReflectionCopilot
          {...base}
          draft={{
            ...base.draft,
            config: { ...base.draft.config, module_type: "milestone_based" },
          }}
          onApply={onApply}
        />,
      );
    expect(
      screen.getByRole("button", { name: "Apply proposal" }),
    ).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("out of date");
    await userEvent.click(
      screen.getByRole("button", { name: "Dismiss proposal" }),
    );
    expect(
      screen.queryByRole("button", { name: "Apply proposal" }),
    ).not.toBeInTheDocument();
    expect(onApply).not.toHaveBeenCalled();
  },
);

test("input changes during inference cannot apply the old result", async () => {
  let resolve;
  api.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const { rerender } = render(
    <ReflectionCopilot {...base} onApply={vi.fn()} />,
  );
  enterGoal();
  await userEvent.click(
    screen.getByRole("button", { name: "Prepare proposal" }),
  );
  expect(screen.getByRole("status")).toHaveTextContent(
    "Reading selected materials",
  );
  expect(screen.getByLabelText("Reflection goal")).toBeEnabled();
  rerender(<ReflectionCopilot {...base} selected={[]} onApply={vi.fn()} />);
  resolve(response);
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Apply proposal" }),
    ).toBeDisabled(),
  );
});

test("reverting an edited goal still requires a fresh proposal", async () => {
  render(<ReflectionCopilot {...base} onApply={vi.fn()} />);
  enterGoal();
  await userEvent.click(
    screen.getByRole("button", { name: "Prepare proposal" }),
  );
  await screen.findByRole("button", { name: "Apply proposal" });
  fireEvent.change(screen.getByLabelText("Reflection goal"), {
    target: { value: "Another reflection goal." },
  });
  enterGoal();
  expect(screen.getByRole("button", { name: "Apply proposal" })).toBeDisabled();
  await userEvent.click(
    screen.getByRole("button", { name: "Prepare proposal" }),
  );
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Apply proposal" }),
    ).toBeEnabled(),
  );
});

test("provider errors are actionable and keep preparation usable", async () => {
  api.mockRejectedValue(Error("The local Assignment Copilot is unavailable."));
  render(<ReflectionCopilot {...base} onApply={vi.fn()} />);
  enterGoal();
  await userEvent.click(
    screen.getByRole("button", { name: "Prepare proposal" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "continue configuring Reflections manually",
  );
  expect(
    screen.getByRole("button", { name: "Prepare proposal" }),
  ).toBeEnabled();
});

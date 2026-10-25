import React from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AssignmentCopilot, {
  applyAssignmentProposal,
} from "./AssignmentCopilot";
import { api } from "./api";

vi.mock("./api", async (original) => ({ ...(await original()), api: vi.fn() }));
const proposal = {
  tool: "socratic",
  title: "Processes and threads",
  instructions: "Explain resource isolation.",
  objectives: ["Distinguish a process from a thread"],
  rationale: "Questions expose misconceptions.",
  config: {
    keywords: ["Processes", "Threads"],
    prompt: "Compare processes and threads",
    minimum_messages: 3,
    document_ids: ["d1"],
  },
};
const response = {
  request_id: "request-1",
  proposal,
  evidence: [
    {
      document_id: "d1",
      title: "OS.pdf",
      excerpt: "Threads share the process address space.",
    },
  ],
  warnings: [],
};
const base = {
  courseId: "course-1",
  selected: ["d1"],
  documents: [{ document_id: "d1" }],
  draft: {
    title: "Original title",
    instructions: "Original instructions",
    tool: "",
    config: {},
  },
  onApply: vi.fn(),
};
const goal = () =>
  fireEvent.change(screen.getByLabelText("Learning outcome"), {
    target: { value: "Help students distinguish processes from threads." },
  });
beforeEach(() => {
  api.mockReset();
  api.mockResolvedValue(response);
  base.onApply.mockReset();
});

test("automatic recommendation previews choice, objectives, configuration and real sources without applying", async () => {
  render(<AssignmentCopilot {...base} />);
  goal();
  await userEvent.click(
    screen.getByRole("button", { name: "Prepare proposal" }),
  );
  await screen.findByText("Socratic Chat");
  expect(
    screen.getByText("Distinguish a process from a thread"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Threads share the process address space."),
  ).toBeInTheDocument();
  expect(base.onApply).not.toHaveBeenCalled();
  const [path, { body }] = api.mock.calls[0];
  expect(path).toBe("/platform/copilot/propose");
  expect(body.current.tool).toBeNull();
  expect(body.request_id).toMatch(/^[0-9a-f-]{36}$/);
  expect(JSON.stringify(body)).not.toContain("config");
  await userEvent.click(screen.getByRole("button", { name: "Apply proposal" }));
  expect(base.onApply).toHaveBeenCalledExactlyOnceWith(proposal, undefined);
  expect(api).toHaveBeenCalledTimes(1);
});

test.each([
  ["title", "Apply title"],
  ["instructions", "Apply instructions"],
  ["objectives", "Apply objectives"],
  ["config", "Apply activity and settings"],
])("supports applying %s individually", async (field, name) => {
  render(<AssignmentCopilot {...base} />);
  goal();
  await userEvent.click(
    screen.getByRole("button", { name: "Prepare proposal" }),
  );
  await userEvent.click(await screen.findByRole("button", { name }));
  expect(base.onApply).toHaveBeenCalledWith(proposal, field);
  expect(api).toHaveBeenCalledTimes(1);
});

test("revision requests regenerate from selected materials and retain the instructor-selected activity", async () => {
  render(
    <AssignmentCopilot {...base} draft={{ ...base.draft, tool: "socratic" }} />,
  );
  goal();
  await userEvent.click(
    screen.getByRole("button", { name: "Prepare proposal" }),
  );
  await screen.findByRole("button", { name: "Apply proposal" });
  fireEvent.change(screen.getByLabelText("Revision request"), {
    target: { value: "Focus on memory isolation." },
  });
  expect(screen.getByRole("button", { name: "Apply proposal" })).toBeDisabled();
  await userEvent.click(
    screen.getByRole("button", { name: "Revise proposal" }),
  );
  await waitFor(() => expect(api).toHaveBeenCalledTimes(2));
  expect(api.mock.calls[1][1].body).toMatchObject({
    revision: "Focus on memory isolation.",
    current: { tool: "socratic" },
  });
  expect(api.mock.calls[1][1].body.request_id).not.toBe(
    api.mock.calls[0][1].body.request_id,
  );
});

test("changes during inference cannot apply a stale result", async () => {
  let resolve;
  api.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const { rerender } = render(<AssignmentCopilot {...base} />);
  goal();
  await userEvent.click(
    screen.getByRole("button", { name: "Prepare proposal" }),
  );
  rerender(<AssignmentCopilot {...base} selected={[]} />);
  resolve(response);
  expect(
    await screen.findByRole("button", { name: "Apply proposal" }),
  ).toBeDisabled();
});

test("AIducate stays manual and unavailable to the copilot", () => {
  render(
    <AssignmentCopilot {...base} draft={{ ...base.draft, tool: "aiducate" }} />,
  );
  goal();
  expect(
    screen.getByRole("button", { name: "Prepare proposal" }),
  ).toBeDisabled();
  expect(screen.getByText(/runtime contract is finalized/)).toBeInTheDocument();
});

test("local application preserves document selection, milestone CSV and unrelated fields", () => {
  const current = {
    ...base.draft,
    due: "2026-11-01",
    tool: "reflections",
    config: { historical_data: "PRIVATE CSV" },
  };
  const reflection = {
    ...proposal,
    tool: "reflections",
    config: {
      module_type: "milestone_based",
      historical_data: "",
      document_ids: ["untrusted"],
    },
  };
  const applied = applyAssignmentProposal(current, reflection, ["d1"]);
  expect(applied.config).toMatchObject({
    historical_data: "PRIVATE CSV",
    document_ids: ["d1"],
  });
  expect(applied.due).toBe(current.due);
  expect(applied.instructions).toContain("Learning objectives:");
  expect(
    applyAssignmentProposal(current, proposal, ["d1"], "title").config,
  ).toBe(current.config);
  expect(
    applyAssignmentProposal(current, proposal, ["d1"], "config").title,
  ).toBe(current.title);
});

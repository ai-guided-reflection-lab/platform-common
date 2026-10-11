import React from "react";
import { expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DebateConfig from "./DebateConfig";
import { defaults } from "./ToolConfig";

test("instructor configures a Debate scenario and completion threshold", async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  render(<DebateConfig value={defaults.debate} onChange={onChange} />);

  await user.type(
    screen.getByLabelText("Debate scenario or topic"),
    "Should cities restrict cars downtown?",
  );
  expect(onChange).toHaveBeenCalled();
  expect(screen.getByLabelText("Opening prompt")).toHaveValue("");
  expect(
    screen.getByLabelText("Messages required before completion"),
  ).toHaveValue(3);
});

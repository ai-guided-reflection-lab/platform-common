import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ApprovedReflection from "./ApprovedReflection";
import { api } from "../api";
vi.mock("../api", () => ({api:vi.fn()}));
vi.mock("./WorkspaceContext", () => ({useWorkspace:()=>({user:{display_name:"Alex Student"}})}));
beforeEach(()=>vi.clearAllMocks());

it("uses the approved reflection layout with real start, message, and completion contracts", async()=>{
  api.mockResolvedValueOnce({tool:"reflections",title:"Reflect on requirements"})
    .mockResolvedValueOnce({status:"in_progress",messages:[{role:"assistant",content:"Describe a requirement."}]})
    .mockResolvedValueOnce({status:"in_progress",messages:[{role:"student",content:"A measurable requirement"},{role:"assistant",content:"Which evidence supports that?"}]})
    .mockResolvedValueOnce({status:"completed",messages:[{role:"assistant",content:"Reflection saved."}]});
  render(<ApprovedReflection assignmentId="reflection-1"/>);
  expect(await screen.findByText("Describe a requirement.")).toBeInTheDocument();
  expect(screen.getByText("A moment to reflect")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Your reflection"),{target:{value:"A measurable requirement"}});
  fireEvent.click(screen.getByRole("button",{name:/Send reflection/}));
  expect(await screen.findByText("Which evidence supports that?")).toBeInTheDocument();
  expect(api.mock.calls[2]).toEqual(["/platform/assignments/reflection-1/messages",{method:"POST",body:{message:"A measurable requirement",request_id:expect.any(String)}}]);
  fireEvent.click(screen.getByRole("button",{name:"Finish reflection"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"Reflection complete"})).toBeDisabled());
  expect(api.mock.calls[3][0]).toBe("/platform/assignments/reflection-1/complete");
});

it("shows provider failures without inventing a conversation",async()=>{
  api.mockResolvedValueOnce({tool:"reflections",title:"Reflect"}).mockRejectedValueOnce(new Error("The provider API key was rejected."));
  render(<ApprovedReflection assignmentId="reflection-1"/>);
  expect(await screen.findByRole("alert")).toHaveTextContent("The provider API key was rejected.");
  expect(screen.queryByText("Describe a requirement.")).not.toBeInTheDocument();
});

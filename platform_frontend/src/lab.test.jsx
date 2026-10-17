import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { test, expect, vi } from "vitest";
import LabApp from "../../adaptive-learning-app/student-app/src/LabApp";

const response = data => ({ ok: true, status: 200, json: async () => data });
const participant = { id: "private-id", display_name: "Lab Tester", role: "student" };

test("name entry creates a private session and displays the existing assignment list", async () => {
  vi.stubGlobal("fetch", vi.fn(async (path) => response(path === "/api/lab/sessions"
    ? { token: "private-token", user: participant } : [])));
  render(<LabApp />);
  fireEvent.change(await screen.findByLabelText("Your name"), { target: { value: "Lab Tester" } });
  fireEvent.click(screen.getByRole("button", { name: "View assignments" }));
  expect(await screen.findByRole("heading", { name: "Your assignments" })).toBeInTheDocument();
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  expect(localStorage.getItem("adaptive-lab-session-v1")).toBe("private-token");
  const call = fetch.mock.calls.find(([path]) => path === "/api/student/assignments");
  expect(call[1].headers.get("Authorization")).toBe("Bearer private-token");
  expect(call[1].headers.has("X-Demo-User")).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Refresh assignments" }));
  await waitFor(() => expect(fetch.mock.calls.filter(([path]) => path === "/api/student/assignments")).toHaveLength(2));
});

test("returning participants resume without entering their name again", async () => {
  localStorage.setItem("adaptive-lab-session-v1", "saved-token");
  vi.stubGlobal("fetch", vi.fn(async path => response(path === "/api/lab/session" ? participant : [])));
  render(<LabApp />);
  expect(await screen.findByRole("heading", { name: "Your assignments" })).toBeInTheDocument();
  expect(screen.queryByLabelText("Your name")).not.toBeInTheDocument();
});

test("redeeming a code adds the assignment and invalid codes show an error", async () => {
  localStorage.setItem("adaptive-lab-session-v1", "saved-token");
  let unlocked = false;
  vi.stubGlobal("fetch", vi.fn(async (path, options) => {
    if (path === "/api/lab/session") return response(participant);
    if (path === "/api/lab/redeem") {
      if (JSON.parse(options.body).code !== "ABC123") return {ok:false,status:404,json:async()=>({detail:"Invalid assignment code."})};
      unlocked = true;
      return response({assignment_id:"lesson",title:"Code lesson"});
    }
    return response(unlocked ? [{id:"lesson",title:"Code lesson",instructions:"Study",learning_plan:{objectives:[]}}] : []);
  }));
  render(<LabApp />);
  const input = await screen.findByLabelText("Assignment code");
  fireEvent.change(input,{target:{value:"WRONG"}});
  fireEvent.click(screen.getByRole("button",{name:"Add assignment"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("Invalid assignment code.");
  fireEvent.change(input,{target:{value:"ABC123"}});
  fireEvent.click(screen.getByRole("button",{name:"Add assignment"}));
  expect(await screen.findByRole("heading",{name:"Code lesson"})).toBeInTheDocument();
});

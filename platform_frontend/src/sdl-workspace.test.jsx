import React from "react";
import {test,expect,vi} from "vitest";
import {render,screen,fireEvent,waitFor} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import SDLWorkspace from "./SDLWorkspace";
import {api} from "./api";
vi.mock("./api",()=>({api:vi.fn()}));
test("resumes SDL in the platform and sends choices through the SDL adapter",async()=>{
  const attempt={messages:[{id:"m1",role:"assistant",content:"Welcome to the lesson."}],objective_progress:[],learning_state:{stage:"welcome"}};
  api.mockImplementation(async(path)=>path.endsWith("/start") || path.endsWith("/learning-turn") ? attempt : {title:"Requirements activity",learning_plan:{topic:"Requirements",study_resources:[]}});
  render(<MemoryRouter><SDLWorkspace assignmentId="sdl1"/></MemoryRouter>);
  expect(await screen.findByRole("heading",{name:"Requirements activity"})).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"I'm completely new"}));
  await waitFor(()=>expect(api).toHaveBeenCalledWith("/platform/self-directed/assignments/sdl1/learning-turn",expect.objectContaining({method:"POST",body:expect.objectContaining({content:"I'm completely new",turn_id:expect.any(String)})})));
});

test("shows selected course materials without a broken external link", async () => {
  const resource = {title: "Selected course materials", url: "", provider: "Instructor course materials", description: "Included in the lesson.", focus: "Study the examples."};
  const attempt = {messages: [], objective_progress: [], learning_state: {stage: "study_resources", study_concepts: [], familiarity: "new", recommended_resource_url: null}};
  api.mockImplementation(async path => path.endsWith("/start") ? attempt : {title: "SDL activity", learning_plan: {topic: "Databases", study_resources: [resource]}});

  render(<MemoryRouter><SDLWorkspace assignmentId="sdl-local"/></MemoryRouter>);

  expect((await screen.findAllByText("Selected course materials")).length).toBeGreaterThan(0);
  expect(screen.queryByRole("link", {name: /Selected course materials/})).not.toBeInTheDocument();
  expect(screen.getByText("Included in this lesson")).toBeInTheDocument();
});

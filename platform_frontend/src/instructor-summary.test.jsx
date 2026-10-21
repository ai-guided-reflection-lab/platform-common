import React from "react";
import { expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import {api} from "./api";
import InstructorActivityPage, { AnalyticsPage, progressMetrics } from "./InstructorActivityPage";
vi.mock("./courseContext",()=>({cachedCourseContext:()=>null,loadCourseContext:async()=>({course_id:"course1"})}));
vi.mock("./api",async original=>({...await original(),api:vi.fn(async path=>{
 if(path.includes("/documents"))return {files:[]};
 return {id:"a1",course_id:"course1",tool:"debate",status:"published",title:"Design tradeoffs",instructions:"Defend a position",config:{scenario:"Should teams favor simple design?"},students:[{progress:"completed",result:{score_percent:80}},{progress:"in_progress"},{progress:"not_started"}]};
})}));

test("published assignment opens summary and KPIs with navigation to Analytics",async()=>{
 render(<MemoryRouter initialEntries={["/professor/activities/a1"]}><Routes><Route path="/professor/activities/:id" element={<InstructorActivityPage/>}/><Route path="/professor/analytics" element={<AnalyticsPage/>}/></Routes></MemoryRouter>);
 expect(await screen.findByRole("heading",{name:"Design tradeoffs"})).toBeInTheDocument();
 expect(screen.getByRole("heading",{name:"At a glance"})).toBeInTheDocument();
 expect(screen.getByText("Students started").parentElement).toHaveTextContent("2");
 expect(screen.getByText("Average grade").parentElement).toHaveTextContent("80%");
 expect(screen.queryByRole("heading",{name:"Select activity"})).not.toBeInTheDocument();
 await userEvent.setup().click(screen.getByRole("link",{name:"Detailed Insights →"}));
 expect(screen.getByText("Analytics will come here.")).toBeInTheDocument();
});
test("missing grade data is unavailable rather than a fabricated score",()=>{
 expect(progressMetrics([{progress:"completed",result:{message_count:4}},{progress:"not_started"}])).toMatchObject({assigned:2,started:1,completed:1,pending:1,completionRate:50,averageGrade:null});
});

test("draft editor reuses the loaded assignment instead of fetching it twice",async()=>{
 api.mockClear();
 api.mockImplementationOnce(async()=>({id:"draft1",course_id:"course1",tool:"self-directed-learning",status:"draft",title:"Saved draft",instructions:"Saved description",config:{document_ids:[],prompt:"Saved focus",custom_questions:[]}}));
 render(<MemoryRouter initialEntries={["/professor/activities/draft1"]}><Routes><Route path="/professor/activities/:id" element={<InstructorActivityPage/>}/></Routes></MemoryRouter>);
 expect(await screen.findByLabelText("Activity title")).toHaveValue("Saved draft");
 expect(screen.getByLabelText("Learning focus")).toHaveValue("Saved focus");
 expect(api.mock.calls.filter(([path])=>path==="/platform/assignments/draft1")).toHaveLength(1);
});

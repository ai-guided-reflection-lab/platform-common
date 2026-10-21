import React from "react";
import {test,expect} from "vitest";
import {render,screen} from "@testing-library/react";
import LessonPreview from "./LessonPreview";

test("shows generated questions, answer keys, practice and rubrics",()=>{
  render(<LessonPreview plan={{diagnostic_quiz:[{id:"q1",question:"What makes this measurable?",options:["A","B","C","D"],correct_index:2,explanation:"Use an observable measure."}],learning_assets:[{standard:[{prompt:"Write a measurable requirement.",rubric:"Includes a threshold."}]}]}}/>);
  expect(screen.getByText("What makes this measurable?")).toBeTruthy();
  expect(screen.getByText("Correct option (1–4)")).toBeTruthy();
  expect(screen.getByText("3")).toBeTruthy();
  expect(screen.getByText("Use an observable measure.")).toBeTruthy();
  expect(screen.getByText("Write a measurable requirement.")).toBeTruthy();
  expect(screen.getByText("Includes a threshold.")).toBeTruthy();
});

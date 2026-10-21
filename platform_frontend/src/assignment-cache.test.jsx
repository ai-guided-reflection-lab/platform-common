import {test,expect,vi} from "vitest";
import {api,cachedAssignmentView,preloadAssignment,SESSION_KEY} from "./api";
test("cached navigation stays isolated by login and clears after a write",async()=>{
  localStorage.setItem(SESSION_KEY,JSON.stringify({access_token:"alice"}));
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,status:200,json:async()=>({id:"a1",title:"Saved title"})})));
  await api("/platform/assignments/a1");
  expect(cachedAssignmentView("/platform/assignments/a1").title).toBe("Saved title");
  localStorage.setItem(SESSION_KEY,JSON.stringify({access_token:"bob"}));
  expect(cachedAssignmentView("/platform/assignments/a1")).toBeNull();
  localStorage.setItem(SESSION_KEY,JSON.stringify({access_token:"alice"}));
  await api("/platform/assignments/a1",{method:"PUT",body:{title:"Changed"}});
  expect(cachedAssignmentView("/platform/assignments/a1")).toBeNull();
  vi.unstubAllGlobals();
});
test("hover preloads share one request",async()=>{
  localStorage.setItem(SESSION_KEY,JSON.stringify({access_token:"preload-test"}));
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,status:200,json:async()=>({id:"a2"})})));
  await Promise.all([preloadAssignment("a2"),preloadAssignment("a2")]);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(cachedAssignmentView("/platform/assignments/a2").id).toBe("a2");
  vi.unstubAllGlobals();
});
test("list snapshots seed drafts without showing incomplete published analytics",async()=>{
  localStorage.setItem(SESSION_KEY,JSON.stringify({access_token:"instructor-list"}));
  vi.stubGlobal("fetch",vi.fn(async()=>({ok:true,status:200,json:async()=>[
    {id:"draft1",status:"draft",config:{prompt:"Saved settings"}},
    {id:"published1",status:"published",config:{scenario:"Debate"}},
  ]})));
  await api("/platform/assignments?course_id=course1");
  expect(cachedAssignmentView("/platform/assignments/draft1").config.prompt).toBe("Saved settings");
  expect(cachedAssignmentView("/platform/assignments/published1")).toBeNull();
  vi.unstubAllGlobals();
});

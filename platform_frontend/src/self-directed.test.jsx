import {beforeEach, expect, test, vi} from "vitest";
import {SESSION_KEY} from "./api";
import {studentTransport, loadSignedInStudent} from "./self-directed-api";

beforeEach(() => {
 localStorage.clear();
 localStorage.setItem(SESSION_KEY,JSON.stringify({access_token:"signed-session"}));
});

test("SDL transport carries signed authentication and preserves response identifiers", async () => {
 const fetch=vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>({learning_state:{stage:"diagnostic_quiz"}})});
 vi.stubGlobal("fetch",fetch);
 await studentTransport("/student/assignments/lesson/learning-turn", {method:"POST",body:JSON.stringify({turn_id:"retry-id",action:"choice",content:"A worked example"})});
 expect(fetch.mock.calls[0][0]).toBe("/api/platform/self-directed/assignments/lesson/learning-turn");
 const options=fetch.mock.calls[0][1];
 expect(options.headers.Authorization).toBe("Bearer signed-session");
 expect(options.headers["X-Demo-User"]).toBeUndefined();
 expect(JSON.parse(options.body).turn_id).toBe("retry-id");
});

test("SDL loads the actual student account and refuses professor impersonation", async () => {
 vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>({user:{user_id:"actual-student",display_name:"Student Name",authority_level:2,onboarding_complete:true}})}));
 expect(await loadSignedInStudent()).toEqual([{id:"actual-student",display_name:"Student Name",role:"student"}]);
 vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>({user:{authority_level:1,onboarding_complete:true}})}));
 await expect(loadSignedInStudent()).rejects.toThrow("student account");
});

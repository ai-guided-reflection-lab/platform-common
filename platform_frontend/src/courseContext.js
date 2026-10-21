import { api, session } from "./api";

let cached = null;
let resolved = null;
export function cachedCourseContext() {
  const requested=new URLSearchParams(window.location.search).get("course");
  return resolved?.token===(session()?.access_token || "") && (!requested || requested===String(resolved.context.course_id)) ? resolved.context : null;
}
export function resetCourseContext() { cached = null; resolved = null; }

export async function loadCourseContext() {
  const account = session()?.user_id || session()?.username || "current";
  const key = `platform_course_context:${account}`;
  const requested = new URLSearchParams(window.location.search).get("course") || sessionStorage.getItem(key);
  const token=session()?.access_token || "";
  const identity = `${token}:${requested || ""}`;
  if(cached?.identity===identity && cached.expires>Date.now()) return cached.promise;
  const promise = api(`/platform/context${requested ? `?course_id=${encodeURIComponent(requested)}` : ""}`).then(context=>{resolved={token,context,expires:Date.now()+30000};sessionStorage.setItem(key,context.course_id); if(cached?.promise===promise) cached.identity=`${token}:${context.course_id}`; return context;}).catch(error=>{if(cached?.promise===promise)cached=null;throw error;});
  cached={identity,promise,expires:Date.now()+30000};
  return promise;
}

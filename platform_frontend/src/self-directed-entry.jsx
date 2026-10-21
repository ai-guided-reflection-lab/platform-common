const assignmentId = new URLSearchParams(window.location.search).get("assignment");
window.location.replace(assignmentId ? `/platform/student/assignments/${encodeURIComponent(assignmentId)}` : "/platform/student");

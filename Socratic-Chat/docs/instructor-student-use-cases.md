# Socratic-Chat Instructor and Student Use Cases

**Document status:** Proposed target behavior based on the current implementation  
**Date:** August 23, 2026  
**Primary actors:** Instructor, Student  
**System:** Socratic-Chat, a course-scoped retrieval-augmented generation (RAG) tutor

## 1. Purpose

Socratic-Chat should support two clearly different roles:

- The **instructor determines the scope of discussion**, uploads one or more authoritative course files, reviews the resulting knowledge base, and publishes it.
- The **student selects an available course or topic and asks questions**. The chatbot retrieves information from the instructor-published files automatically, so the student does not need to upload the same materials.

The intended workflow is:

```text
Instructor defines course scope
          ↓
Instructor uploads and publishes course files
          ↓
System extracts, chunks, and indexes the content for RAG
          ↓
Student selects the course and asks a question
          ↓
System retrieves relevant course passages and generates a sourced answer
```

## 2. Answer to the Professor's Questions

### What should the uploaded files be about?

The files should define the instructor-approved knowledge scope for a course, module, assignment, or discussion. Appropriate files include:

- Syllabus and course policies
- Instructor lecture notes
- Lecture slides exported as text-readable PDF files
- Assigned readings that the instructor has permission to distribute
- Assignment instructions and grading rubrics
- Study guides and instructor-created FAQs
- Lab instructions
- Case studies
- Worked examples intended for student access
- Lecture or tutorial transcripts

The current RAG implementation can index `.pdf`, `.txt`, and `.md` files. Image files can currently be stored, but their contents are not extracted into the RAG index. Scanned PDFs must contain selectable text or later receive optical character recognition support.

The instructor should not publish:

- Student grades or personally identifiable student information
- Private accommodation records
- Instructor-only answer keys unless students are meant to access them
- Copyrighted material that the instructor is not authorized to distribute
- Draft or outdated materials that should not influence answers

### Why should students not have to upload files?

Students should be able to talk about a subject immediately after selecting a course because the instructor has already established the trusted knowledge base. Requiring every student to upload course files would:

- Repeat the same work for every student
- Produce inconsistent answers when students upload different file versions
- Allow incomplete, incorrect, or unrelated documents to affect the chatbot
- Make it unclear whether an answer represents instructor-approved material
- Increase privacy, copyright, and document-management risks
- Prevent the instructor from controlling the educational scope

Student upload should therefore be disabled by default. It may later be offered as an instructor-controlled option for specific activities, but student files must be isolated from the official course knowledge base unless an instructor reviews and publishes them.

## 3. Current System Behavior

The current implementation does **not** distinguish instructors from students.

### Current authentication and permissions

- A signed-in user is represented by one `users` record.
- The system does not currently have a `student` or `instructor` role.
- Every authenticated user can access the same chatbot interface and document-upload functions.
- Conversations and uploaded files are associated with the signed-in user.

### Current document and RAG behavior

- A user uploads one or more files into an individual conversation.
- Supported RAG formats are PDF, Markdown, and plain text.
- The original file is saved in PostgreSQL when the database is enabled.
- Extracted chunks are stored in a local JSON RAG index.
- Each indexed chunk is scoped with the conversation ID.
- Retrieval searches only chunks belonging to the current conversation.
- Therefore, a user usually must upload a file before asking questions about it.

### Gap between current and intended behavior

| Area | Current behavior | Intended behavior |
|---|---|---|
| Roles | All users have the same capabilities | Instructor and student permissions are different |
| Uploading | Any authenticated user can upload | Only instructors publish official course files |
| RAG scope | One conversation | One instructor-controlled course or module |
| Reuse | Files must be attached to individual chats | Published materials are reused by all enrolled students |
| Student entry point | Upload first, then ask | Select course, then ask immediately |
| Trust | User-provided files define the answer scope | Instructor-approved files define the answer scope |

## 4. Proposed Roles and Permissions

| Capability | Student | Instructor |
|---|:---:|:---:|
| Sign in with approved school account | Yes | Yes |
| View enrolled courses | Yes | Yes |
| Ask questions about published materials | Yes | Yes |
| View sources used in an answer | Yes | Yes |
| View personal conversation history | Yes | Yes |
| Create a course | No | Yes |
| Define discussion scope | No | Yes |
| Upload official RAG documents | No | Yes |
| Publish or unpublish documents | No | Yes |
| Replace or remove course documents | No | Yes |
| Test the course chatbot before publishing | No | Yes |
| View aggregate question topics | No | Yes, if enabled |
| View another student's private conversation | No | No by default |

New users must receive the `student` role by default. Instructor access must be assigned by an administrator, an approved instructor-email list, or an instructor invitation. A user must never be allowed to grant themselves the instructor role from the frontend.

## 5. Instructor Use Cases

### UC-I01: Create a course and define the discussion scope

**Primary actor:** Instructor  
**Goal:** Establish the subject boundary within which Socratic-Chat should answer.  
**Preconditions:** The user is authenticated and has the instructor role.  
**Trigger:** The instructor selects **Create Course**.

**Main flow:**

1. The instructor enters the course name, course code, term, and a short description.
2. The instructor optionally creates modules or topic areas.
3. The instructor defines guidance such as intended audience, permitted subjects, and topics the chatbot should treat as outside scope.
4. The system saves the course as a draft.
5. The system assigns the instructor as the course owner.

**Postconditions:** A draft course exists, but students cannot use it until materials are indexed and the course is published.

### UC-I02: Upload and index course materials

**Primary actor:** Instructor  
**Goal:** Build the authoritative RAG knowledge base for a course.  
**Preconditions:** A draft or published course exists and the instructor is authorized to manage it.  
**Trigger:** The instructor selects **Add Course Materials**.

**Main flow:**

1. The instructor selects one or more `.pdf`, `.txt`, or `.md` files.
2. The system validates the file type, size, filename, and presence of extractable text.
3. The system stores the original file with its course ID and uploader ID.
4. The system extracts and divides the text into RAG chunks.
5. Every chunk is tagged with its course ID, document ID, title, and page number when available.
6. The system indexes the chunks.
7. The system reports the number of accepted files, skipped files, and indexed chunks.
8. The instructor previews the document list and extraction status.

**Alternative flows:**

- If a file format is unsupported, the system skips it and explains the supported formats.
- If a PDF contains no extractable text, the system asks for a text-readable version.
- If the file duplicates an existing version, the system asks whether to replace it or cancel.
- If indexing fails, the document remains unpublished and the system reports the failure.

**Postconditions:** Valid files are associated with the course and available for instructor testing. They are not student-visible until published.

### UC-I03: Test and publish the course chatbot

**Primary actor:** Instructor  
**Goal:** Confirm that answers are properly grounded before students gain access.  
**Preconditions:** At least one document has been indexed successfully.  
**Trigger:** The instructor opens **Preview Chatbot**.

**Main flow:**

1. The instructor asks representative questions.
2. The system retrieves only chunks from the selected course.
3. The system displays an answer and its sources.
4. The instructor confirms that the sources and answer are appropriate.
5. The instructor publishes the course knowledge base.
6. Enrolled students can now select the course in Socratic-Chat.

**Alternative flow:** If answers are incomplete or inappropriate, the instructor updates the files or scope and retests before publication.

**Postconditions:** Students can use the published course corpus.

### UC-I04: Maintain course materials

**Primary actor:** Instructor  
**Goal:** Keep the RAG scope current and accurate.  
**Main flow:**

1. The instructor opens the course document library.
2. The instructor adds, replaces, unpublishes, or deletes a document.
3. The system reindexes only the affected course material.
4. New student questions use the latest published version.
5. The system retains document version and update information for accountability.

### UC-I05: Review learning gaps without exposing private chats

**Primary actor:** Instructor  
**Goal:** Identify areas where course materials or instruction may need clarification.  
**Main flow:**

1. The instructor opens course insights.
2. The system shows aggregate topics, unanswered-question counts, and documents most often cited.
3. The instructor uses the results to improve course documents or classroom instruction.

**Privacy rule:** Individual student conversations remain private unless the institution explicitly approves another policy and students are clearly informed.

## 6. Student Use Cases

### UC-S01: Sign in and select a course

**Primary actor:** Student  
**Goal:** Enter an instructor-approved learning space.  
**Preconditions:** The student has an approved school account and is enrolled or invited to at least one published course.  
**Trigger:** The student signs in.

**Main flow:**

1. The system authenticates the student's school account.
2. The system reads the student's role and course memberships.
3. The system displays only courses available to that student.
4. The student selects a course or module.
5. The chatbot displays the selected scope and the names of available instructor-published sources.

**Postconditions:** A new conversation is associated with the student and selected course.

### UC-S02: Ask a course question without uploading files

**Primary actor:** Student  
**Goal:** Receive an answer grounded in instructor-provided materials.  
**Preconditions:** A published course is selected and contains at least one indexed document.  
**Trigger:** The student submits a question.

**Main flow:**

1. The system records the question in the student's course conversation.
2. The system searches only published chunks belonging to the selected course or module.
3. The system selects the most relevant passages.
4. The language model produces a concise, Socratic response grounded in those passages.
5. The interface displays the answer and source titles or page numbers.
6. The student may ask a follow-up question without reselecting the course or uploading documents.

**Alternative flows:**

- If the question is outside the instructor-defined scope, the chatbot explains that it is outside the current course materials and invites a course-related question.
- If no relevant passage is found, the chatbot says that the answer is not available in the instructor-provided materials; it must not invent an answer.
- If the question is ambiguous, the chatbot asks a clarifying question.

**Postconditions:** The question, answer, and source references are saved in the student's private conversation history.

### UC-S03: Inspect sources and continue learning

**Primary actor:** Student  
**Goal:** Understand why an answer was given and continue the discussion.  
**Main flow:**

1. The student opens a cited source reference.
2. The system shows the document name, page number when available, and relevant excerpt.
3. The student asks a follow-up question.
4. The system retains the course scope and recent conversation context.

### UC-S04: Review personal conversation history

**Primary actor:** Student  
**Goal:** Return to previous course discussions.  
**Main flow:**

1. The student opens **My Conversations**.
2. The system lists only conversations owned by that student.
3. The student filters or groups conversations by course.
4. The student opens or deletes a conversation.

## 7. Target System Rules

1. Every user has a server-controlled role: `student`, `instructor`, or optionally `admin`.
2. New users default to `student`.
3. Only instructors can create courses and modify official course documents.
4. Every course document and RAG chunk belongs to a course.
5. Only published documents are searchable by students.
6. Every student conversation belongs to both a student and a course.
7. Retrieval must filter by the selected course ID on the backend; the frontend cannot be trusted to enforce scope.
8. Students cannot retrieve documents from courses in which they are not enrolled.
9. The chatbot must cite the instructor-provided sources used for an answer.
10. When evidence is missing, the chatbot must say so instead of answering from unsupported general knowledge.
11. Student uploads, if added later, remain private and separate from the official course corpus until instructor approval.
12. Theme and other display preferences remain local to the user's browser and do not affect authorization.

## 8. Required Data and Architecture Changes

The following model supports these use cases:

```text
users
  id
  email
  display_name
  role

courses
  id
  instructor_id
  course_code
  title
  term
  description
  status              # draft or published

course_memberships
  course_id
  user_id
  membership_role     # instructor, assistant, or student

course_documents
  id
  course_id
  uploaded_by
  filename
  status              # processing, ready, published, failed, archived
  version
  content

rag_chunks
  id
  course_id
  document_id
  page_number
  chunk_text
  search_tokens_or_embedding

conversations
  id
  user_id
  course_id
  title
```

The current conversation-scoped JSON index should be changed to a course-scoped persistent index. PostgreSQL with `pgvector`, or another durable vector store, would allow all Render instances to retrieve the same instructor-published course material without relying on one server's local filesystem.

## 9. Minimum Viable Implementation

The first useful instructor/student release should include:

1. Add `role` to users, defaulting to `student`.
2. Add courses and course memberships.
3. Add an instructor course-management screen.
4. Restrict document upload, scan, publish, replacement, and deletion endpoints to instructors.
5. Store and index documents by `course_id` rather than conversation ID.
6. Add a student course selector.
7. Remove the standard upload control from the student chatbot.
8. Retrieve only published chunks from the selected enrolled course.
9. Keep student histories private and grouped by course.
10. Add backend authorization tests proving that students cannot call instructor endpoints.

## 10. Acceptance Criteria

- An instructor can create a course and upload one or more supported files.
- A student cannot upload or publish official course materials.
- A student can select a published course and ask questions without uploading anything.
- Two students in the same course receive answers grounded in the same published corpus.
- A question in Course A never retrieves material from Course B.
- An unpublished or archived document is never used in a student answer.
- Every grounded answer displays at least one source when relevant evidence exists.
- An unsupported question produces a clear limitation statement rather than an invented answer.
- A student's conversation history cannot be opened by another student.
- Hiding an instructor button is not the only protection; instructor permissions are enforced by the backend.


# ClubALL integration contract

The standalone application deliberately separates Student Agent behavior from platform ownership. Reintegration should replace adapters, not the adaptive workflow.

## Identity adapter

Standalone requests identify one seeded user with `X-Demo-User`. ClubALL should translate its signed session into the same internal shape:

```json
{ "id": "stable-user-id", "display_name": "Name", "email": "name@example.edu", "role": "student" }
```

Never expose the demo header in a deployed ClubALL environment.

## Assignment adapter

The Student Agent contract requires an assignment with a stable id, title, instructions, recipients, immutable published learning plan, and document collection. ClubALL can continue to own assignment publication and pass a frozen snapshot to Student Agent.

## Learning-session adapter

Student Agent requires one attempt per student and assignment, ordered messages, objective evidence, required-task state, and completion state. The standalone SQLite tables model this contract; ClubALL may implement it with its PostgreSQL store.

## Knowledge adapter

The standalone implementation accepts PDF, Markdown, and text documents and retrieves embedded chunks by assignment id. ClubALL may replace storage and retrieval as long as it returns:

```json
[
  {
    "document_id": "id",
    "filename": "source.pdf",
    "content": "retrieved excerpt",
    "score": 0.82
  }
]
```

Student-facing responses receive source metadata but not raw hidden chunks.

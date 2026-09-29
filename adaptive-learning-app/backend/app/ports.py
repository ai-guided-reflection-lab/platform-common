"""Stable boundaries that ClubALL adapters can implement later."""

from __future__ import annotations

from typing import Protocol

from fastapi import UploadFile


class IdentityProvider(Protocol):
    def resolve_user(self, credential: str) -> dict: ...


class KnowledgeRepository(Protocol):
    async def add_document(self, assignment_id: str, upload: UploadFile) -> dict: ...

    def retrieve(self, assignment_id: str, query: str, limit: int = 4) -> list[dict]: ...


class AssignmentRepository(Protocol):
    def get_assignment(self, assignment_id: str) -> dict | None: ...

    def list_for_student(self, student_id: str) -> list[dict]: ...


class AttemptRepository(Protocol):
    def get_attempt(self, assignment_id: str, student_id: str) -> dict | None: ...

"""Create draft activities from verified assignment launches, never navigation."""
from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from app import settings
from platform_app.canvas_lms import description_text

RESOURCE_CLAIM = 'https://purl.imsglobal.org/spec/lti/claim/resource_link'
CUSTOM_CLAIM = 'https://purl.imsglobal.org/spec/lti/claim/custom'
AGS_CLAIM = 'https://purl.imsglobal.org/spec/lti-ags/claim/endpoint'


def _value(value) -> str:
    """Canvas may leave unavailable substitutions literally unexpanded."""
    return value.strip() if isinstance(value, str) and not value.strip().startswith('$') else ''


def _canvas_title(custom, resource) -> str:
    return _value(custom.get('canvas_assignment_title')) or _value(resource.get('title'))


def _canvas_due_at(custom):
    due = _value(custom.get('canvas_assignment_due_at'))
    if not due:
        return None
    try:
        parsed = datetime.fromisoformat(due.replace('Z', '+00:00'))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def provision(conn, claims, *, issuer, deployment_id, context_id, course_id, user_id, role):
    if not settings.LTI_AUTO_CREATE_ASSIGNMENTS:
        return None
    custom = claims.get(CUSTOM_CLAIM) or {}
    resource = claims.get(RESOURCE_CLAIM) or {}
    ags = claims.get(AGS_CLAIM) or {}
    if not all(isinstance(value, dict) for value in (custom, resource, ags)):
        raise HTTPException(422, 'Canvas sent invalid assignment launch information.')
    canvas_id = _value(custom.get('canvas_assignment_id'))
    if not (canvas_id or claims.get('_assignment_launch') is True or _value(ags.get('lineitem'))):
        return None
    resource_id = _value(resource.get('id'))
    if not resource_id or len(resource_id) > 1024 or len(canvas_id) > 1024:
        raise HTTPException(422, 'Canvas assignment launch requires a valid resource link ID.')

    # _provision_launch holds the course advisory lock for this transaction.
    linked = conn.execute(
        '''SELECT a.*, link.canvas_assignment_id
           FROM lti_assignment_links_platform link
           JOIN assignments_platform a ON a.id = link.assignment_id
           WHERE link.issuer=%s AND link.deployment_id=%s
             AND link.context_id=%s AND link.resource_link_id=%s
           FOR UPDATE OF a''',
        (issuer, deployment_id, context_id, resource_id),
    ).fetchone()
    if linked:
        if str(linked['course_id']) != str(course_id):
            raise HTTPException(409, 'The linked assignment was moved to a different course.')
        if canvas_id and linked['canvas_assignment_id'] and canvas_id != linked['canvas_assignment_id']:
            raise HTTPException(409, 'This Canvas link is already bound to a different assignment.')
        if linked['status'] == 'archived':
            raise HTTPException(409, 'Your instructor has archived this assignment.')
        if role == 'instructor' and linked['status'] == 'draft':
            canvas_title = _canvas_title(custom, resource)
            canvas_due_at = _canvas_due_at(custom)
            conn.execute(
                '''UPDATE assignments_platform
                   SET title=COALESCE(%s,title), due_at=COALESCE(%s,due_at), updated_at=now()
                   WHERE id=%s''',
                (canvas_title[:200] or None, canvas_due_at, linked['id']),
            )
        if role == 'student':
            if linked['status'] != 'published':
                raise HTTPException(409, 'Your instructor must finish configuring and publish this assignment before you can start.')
            if linked['audience'] != 'course' and not conn.execute(
                'SELECT 1 FROM assignment_recipients_platform WHERE assignment_id=%s AND student_id=%s',
                (linked['id'], user_id),
            ).fetchone():
                raise HTTPException(403, 'This assignment is not assigned to you.')
        return str(linked['id'])

    if role != 'instructor':
        raise HTTPException(409, 'An instructor must open this Canvas assignment in CourseLab and publish it before students can start.')
    title = _canvas_title(custom, resource) or 'Canvas assignment'
    raw_description = _value(custom.get('canvas_assignment_description')) or _value(resource.get('description'))
    instructions = description_text(raw_description)
    due_at = _canvas_due_at(custom)
    assignment_id = str(uuid4())
    config = {}
    conn.execute(
        '''INSERT INTO assignments_platform
           (id, course_id, creator_id, tool, title, instructions, due_at, audience, config)
           VALUES (%s,%s,%s,NULL,%s,%s,%s,'course',%s)''',
        (assignment_id, course_id, user_id, title[:200], instructions, due_at, Jsonb(config)),
    )
    conn.execute(
        '''INSERT INTO lti_assignment_links_platform
           (issuer, deployment_id, context_id, resource_link_id, canvas_assignment_id, assignment_id)
           VALUES (%s,%s,%s,%s,%s,%s)''',
        (issuer, deployment_id, context_id, resource_id, canvas_id or None, assignment_id),
    )
    return assignment_id

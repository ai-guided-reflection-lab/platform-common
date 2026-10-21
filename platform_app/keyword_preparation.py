"""Prepare a private RAG snapshot when an instructor confirms assignment keywords."""
import hashlib
import json

from fastapi import HTTPException
from psycopg.types.json import Jsonb

from platform_app import engines, store


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _input_fingerprint(item):
    config = item['config']
    return _digest({'version': 1, 'course_id': str(item['course_id']), 'tool': item['tool'],
                    'keywords': config.get('keywords') or [],
                    'document_ids': sorted(set(config.get('document_ids') or []))})


def _material_fingerprint(item):
    chosen = item['config'].get('document_ids') or []
    # Row versions detect reindexing, edits, visibility changes and deleted files
    # without loading all text or vectors merely to display preparation status.
    with store.connection() as source_conn:
        rows = source_conn.execute('''SELECT rf.id::text AS file_id, rf.xmin::text AS file_revision,
        rf.document_id, dc.id::text AS chunk_id, dc.xmin::text AS chunk_revision
        FROM documents rf
        LEFT JOIN chunks dc ON dc.file_id=rf.id AND dc.course_id=rf.course_id
        WHERE rf.course_id=%s AND (%s::text[]='{}'::text[] OR rf.document_id=ANY(%s::text[]))
        ORDER BY rf.id, dc.id''', (item['course_id'], chosen, chosen)).fetchall()
    return _digest(rows)


def current(conn, item):
    row = conn.execute('SELECT * FROM assignment_keyword_preparations_platform WHERE assignment_id=%s', (item['id'],)).fetchone()
    if not row:
        return None
    reason = None
    if row['input_fingerprint'] != _input_fingerprint(item):
        reason = 'keywords_changed'
    elif row['material_fingerprint'] != _material_fingerprint(item):
        reason = 'materials_changed'
    chunks = row['prepared_snapshot'].get('chunks') or []
    metadata = {'ready': reason is None, 'reason': reason, 'keywords': row['keywords'],
                'document_ids': row['prepared_snapshot']['config'].get('document_ids') or [],
                'course_id': str(item['course_id']), 'prepared_at': row['prepared_at'],
                'passage_count': len(chunks), 'document_count': len({c['document_id'] for c in chunks})}
    return {'metadata': metadata, 'snapshot': row['prepared_snapshot']}


def status(conn, item):
    result = current(conn, item)
    return result['metadata'] if result else None


def confirm(conn, item):
    if item['status'] != 'draft':
        raise HTTPException(409, 'Published assignments are frozen. Duplicate the assignment to change keywords.')
    if item['tool'] != 'socratic':
        raise HTTPException(422, 'Keyword confirmation is available for Socratic Chat assignments.')
    if not item['config'].get('keywords'):
        raise HTTPException(422, 'Move at least one keyword to Approved before confirming.')
    existing = current(conn, item)
    if existing and existing['metadata']['ready']:
        return existing['metadata']
    before = _material_fingerprint(item)
    snapshot = engines.publish_snapshot(item)
    if before != _material_fingerprint(item):
        raise HTTPException(409, 'Course materials changed during preparation. Confirm the keywords again.')
    conn.execute('''INSERT INTO assignment_keyword_preparations_platform
        (assignment_id,input_fingerprint,material_fingerprint,keywords,prepared_snapshot)
        VALUES (%s,%s,%s,%s,%s) ON CONFLICT(assignment_id) DO UPDATE SET
        input_fingerprint=EXCLUDED.input_fingerprint, material_fingerprint=EXCLUDED.material_fingerprint,
        keywords=EXCLUDED.keywords, prepared_snapshot=EXCLUDED.prepared_snapshot, prepared_at=now()''',
        (item['id'], _input_fingerprint(item), before, Jsonb(item['config']['keywords']), Jsonb(snapshot)))
    return status(conn, item)


def snapshot_for_publish(conn, item):
    prepared = current(conn, item)
    if not prepared or not prepared['metadata']['ready']:
        raise HTTPException(409, 'Confirm keywords to prepare the course materials before publishing. Confirm again after changing keywords or materials.')
    # Title/instructions may change without affecting RAG; use the current config.
    return {**prepared['snapshot'], 'config': item['config']}

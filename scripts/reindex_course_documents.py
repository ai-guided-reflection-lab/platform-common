"""Repair stored course documents without duplicating uploads or publishing work."""
import argparse
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from uuid import UUID

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
sys.path.insert(0, str(ROOT / 'Socratic-Chat/backend'))

from app import db, rag, settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--course-id', required=True, type=UUID)
    parser.add_argument('--unindexed-only', action='store_true')
    args = parser.parse_args()
    course_id = str(args.course_id)
    repaired, failures = 0, 0
    for source in db.list_indexable_rag_files(course_id=course_id):
        if args.unindexed_only and source['document_id']:
            continue
        with TemporaryDirectory(prefix='courselab-reindex-') as directory:
            path = Path(directory) / Path(source['filename']).name
            path.write_bytes(source['content'])
            os.chmod(path, 0o600)
            try:
                _, chunks = rag.ingest_file(path, conversation_id=source['conversation_id'], course_id=course_id, file_id=source['file_id'])
            except (rag.EmbeddingError, rag.DocumentTextError) as error:
                print(f"Not indexed: {path.name}: {error}")
                failures += 1
                continue
            print(f"Indexed {path.name}: {chunks} chunk(s), {settings.embedding_model_name()}.")
            repaired += 1
    print(f"Course documents repaired: {repaired}; failures: {failures}. Assignments were not published.")
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())

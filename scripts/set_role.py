"""Explicit local administrator command for bootstrapping registered accounts."""
import argparse
import os
import re
from pathlib import Path

from dotenv import load_dotenv
import psycopg
from psycopg import sql

load_dotenv(Path(__file__).resolve().parents[1] / '.env')
parser = argparse.ArgumentParser(description='Set a registered platform account role.')
parser.add_argument('email')
parser.add_argument('role', choices=['admin', 'instructor', 'student'])
args = parser.parse_args()
platform_schema = os.getenv('PLATFORM_DB_SCHEMA', 'platform')
if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', platform_schema):
    raise SystemExit('PLATFORM_DB_SCHEMA must be a valid PostgreSQL identifier.')
with psycopg.connect(os.environ['DATABASE_URL']) as conn:
    query = sql.SQL(
        'UPDATE {}.users_platform '
        'SET authority_level=%s, requested_authority_level=NULL '
        'WHERE lower(email)=lower(%s) RETURNING username'
    ).format(sql.Identifier(platform_schema))
    row = conn.execute(
        query,
        ({'admin': 0, 'instructor': 1, 'student': 2}[args.role], args.email),
    ).fetchone()
    if not row: raise SystemExit('Account not found. Register this account first.')
    print(f'Updated {row[0]} to {args.role}.')

"""Explicit local administrator command for bootstrapping registered accounts."""
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
import psycopg

load_dotenv(Path(__file__).resolve().parents[1] / '.env')
parser = argparse.ArgumentParser(description='Set a registered platform account role.')
parser.add_argument('email')
parser.add_argument('role', choices=['admin', 'instructor', 'student'])
args = parser.parse_args()
with psycopg.connect(os.environ['DATABASE_URL']) as conn:
    row = conn.execute('UPDATE users SET authority_level=%s, requested_authority_level=NULL WHERE lower(email)=lower(%s) RETURNING username',
                       ({'admin':0,'instructor':1,'student':2}[args.role], args.email)).fetchone()
    if not row: raise SystemExit('Account not found. Register this account first.')
    print(f'Updated {row[0]} to {args.role}.')

import argparse

import psycopg
from psycopg.rows import dict_row

from app.core.config import get_settings


def main():
    parser=argparse.ArgumentParser(description='Promote an existing verified account to the first administrator')
    parser.add_argument('--email',required=True)
    args=parser.parse_args()
    with psycopg.connect(get_settings().postgres_dsn,row_factory=dict_row) as c:
        c.execute("SELECT pg_advisory_xact_lock(hashtextextended('admin-user-management',0))")
        if c.execute("SELECT 1 FROM users WHERE role='admin' AND is_active LIMIT 1").fetchone():
            raise SystemExit('An active administrator already exists; use the admin workspace.')
        user=c.execute('SELECT user_id,is_active,is_email_verified FROM users WHERE lower(email)=lower(%s) FOR UPDATE',(args.email,)).fetchone()
        if not user or not user['is_active'] or not user['is_email_verified']:
            raise SystemExit('An active, verified account is required.')
        c.execute("UPDATE users SET role='admin',updated_at=now() WHERE user_id=%s",(user['user_id'],))
        c.execute("INSERT INTO admin_audit(actor_id,target_id,action,details) VALUES (%s,%s,'bootstrap_admin','{}')",(user['user_id'],user['user_id']))
        c.execute('UPDATE refresh_tokens SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL',(user['user_id'],))
    print('Initial administrator configured. Sign in again.')


if __name__=='__main__':
    main()

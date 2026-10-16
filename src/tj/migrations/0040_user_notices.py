"""Уведомления пользователю (баннеры PWA): «Garmin просит войти заново» и т.п."""


def upgrade(con):
    con.execute('''CREATE TABLE IF NOT EXISTS user_notices (
        "id" TEXT PRIMARY KEY, "uid" INTEGER NOT NULL, "kind" TEXT NOT NULL,
        "text" TEXT NOT NULL, "created_at" TEXT NOT NULL, "read_at" TEXT )''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_user_notices_uid '
                'ON user_notices ("uid","read_at","created_at")')
    con.commit()

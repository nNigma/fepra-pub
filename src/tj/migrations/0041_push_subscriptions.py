"""Подписки Web Push (одна строка на endpoint браузера/устройства)."""


def upgrade(con):
    con.execute('''CREATE TABLE IF NOT EXISTS push_subscriptions (
        "id" TEXT PRIMARY KEY, "uid" INTEGER NOT NULL,
        "endpoint" TEXT NOT NULL UNIQUE, "p256dh" TEXT NOT NULL, "auth" TEXT NOT NULL,
        "ua" TEXT, "created_at" TEXT NOT NULL, "deleted_at" TEXT )''')
    con.execute('CREATE INDEX IF NOT EXISTS idx_push_subs_uid '
                'ON push_subscriptions ("uid","deleted_at")')
    con.commit()

from tjapp.auth import resolve_effective_user

ADMIN = REDACTED
FRIEND = 111
STRANGER = 999

def _allow(_id=None):
    return {ADMIN, FRIEND}

def _admins(_id=None):
    return {ADMIN}

def test_admin_can_view_allowed_user():
    assert resolve_effective_user(ADMIN, FRIEND, _load_allow=_allow, _load_admins=_admins) == FRIEND

def test_admin_view_stranger_falls_back_to_self():
    assert resolve_effective_user(ADMIN, STRANGER, _load_allow=_allow, _load_admins=_admins) == ADMIN

def test_non_admin_cannot_view_other():
    assert resolve_effective_user(FRIEND, ADMIN, _load_allow=_allow, _load_admins=_admins) == FRIEND

def test_no_as_user_returns_self():
    assert resolve_effective_user(FRIEND, None, _load_allow=_allow, _load_admins=_admins) == FRIEND

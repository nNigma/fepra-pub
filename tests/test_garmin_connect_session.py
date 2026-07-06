from tjbot.garmin_connect import GarminConnectSession

class _FakeAdapter:
    def __init__(self, email, password, tokenstore, prompt_mfa, needs_mfa=False, bad=False):
        self._prompt_mfa = prompt_mfa; self._needs = needs_mfa; self._bad = bad
    def _login(self):
        if self._bad:
            raise ValueError("bad creds")
        if self._needs:
            code = self._prompt_mfa()
            if code != "999":
                raise ValueError("bad mfa")
        return object()

def _factory(**kw):
    def f(email, password, tokenstore, prompt_mfa):
        return _FakeAdapter(email, password, tokenstore, prompt_mfa, **kw)
    return f

def test_login_no_mfa_ok():
    s = GarminConnectSession(_factory())
    s.start_login("e", "p", "/tmp/ts")
    assert s.wait_state(2) == "ok"

def test_login_with_mfa_ok():
    s = GarminConnectSession(_factory(needs_mfa=True))
    s.start_login("e", "p", "/tmp/ts")
    assert s.wait_state(2) == "need_mfa"
    s.submit_mfa("999")
    assert s.wait_state(2) == "ok"

def test_login_with_mfa_bad_code():
    s = GarminConnectSession(_factory(needs_mfa=True))
    s.start_login("e", "p", "/tmp/ts")
    assert s.wait_state(2) == "need_mfa"
    s.submit_mfa("000")
    assert s.wait_state(2) == "error"

def test_login_bad_creds():
    s = GarminConnectSession(_factory(bad=True))
    s.start_login("e", "p", "/tmp/ts")
    assert s.wait_state(2) == "error"

def test_login_mfa_timeout():
    import time
    s = GarminConnectSession(_factory(needs_mfa=True), mfa_timeout=0.1)
    s.start_login("e", "p", "/tmp/ts")
    assert s.wait_state(2) == "need_mfa"
    time.sleep(0.25)
    assert s.wait_state(2) == "error"

def test_early_submit_before_prompt():
    s = GarminConnectSession(_factory(needs_mfa=True))
    s.submit_mfa("999")
    s.start_login("e", "p", "/tmp/ts")
    assert s.wait_state(2) == "ok"

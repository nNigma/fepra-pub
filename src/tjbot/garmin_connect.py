"""Изолированный тред-мост для логина Garmin с MFA. Логин garminconnect
синхронный и блокирующий (prompt_mfa), поэтому крутим его в потоке, а код MFA
подаём из бота через Event. Пароль живёт только в памяти сессии."""
from __future__ import annotations

import threading


class GarminConnectSession:
    def __init__(self, adapter_factory, mfa_timeout: float = 300.0):
        self._factory = adapter_factory
        self._mfa_timeout = mfa_timeout
        self._mfa_event = threading.Event()
        self._mfa_requested = threading.Event()
        self._done = threading.Event()
        self._mfa_code = None
        self._result = None
        self._error = None
        self._thread = None

    def _prompt_mfa(self):
        self._mfa_requested.set()
        if not self._mfa_event.wait(timeout=self._mfa_timeout):
            raise TimeoutError("MFA timeout")
        return self._mfa_code

    def start_login(self, email, password, tokenstore) -> None:
        def run():
            try:
                ad = self._factory(email, password, tokenstore, self._prompt_mfa)
                ad._login()
                self._result = "ok"
            except Exception as e:
                self._result = "error"
                self._error = type(e).__name__
                print(f"[garmin] login failed: {type(e).__name__}", flush=True)
            finally:
                self._done.set()
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def submit_mfa(self, code: str) -> None:
        self._mfa_code = (code or "").strip()
        self._mfa_event.set()

    def wait_state(self, timeout: float) -> str:
        """Дождаться либо завершения логина, либо запроса MFA — что раньше.
        Возвращает 'ok' | 'error' | 'need_mfa' | 'pending'."""
        step = 0.05
        waited = 0.0
        while waited < timeout:
            if self._done.is_set():
                return self._result or "error"
            if self._mfa_requested.is_set() and not self._mfa_event.is_set():
                return "need_mfa"
            self._done.wait(step)
            waited += step
        return "pending"

from tjbot.handlers import watch


def test_connect_message_has_link_and_token():
    msg = watch.connect_message("https://x/fepra-connect.apk", "TOK123", "ru")
    assert "https://x/fepra-connect.apk" in msg
    assert "TOK123" in msg


def test_connect_message_en():
    msg = watch.connect_message("https://x/fepra-connect.apk", "TOK123", "en")
    assert "TOK123" in msg
    assert not any("а" <= ch.lower() <= "я" for ch in msg)

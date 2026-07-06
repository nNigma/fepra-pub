from tj.adapters.garmin import GarminAdapter


def test_adapter_accepts_prompt_mfa():
    ad = GarminAdapter("e", "p", "/tmp/ts", tz=None, prompt_mfa=lambda: "123")
    assert ad._prompt_mfa() == "123"

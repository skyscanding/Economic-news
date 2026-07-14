"""Provider routing (Gemini vs DeepSeek). No live API calls."""
from newsagent import providers
from newsagent.config import Config


def test_is_deepseek_detection():
    assert providers.is_deepseek("deepseek-v4-pro")
    assert providers.is_deepseek("deepseek-v4-flash")
    assert not providers.is_deepseek("gemini-3.5-flash")
    assert not providers.is_deepseek("")


def test_provider_name():
    assert providers.provider_name("deepseek-v4-flash") == "deepseek"
    assert providers.provider_name("gemini-3.5-flash") == "gemini"


def test_api_key_routing():
    cfg = Config(gemini_api_key="G", deepseek_api_key="D")
    assert providers.api_key_for("gemini-3.5-flash", cfg) == "G"
    assert providers.api_key_for("deepseek-v4-pro", cfg) == "D"


def test_sdk_available():
    # both httpx (deepseek) and google-genai (gemini) are installed
    assert providers.sdk_available("deepseek-v4-flash")
    assert providers.sdk_available("gemini-3.5-flash")

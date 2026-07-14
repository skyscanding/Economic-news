"""Config: env-var / .env overrides for model and key."""
import os

from newsagent import config
from newsagent.config import Config


def test_gemini_model_reads_env(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3-flash-preview")
    assert Config().gemini_model == "gemini-3-flash-preview"


def test_gemini_model_default(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert Config().gemini_model == "gemini-3.5-flash"


def test_load_dotenv_sets_defaults_and_strips_quotes(tmp_path, monkeypatch):
    # Use throwaway var names (not GEMINI_*) so setdefault can't leak a real
    # config value into other tests in the same process.
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        '# a comment\nNEWSAGENT_TV=fromfile\nNEWSAGENT_TVQ="quoted val"\n',
        encoding="utf-8")
    monkeypatch.delenv("NEWSAGENT_TV", raising=False)
    monkeypatch.delenv("NEWSAGENT_TVQ", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "x")   # shield the real project .env

    config._load_dotenv()
    assert os.environ["NEWSAGENT_TV"] == "fromfile"
    assert os.environ["NEWSAGENT_TVQ"] == "quoted val"    # quotes stripped


def test_load_dotenv_does_not_override_real_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("NEWSAGENT_TV2=fromfile\n", encoding="utf-8")
    monkeypatch.setenv("NEWSAGENT_TV2", "fromenv")
    monkeypatch.setenv("GEMINI_API_KEY", "x")

    config._load_dotenv()
    assert os.environ["NEWSAGENT_TV2"] == "fromenv"        # env wins over file

import pytest

from app.auth.passwords import hash_password, password_problem, verify_password
from app.auth.providers import LdapProvider, LocalProvider, get_provider
from app.config import Settings


def test_hash_and_verify():
    h = hash_password("Correct-horse-1")
    assert verify_password(h, "Correct-horse-1") and not verify_password(h, "wrong")
    assert not verify_password("", "anything")


@pytest.mark.parametrize("pw,ok", [("short1", False), ("onlyletterslong", False), ("12345678901", False),
                                   ("Good-pass-1", True)])  # fmt: skip
def test_password_policy(pw, ok):
    assert (password_problem(pw) is None) == ok


def test_provider_selection():
    assert isinstance(get_provider(Settings(auth_provider="local")), LocalProvider)
    assert isinstance(get_provider(Settings(auth_provider="ldap")), LdapProvider)
    with pytest.raises(ValueError):
        get_provider(Settings(auth_provider="magic"))


def test_ldap_stub_fails_safely(db):
    from app.db.models import User

    db.add(User(username="ldapuser", auth_source="ldap"))
    db.commit()
    out = LdapProvider().authenticate(db, "ldapuser", "whatever")
    assert out.user is None and "not available" in out.message


def test_prod_requires_strong_secret():
    from app.main import check_settings

    with pytest.raises(RuntimeError):
        check_settings(Settings(environment="prod", secret_key="dev-only-change-me"))
    check_settings(Settings(environment="prod", secret_key="x" * 40, cookie_secure=True))


def test_cli_create_and_list(db, monkeypatch, capsys):
    from app import cli

    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "Cli-pass-123")
    assert cli.main(["create-user", "cliadmin", "--role", "admin"]) == 0
    assert cli.main(["list-users"]) == 0
    assert "cliadmin" in capsys.readouterr().out

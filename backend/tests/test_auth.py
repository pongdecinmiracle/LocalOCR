from __future__ import annotations

from conftest import register

from app import config


def test_first_user_becomes_admin(client):
    r = register(client, "alice")
    assert r.status_code == 200
    assert r.json()["is_admin"] is True
    assert "token_version" not in r.json()

    r2 = register(client, "bob")
    assert r2.json()["is_admin"] is False


def test_register_validation(client):
    assert register(client, "ab").status_code == 400          # username too short
    assert register(client, "carol", "123").status_code == 400  # password too short
    register(client, "dave")
    assert register(client, "DAVE").status_code == 400          # case-insensitive dupe


def test_login_and_me(client):
    register(client, "alice")
    client.cookies.clear()
    assert client.get("/api/me").status_code == 401

    r = client.post("/api/login", json={"username": "alice", "password": "secret123"})
    assert r.status_code == 200
    assert client.get("/api/me").json()["username"] == "alice"

    r = client.post("/api/login", json={"username": "alice", "password": "wrong-pw"})
    assert r.status_code == 401


def test_login_lockout_after_repeated_failures(client):
    register(client, "alice")
    client.cookies.clear()
    for _ in range(config.LOGIN_MAX_FAILURES):
        client.post("/api/login", json={"username": "alice", "password": "wrong-pw"})
    # Even the correct password is now rejected until the lockout expires.
    r = client.post("/api/login", json={"username": "alice", "password": "secret123"})
    assert r.status_code == 429


def test_password_reset_invalidates_sessions(client, second_client):
    admin = register(client, "alice").json()
    assert admin["is_admin"]
    bob = register(second_client, "bob").json()
    assert second_client.get("/api/me").status_code == 200

    r = client.post(f"/api/admin/users/{bob['id']}/password", json={"password": "newpass123"})
    assert r.status_code == 200
    # Bob's old session cookie no longer works.
    assert second_client.get("/api/me").status_code == 401
    # And the new password logs in fine.
    r = second_client.post("/api/login", json={"username": "bob", "password": "newpass123"})
    assert r.status_code == 200


def test_admin_endpoints_require_admin(client, second_client):
    register(client, "alice")
    register(second_client, "bob")
    assert second_client.get("/api/admin/users").status_code == 403
    assert client.get("/api/admin/users").status_code == 200


def test_last_admin_protections(client):
    alice = register(client, "alice").json()
    r = client.post(f"/api/admin/users/{alice['id']}/admin", json={"is_admin": False})
    assert r.status_code == 400  # can't demote the only admin
    r = client.delete(f"/api/admin/users/{alice['id']}")
    assert r.status_code == 400  # can't self-delete


def test_registration_toggle(client, monkeypatch):
    monkeypatch.setattr(config, "ALLOW_REGISTRATION", False)
    # Bootstrap: first account is always allowed.
    assert client.get("/api/auth-config").json()["allow_registration"] is True
    assert register(client, "alice").status_code == 200
    # After that, self-registration is closed.
    assert client.get("/api/auth-config").json()["allow_registration"] is False
    assert register(client, "bob").status_code == 403

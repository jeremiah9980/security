"""Integration-point status tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from propertypresence.web.status import integration_status, ACTIVE, NEEDS_SETUP, OFF


def _by_key(points):
    return {p["key"]: p for p in points}


def test_all_nine_points_always_reported():
    pts = _by_key(integration_status({}))
    assert set(pts) == {"wifi", "bluetooth", "eero", "slack", "github", "log",
                        "ring", "alexa", "cameras"}


def test_disabled_points_are_off_with_hints():
    pts = _by_key(integration_status({}))
    assert pts["eero"]["state"] == OFF
    assert pts["ring"]["state"] == OFF
    assert "enabled: true" in pts["eero"]["hint"]


def test_slack_enabled_without_webhook_needs_setup(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    cfg = {"sinks": {"slack": {"enabled": True}}}
    pts = _by_key(integration_status(cfg))
    assert pts["slack"]["state"] == NEEDS_SETUP
    assert "SLACK_WEBHOOK_URL" in pts["slack"]["hint"]


def test_slack_active_with_env_webhook(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/T/B/x")
    cfg = {"sinks": {"slack": {"enabled": True}}}
    pts = _by_key(integration_status(cfg))
    assert pts["slack"]["state"] == ACTIVE


def test_eero_enabled_without_session_needs_setup(tmp_path):
    cfg = {"collectors": {"eero": {"enabled": True,
                                   "session_file": str(tmp_path / "nope.cookie")}}}
    pts = _by_key(integration_status(cfg))
    assert pts["eero"]["state"] == NEEDS_SETUP
    assert "--eero-login" in pts["eero"]["hint"]


def test_eero_active_with_session(tmp_path):
    sess = tmp_path / "s.cookie"
    sess.write_text("123|abc")
    cfg = {"collectors": {"eero": {"enabled": True, "session_file": str(sess),
                                   "network_name": "MyNet"}}}
    pts = _by_key(integration_status(cfg))
    assert pts["eero"]["state"] == ACTIVE
    assert "MyNet" in pts["eero"]["detail"]


def test_cameras_active_counts_feeds():
    cfg = {"integrations": {"cameras": {"enabled": True, "feeds": [
        {"name": "Front", "kind": "ring"}, {"name": "Back", "kind": "rtsp"}]}}}
    pts = _by_key(integration_status(cfg))
    assert pts["cameras"]["state"] == ACTIVE
    assert "2 feed(s)" in pts["cameras"]["detail"]


def test_github_needs_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    cfg = {"sinks": {"github": {"enabled": True, "repo": "o/r"}}}
    pts = _by_key(integration_status(cfg))
    assert pts["github"]["state"] == NEEDS_SETUP
    assert "GITHUB_TOKEN" in pts["github"]["detail"]

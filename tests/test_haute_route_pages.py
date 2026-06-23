"""Haute Route 2027 hub and 2012 build-intel sub-pages."""
from fastapi.testclient import TestClient

from ai_endurance_coach_over50.server import app


client = TestClient(app)


def test_haute_route_hub_returns_200():
    r = client.get("/haute-route")
    assert r.status_code == 200
    body = r.text
    assert "2027 Build Intel" in body
    assert "/haute-route/2012-postmortem" in body
    assert "/haute-route/power-protocol" in body


def test_2012_postmortem_page():
    r = client.get("/haute-route/2012-postmortem")
    assert r.status_code == 200
    body = r.text
    assert "broom wagon" in body
    assert "11-36" in body
    assert "/haute-route/power-protocol" in body


def test_power_protocol_page():
    r = client.get("/haute-route/power-protocol")
    assert r.status_code == 200
    body = r.text
    assert "FTP Test Protocol" in body
    assert "/haute-route/2012-postmortem" in body


def test_hr_subnav_on_all_pages():
    for path in ("/haute-route", "/haute-route/2012-postmortem", "/haute-route/power-protocol"):
        body = client.get(path).text
        assert "Training Plan" in body
        assert "2012 Post-Mortem" in body
        assert "Power &amp; FTP" in body or "Power & FTP" in body

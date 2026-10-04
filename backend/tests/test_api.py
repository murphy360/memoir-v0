"""Smoke tests for the API: it starts, migrates an empty database and serves the timeline."""


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_points_at_health(client):
    assert client.get("/").json()["health"] == "/api/health"


def test_period_round_trip(client):
    created = client.post(
        "/api/periods",
        json={"title": "College", "start_date_text": "1998", "end_date_text": "2002"},
    )
    assert created.status_code == 200, created.text
    period = created.json()
    assert period["title"] == "College"

    listed = client.get("/api/periods")
    assert listed.status_code == 200
    assert period["id"] in {p["id"] for p in listed.json()}


def test_missing_person_is_404(client):
    assert client.get("/api/people/999999").status_code == 404

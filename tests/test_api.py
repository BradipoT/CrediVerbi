def _org(client, name="Le Fil Media", kind="media"):
    r = client.post("/api/organizations", json={"name": name, "kind": kind})
    assert r.status_code == 201, r.text
    return r.json()


def _person(client, name="Jean Exemple", org_id=None, public=True):
    payload = {
        "name": name,
        "role": "journaliste",
        "organization_id": org_id,
        "is_public_figure": public,
    }
    r = client.post("/api/persons", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _statement(client, person_id, quote="Le chômage a baissé de 50 %.", **kw):
    payload = {"person_id": person_id, "quote": quote, "source_url": "https://exemple.fr/dep", **kw}
    r = client.post("/api/statements", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _verdict(client, statement_id, rating, sources=None, supersedes=None, justification="Justification documentée."):
    payload = {
        "rating": rating,
        "justification": justification,
        "sources": sources if sources is not None else [{"url": "https://exemple.fr/preuve"}],
        "created_by": "redaction",
    }
    if supersedes is not None:
        payload["supersedes"] = supersedes
    r = client.post(f"/api/statements/{statement_id}/verdicts", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_duplicate_organization_rejected(client):
    _org(client)
    r = client.post("/api/organizations", json={"name": "Le Fil Media", "kind": "media"})
    assert r.status_code == 400


def test_statement_requires_public_figure(client):
    p = _person(client, public=False)
    r = client.post("/api/statements", json={"person_id": p["id"], "quote": "x"})
    assert r.status_code == 400


def test_statement_requires_existing_person(client):
    r = client.post("/api/statements", json={"person_id": 999, "quote": "x"})
    assert r.status_code == 404


def test_verdict_requires_at_least_one_source(client):
    p = _person(client)
    st = _statement(client, p["id"])
    r = client.post(
        f"/api/statements/{st['id']}/verdicts",
        json={"rating": "faux", "justification": "…", "sources": []},
    )
    assert r.status_code == 422


def test_invalid_rating_rejected(client):
    p = _person(client)
    st = _statement(client, p["id"])
    r = client.post(
        f"/api/statements/{st['id']}/verdicts",
        json={"rating": "mensonge", "justification": "…", "sources": [{"url": "https://x.fr"}]},
    )
    assert r.status_code == 422


def test_index_scoring_and_counts(client):
    org = _org(client)
    p = _person(client, org_id=org["id"])
    for i, rating in enumerate(["vrai", "partiellement_vrai", "faux", "indetermine"]):
        st = _statement(client, p["id"], quote=f"Affirmation {i}")
        _verdict(client, st["id"], rating)
    idx = client.get(f"/api/index/persons/{p['id']}").json()
    assert idx["active_verdicts"] == 4
    assert idx["counts"]["vrai"] == 1
    assert idx["counts"]["indetermine"] == 1
    assert idx["scored_verdicts"] == 3
    assert idx["score"] == round((1.0 + 0.5 + 0.0) / 3, 3)
    org_idx = client.get(f"/api/index/organizations/{org['id']}").json()
    assert org_idx["score"] == idx["score"]
    assert org_idx["active_verdicts"] == 4


def test_correction_supersedes_and_history(client):
    p = _person(client)
    st = _statement(client, p["id"])
    v1 = _verdict(client, st["id"], "faux")
    v2 = _verdict(client, st["id"], "vrai", supersedes=v1["id"])
    assert v2["is_current"] is True
    detail = client.get(f"/api/statements/{st['id']}").json()
    assert detail["current_verdict"]["id"] == v2["id"]
    assert len(detail["verdict_history"]) == 2
    history = client.get(f"/api/statements/{st['id']}/verdicts").json()
    assert {h["id"] for h in history} == {v1["id"], v2["id"]}
    idx = client.get(f"/api/index/persons/{p['id']}").json()
    assert idx["active_verdicts"] == 1
    assert idx["score"] == 1.0


def test_correction_rejects_foreign_verdict(client):
    p = _person(client)
    st1 = _statement(client, p["id"], quote="A")
    st2 = _statement(client, p["id"], quote="B")
    v1 = _verdict(client, st1["id"], "faux")
    r = client.post(
        f"/api/statements/{st2['id']}/verdicts",
        json={
            "rating": "vrai",
            "justification": "j",
            "sources": [{"url": "https://x.fr"}],
            "supersedes": v1["id"],
        },
    )
    assert r.status_code == 400


def test_droit_de_reponse(client):
    p = _person(client)
    st = _statement(client, p["id"])
    v = _verdict(client, st["id"], "trompeur")
    r = client.post(
        f"/api/verdicts/{v['id']}/responses",
        json={
            "author_name": "Porte-parole de X",
            "author_capacity": "porte-parole",
            "content": "Nous contestons ce verdict.",
        },
    )
    assert r.status_code == 201, r.text
    detail = client.get(f"/api/statements/{st['id']}").json()
    responses = detail["current_verdict"]["responses"]
    assert len(responses) == 1
    assert responses[0]["content"] == "Nous contestons ce verdict."


def test_soft_delete_person_excluded_from_lists_and_index(client):
    org = _org(client)
    p = _person(client, org_id=org["id"])
    st = _statement(client, p["id"])
    _verdict(client, st["id"], "vrai")
    r = client.delete(f"/api/persons/{p['id']}")
    assert r.status_code == 200
    assert client.get(f"/api/persons/{p['id']}").status_code == 404
    assert all(x["id"] != p["id"] for x in client.get("/api/persons").json())
    assert client.get(f"/api/index/persons/{p['id']}").status_code == 404
    org_idx = client.get(f"/api/index/organizations/{org['id']}").json()
    assert org_idx["active_verdicts"] == 0
    assert org_idx["score"] is None


def test_rating_filter(client):
    p = _person(client)
    st1 = _statement(client, p["id"], quote="A")
    st2 = _statement(client, p["id"], quote="B")
    _verdict(client, st1["id"], "vrai")
    _verdict(client, st2["id"], "faux")
    r = client.get("/api/statements", params={"rating": "faux"})
    assert r.status_code == 200
    assert [s["id"] for s in r.json()] == [st2["id"]]


def test_schema_has_no_gender_field():
    from app.models import Person

    column_names = {c.name.lower() for c in Person.__table__.columns}
    assert not any(name in column_names for name in ("gender", "sexe", "genre"))


def test_html_pages_render(client):
    assert client.get("/").status_code == 200
    assert client.get("/index").status_code == 200
    org = _org(client)
    p = _person(client, org_id=org["id"])
    st = _statement(client, p["id"])
    v = _verdict(client, st["id"], "vrai")
    assert client.get(f"/statements/{st['id']}").status_code == 200
    assert client.get(f"/persons/{p['id']}").status_code == 200
    assert client.get("/new/statement").status_code == 200
    assert client.get("/new/person").status_code == 200
    assert client.get("/new/organization").status_code == 200
    assert client.get(f"/statements/{st['id']}/new/verdict").status_code == 200
    assert client.get(f"/verdicts/{v['id']}/new/response").status_code == 200


def test_html_forms_end_to_end(client):
    no_follow = {"follow_redirects": False}
    r = client.post("/new/organization", data={"name": "Media Test", "kind": "media"}, **no_follow)
    assert r.status_code == 303
    r = client.post(
        "/new/person",
        data={"name": "Marie Test", "role": "députée", "is_public_figure": "on"},
        **no_follow,
    )
    assert r.status_code == 303
    person = client.get("/api/persons").json()[0]
    assert person["is_public_figure"] is True
    r = client.post(
        "/new/statement",
        data={
            "person_id": str(person["id"]),
            "quote": "Déclaration test",
            "source_url": "https://x.fr/dep",
            "said_at": "2024-05-01",
        },
        **no_follow,
    )
    assert r.status_code == 303
    st = client.get("/api/statements").json()[0]
    assert st["said_at"] == "2024-05-01"
    r = client.post(
        f"/statements/{st['id']}/new/verdict",
        data={
            "rating": "vrai",
            "justification": "Confirmé par deux sources.",
            "sources_text": "https://x.fr/a\nhttps://x.fr/b",
        },
        **no_follow,
    )
    assert r.status_code == 303
    detail = client.get(f"/api/statements/{st['id']}").json()
    assert detail["current_verdict"]["rating"] == "vrai"
    assert len(detail["current_verdict"]["sources"]) == 2
    verdict_id = detail["current_verdict"]["id"]
    r = client.post(
        f"/verdicts/{verdict_id}/new/response",
        data={"author_name": "Service de presse", "content": "Pris note."},
        **no_follow,
    )
    assert r.status_code == 303
    detail = client.get(f"/api/statements/{st['id']}").json()
    assert len(detail["current_verdict"]["responses"]) == 1


def test_verdict_form_requires_sources(client):
    p = _person(client)
    st = _statement(client, p["id"])
    r = client.post(
        f"/statements/{st['id']}/new/verdict",
        data={"rating": "faux", "justification": "x", "sources_text": "  "},
    )
    assert r.status_code == 200
    assert "obligatoire" in r.text
    assert client.get(f"/api/statements/{st['id']}").json()["current_verdict"] is None

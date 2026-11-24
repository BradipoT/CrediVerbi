def _person(client, name="Jean Exemple"):
    r = client.post(
        "/api/persons",
        json={"name": name, "role": "élu", "is_public_figure": True},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _proposal(client, person_id, quote="Les impôts ont baissé de 30 %."):
    r = client.post(
        "/api/proposals",
        json={
            "person_id": person_id,
            "quote": quote,
            "source_url": "https://exemple.fr/itw",
            "said_at": "2024-06-01",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _published_statement(client, person_id, quote="Déclaration publiée", rating="faux"):
    payload = {"person_id": person_id, "quote": quote, "source_url": "https://exemple.fr/dep"}
    st = client.post("/api/statements", json=payload).json()
    v = client.post(
        f"/api/statements/{st['id']}/verdicts",
        json={
            "rating": rating,
            "justification": "Contrredit par la source primaire.",
            "sources": [{"url": "https://exemple.fr/preuve"}],
        },
    ).json()
    assert v["rating"] == rating
    return st


def _approve(client, statement_id, rating="faux"):
    r = client.post(
        f"/api/moderation/statements/{statement_id}/decision",
        json={
            "action": "approve",
            "rating": rating,
            "justification": "Vérifié : chiffre contredit par la source.",
            "sources": [{"url": "https://exemple.fr/preuve", "title": "Preuve"}],
            "decided_by": "modération",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_proposal_is_pending_and_invisible(client):
    p = _person(client)
    st = _proposal(client, p["id"])
    assert st["status"] == "pending"
    assert client.get(f"/api/statements/{st['id']}").status_code == 404
    assert all(s["id"] != st["id"] for s in client.get("/api/statements").json())
    assert "impôts" not in client.get("/").text
    idx = client.get(f"/api/index/persons/{p['id']}").json()
    assert idx["active_verdicts"] == 0
    pending = client.get("/api/moderation/pending").json()
    assert [s["id"] for s in pending["statements"]] == [st["id"]]
    r = client.post(
        f"/api/statements/{st['id']}/verdicts",
        json={
            "rating": "faux",
            "justification": "x",
            "sources": [{"url": "https://x.fr"}],
        },
    )
    assert r.status_code == 400


def test_proposal_requires_public_figure(client):
    r = client.post(
        "/api/persons", json={"name": "Anonyme", "is_public_figure": False}
    )
    p = r.json()
    r = client.post(
        "/api/proposals", json={"person_id": p["id"], "quote": "x"}
    )
    assert r.status_code == 400


def test_approve_publishes_with_verdict(client):
    p = _person(client)
    st = _proposal(client, p["id"])
    decided = _approve(client, st["id"], rating="faux")
    assert decided["status"] == "published"
    assert decided["current_verdict"]["rating"] == "faux"
    assert len(decided["current_verdict"]["sources"]) == 1
    assert client.get(f"/api/statements/{st['id']}").status_code == 200
    assert any(s["id"] == st["id"] for s in client.get("/api/statements").json())
    assert "impôts" in client.get("/").text
    idx = client.get(f"/api/index/persons/{p['id']}").json()
    assert idx["active_verdicts"] == 1
    assert idx["counts"]["faux"] == 1
    assert idx["score"] == 0.0
    pending = client.get("/api/moderation/pending").json()
    assert pending["statements"] == []
    r = client.post(
        f"/api/moderation/statements/{st['id']}/decision",
        json={"action": "reject"},
    )
    assert r.status_code == 404


def test_approve_requires_complete_verdict(client):
    p = _person(client)
    st = _proposal(client, p["id"])
    r = client.post(
        f"/api/moderation/statements/{st['id']}/decision",
        json={"action": "approve", "rating": "faux", "justification": "", "sources": []},
    )
    assert r.status_code == 422
    r = client.post(
        f"/api/moderation/statements/{st['id']}/decision", json={"action": "reject"}
    )
    assert r.status_code == 200
    decided = r.json()
    assert decided["status"] == "rejected"
    assert client.get(f"/api/statements/{st['id']}").status_code == 404
    assert "impôts" not in client.get("/").text


def test_appeal_keeps_statement_visible_until_rereviewed(client):
    p = _person(client)
    st = _published_statement(client, p["id"])
    r = client.post(
        f"/api/statements/{st['id']}/appeals", json={"reason": "La source primaire dit l'inverse."}
    )
    assert r.status_code == 201, r.text
    appeal = r.json()
    assert appeal["status"] == "pending"
    detail = client.get(f"/api/statements/{st['id']}").json()
    assert detail["status"] == "under_review"
    assert any(s["id"] == st["id"] for s in client.get("/api/statements").json())
    assert "Déclaration publiée" in client.get("/").text
    assert "sous réexamen" in client.get(f"/statements/{st['id']}").text
    pending = client.get("/api/moderation/pending").json()
    assert [a["id"] for a in pending["appeals"]] == [appeal["id"]]


def test_appeal_on_hidden_statement_is_404(client):
    p = _person(client)
    st = _proposal(client, p["id"])
    r = client.post(f"/api/statements/{st['id']}/appeals", json={"reason": "x"})
    assert r.status_code == 404


def test_resolve_keep_restores_published(client):
    p = _person(client)
    st = _published_statement(client, p["id"], rating="faux")
    appeal = client.post(
        f"/api/statements/{st['id']}/appeals", json={"reason": "Contestation."}
    ).json()
    r = client.post(
        f"/api/moderation/appeals/{appeal['id']}/resolve",
        json={"resolution": "keep", "resolved_by": "modération"},
    )
    assert r.status_code == 200, r.text
    resolved = r.json()
    assert resolved["status"] == "resolved"
    assert resolved["resolution"] == "kept"
    detail = client.get(f"/api/statements/{st['id']}").json()
    assert detail["status"] == "published"
    assert detail["current_verdict"]["rating"] == "faux"
    assert len(detail["verdict_history"]) == 1
    r = client.post(
        f"/api/moderation/appeals/{appeal['id']}/resolve",
        json={"resolution": "keep"},
    )
    assert r.status_code == 404


def test_resolve_update_changes_verdict_and_score(client):
    p = _person(client)
    st = _published_statement(client, p["id"], rating="faux")
    appeal = client.post(
        f"/api/statements/{st['id']}/appeals", json={"reason": "Nouvelle source."}
    ).json()
    r = client.post(
        f"/api/moderation/appeals/{appeal['id']}/resolve",
        json={
            "resolution": "update",
            "rating": "partiellement_vrai",
            "justification": "Chiffre exagéré mais tendance réelle.",
            "sources": [{"url": "https://exemple.fr/nouvelle-preuve"}],
            "resolved_by": "modération",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["resolution"] == "verdict_updated"
    detail = client.get(f"/api/statements/{st['id']}").json()
    assert detail["status"] == "published"
    assert detail["current_verdict"]["rating"] == "partiellement_vrai"
    assert len(detail["verdict_history"]) == 2
    idx = client.get(f"/api/index/persons/{p['id']}").json()
    assert idx["score"] == 0.5
    r = client.post(
        f"/api/moderation/appeals/{appeal['id']}/resolve",
        json={"resolution": "update", "rating": "vrai", "justification": "x", "sources": []},
    )
    assert r.status_code == 422
    r = client.post(
        f"/api/moderation/appeals/{appeal['id']}/resolve",
        json={"resolution": "keep"},
    )
    assert r.status_code == 404


def test_resolve_remove_hides_statement_and_closes_all_appeals(client):
    p = _person(client)
    st = _published_statement(client, p["id"])
    a1 = client.post(
        f"/api/statements/{st['id']}/appeals", json={"reason": "Dénonciation 1."}
    ).json()
    a2 = client.post(
        f"/api/statements/{st['id']}/appeals", json={"reason": "Dénonciation 2."}
    ).json()
    r = client.post(
        f"/api/moderation/appeals/{a1['id']}/resolve",
        json={"resolution": "remove", "resolved_by": "modération"},
    )
    assert r.status_code == 200
    assert r.json()["resolution"] == "removed"
    assert client.get(f"/api/statements/{st['id']}").status_code == 404
    assert all(s["id"] != st["id"] for s in client.get("/api/statements").json())
    assert "Déclaration publiée" not in client.get("/").text
    idx = client.get(f"/api/index/persons/{p['id']}").json()
    assert idx["active_verdicts"] == 0
    pending = client.get("/api/moderation/pending").json()
    assert pending["appeals"] == []
    r = client.post(
        f"/api/moderation/appeals/{a2['id']}/resolve", json={"resolution": "keep"}
    )
    assert r.status_code == 404


def test_second_appeal_keeps_under_review_until_all_resolved(client):
    p = _person(client)
    st = _published_statement(client, p["id"])
    a1 = client.post(
        f"/api/statements/{st['id']}/appeals", json={"reason": "r1"}
    ).json()
    a2 = client.post(
        f"/api/statements/{st['id']}/appeals", json={"reason": "r2"}
    ).json()
    client.post(f"/api/moderation/appeals/{a1['id']}/resolve", json={"resolution": "keep"})
    detail = client.get(f"/api/statements/{st['id']}").json()
    assert detail["status"] == "under_review"
    client.post(f"/api/moderation/appeals/{a2['id']}/resolve", json={"resolution": "keep"})
    detail = client.get(f"/api/statements/{st['id']}").json()
    assert detail["status"] == "published"


def test_html_public_proposal_and_appeal_forms(client):
    p = _person(client)
    assert client.get("/new/proposal").status_code == 200
    no_follow = {"follow_redirects": False}
    r = client.post(
        "/new/proposal",
        data={"person_id": str(p["id"]), "quote": "Proposition HTML", "source_url": "https://x.fr"},
    )
    assert r.status_code == 200
    assert "attente de modération" in r.text
    st = client.get("/api/moderation/pending").json()["statements"][0]
    assert st["quote"] == "Proposition HTML"
    assert client.get(f"/statements/{st['id']}").status_code == 404
    assert client.get("/moderation").status_code == 200
    r = client.post(
        f"/moderation/statements/{st['id']}/decision",
        data={
            "action": "approve",
            "rating": "trompeur",
            "justification": "Chiffre exagéré.",
            "sources_text": "https://x.fr/preuve",
            "decided_by": "modo",
        },
        **no_follow,
    )
    assert r.status_code == 303
    assert client.get(f"/statements/{st['id']}").status_code == 200
    assert client.get(f"/statements/{st['id']}/new/appeal").status_code == 200
    r = client.post(
        f"/statements/{st['id']}/new/appeal",
        data={"reason": "Je conteste ce verdict."},
        **no_follow,
    )
    assert r.status_code == 303
    detail = client.get(f"/api/statements/{st['id']}").json()
    assert detail["status"] == "under_review"
    appeal = client.get("/api/moderation/pending").json()["appeals"][0]
    r = client.post(
        f"/moderation/appeals/{appeal['id']}/resolve",
        data={"resolution": "remove", "resolved_by": "modo"},
        **no_follow,
    )
    assert r.status_code == 303
    assert client.get(f"/api/statements/{st['id']}").status_code == 404

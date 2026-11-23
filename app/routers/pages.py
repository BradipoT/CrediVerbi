from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import services
from ..db import get_db
from ..models import (
    RATING_LABELS,
    Organization,
    Person,
    Response,
    Statement,
    Verdict,
    VerdictRating,
    VerdictSource,
)
from .api import require_editor

router = APIRouter()
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


def _rows(db: Session, statements):
    rows = []
    for statement in statements:
        verdict = services.current_verdict(statement)
        rows.append(
            {
                "statement": statement,
                "rating": verdict.rating.value if verdict else None,
                "rating_label": RATING_LABELS[verdict.rating] if verdict else "Non évalué",
            }
        )
    return rows


def _public_persons(db: Session):
    return (
        db.query(Person)
        .filter(Person.deleted_at.is_(None), Person.is_public_figure.is_(True))
        .order_by(Person.name)
        .all()
    )


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    statements = (
        db.query(Statement)
        .join(Person)
        .filter(Person.deleted_at.is_(None))
        .order_by(Statement.created_at.desc())
        .limit(50)
        .all()
    )
    return templates.TemplateResponse(
        request, "home.html", {"rows": _rows(db, statements)}
    )


@router.get("/statements/{statement_id}")
def statement_page(request: Request, statement_id: int, db: Session = Depends(get_db)):
    statement = db.get(Statement, statement_id)
    if statement is None:
        raise HTTPException(status_code=404, detail="Déclaration inconnue")
    return templates.TemplateResponse(
        request,
        "statement_detail.html",
        {
            "st": statement,
            "current": services.current_verdict(statement),
            "rating_labels": RATING_LABELS,
        },
    )


@router.get("/persons/{person_id}")
def person_page(request: Request, person_id: int, db: Session = Depends(get_db)):
    index = services.person_index(db, person_id)
    if index is None:
        raise HTTPException(status_code=404, detail="Personne inconnue")
    statements = (
        db.query(Statement)
        .filter(Statement.person_id == person_id)
        .order_by(Statement.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "person.html",
        {"index": index, "rows": _rows(db, statements), "rating_labels": RATING_LABELS},
    )


@router.get("/index")
def index_page(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "methodology": services.METHODOLOGY,
            "persons": services.all_persons_index(db),
            "organizations": services.all_organizations_index(db),
        },
    )


@router.get("/new/organization")
def new_organization_form(request: Request):
    return templates.TemplateResponse(request, "organization_form.html", {})


@router.post("/new/organization", dependencies=[Depends(require_editor)])
def new_organization(
    request: Request,
    name: str = Form(...),
    kind: str = Form("autre"),
    db: Session = Depends(get_db),
):
    if db.query(Organization).filter(Organization.name == name).first():
        return templates.TemplateResponse(
            request,
            "organization_form.html",
            {"error": "Une organisation porte déjà ce nom."},
        )
    org = Organization(name=name, kind=kind)
    db.add(org)
    db.commit()
    return RedirectResponse(url="/index", status_code=303)


@router.get("/new/person")
def new_person_form(request: Request, db: Session = Depends(get_db)):
    organizations = db.query(Organization).order_by(Organization.name).all()
    return templates.TemplateResponse(
        request, "person_form.html", {"organizations": organizations}
    )


@router.post("/new/person", dependencies=[Depends(require_editor)])
def new_person(
    request: Request,
    name: str = Form(...),
    role: str | None = Form(None),
    organization_id: int | None = Form(None),
    is_public_figure: bool = Form(False),
    db: Session = Depends(get_db),
):
    organizations = db.query(Organization).order_by(Organization.name).all()
    if organization_id is not None and db.get(Organization, organization_id) is None:
        return templates.TemplateResponse(
            request,
            "person_form.html",
            {"organizations": organizations, "error": "Organisation inconnue."},
        )
    person = Person(
        name=name,
        role=role or None,
        organization_id=organization_id,
        is_public_figure=is_public_figure,
    )
    db.add(person)
    db.commit()
    return RedirectResponse(url=f"/persons/{person.id}", status_code=303)


@router.get("/new/statement")
def new_statement_form(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request, "statement_form.html", {"persons": _public_persons(db)}
    )


@router.post("/new/statement", dependencies=[Depends(require_editor)])
def new_statement(
    request: Request,
    person_id: int = Form(...),
    quote: str = Form(...),
    context: str | None = Form(None),
    source_url: str | None = Form(None),
    source_title: str | None = Form(None),
    said_at: str | None = Form(None),
    db: Session = Depends(get_db),
):
    person = db.get(Person, person_id)
    if person is None or person.deleted_at is not None or not person.is_public_figure:
        return templates.TemplateResponse(
            request,
            "statement_form.html",
            {
                "persons": _public_persons(db),
                "error": "Seules les personnalités publiques peuvent faire l'objet d'une déclaration.",
            },
        )
    said_date = None
    if said_at:
        try:
            said_date = date.fromisoformat(said_at)
        except ValueError:
            return templates.TemplateResponse(
                request,
                "statement_form.html",
                {"persons": _public_persons(db), "error": "Date invalide (format AAAA-MM-JJ)."},
            )
    statement = Statement(
        person_id=person_id,
        quote=quote,
        context=context or None,
        source_url=source_url or None,
        source_title=source_title or None,
        said_at=said_date,
    )
    db.add(statement)
    db.commit()
    return RedirectResponse(url=f"/statements/{statement.id}", status_code=303)


@router.get("/statements/{statement_id}/new/verdict")
def new_verdict_form(
    request: Request,
    statement_id: int,
    supersedes: int | None = None,
    db: Session = Depends(get_db),
):
    statement = db.get(Statement, statement_id)
    if statement is None:
        raise HTTPException(status_code=404, detail="Déclaration inconnue")
    return templates.TemplateResponse(
        request,
        "verdict_form.html",
        {"st": statement, "ratings": RATING_LABELS, "supersedes": supersedes},
    )


@router.post(
    "/statements/{statement_id}/new/verdict", dependencies=[Depends(require_editor)]
)
def new_verdict(
    request: Request,
    statement_id: int,
    rating: VerdictRating = Form(...),
    justification: str = Form(...),
    sources_text: str = Form(...),
    created_by: str | None = Form(None),
    supersedes: int | None = Form(None),
    db: Session = Depends(get_db),
):
    statement = db.get(Statement, statement_id)
    if statement is None:
        raise HTTPException(status_code=404, detail="Déclaration inconnue")
    urls = [line.strip() for line in sources_text.splitlines() if line.strip()]
    if not urls:
        return templates.TemplateResponse(
            request,
            "verdict_form.html",
            {
                "st": statement,
                "ratings": RATING_LABELS,
                "supersedes": supersedes,
                "error": "Au moins une source (URL) est obligatoire pour publier un verdict.",
            },
        )
    verdict = Verdict(
        statement_id=statement_id,
        rating=rating,
        justification=justification,
        created_by=created_by or None,
    )
    db.add(verdict)
    db.flush()
    for url in urls:
        db.add(VerdictSource(verdict_id=verdict.id, url=url))
    if supersedes is not None:
        old = db.get(Verdict, supersedes)
        if old is not None and old.statement_id == statement_id and old.replaced_by_id is None:
            old.replaced_by_id = verdict.id
    db.commit()
    return RedirectResponse(url=f"/statements/{statement_id}", status_code=303)


@router.get("/verdicts/{verdict_id}/new/response")
def new_response_form(request: Request, verdict_id: int, db: Session = Depends(get_db)):
    verdict = db.get(Verdict, verdict_id)
    if verdict is None:
        raise HTTPException(status_code=404, detail="Verdict inconnu")
    return templates.TemplateResponse(request, "response_form.html", {"verdict": verdict})


@router.post(
    "/verdicts/{verdict_id}/new/response", dependencies=[Depends(require_editor)]
)
def new_response(
    request: Request,
    verdict_id: int,
    author_name: str = Form(...),
    author_capacity: str | None = Form(None),
    content: str = Form(...),
    db: Session = Depends(get_db),
):
    verdict = db.get(Verdict, verdict_id)
    if verdict is None:
        raise HTTPException(status_code=404, detail="Verdict inconnu")
    db.add(
        Response(
            verdict_id=verdict_id,
            author_name=author_name,
            author_capacity=author_capacity or None,
            content=content,
        )
    )
    db.commit()
    return RedirectResponse(url=f"/statements/{verdict.statement_id}", status_code=303)

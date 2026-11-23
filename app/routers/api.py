from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import services
from ..config import settings
from ..db import get_db
from ..models import (
    Organization,
    Person,
    Response,
    Statement,
    Verdict,
    VerdictRating,
    VerdictSource,
)
from ..schemas import (
    OrganizationCreate,
    PersonCreate,
    ResponseCreate,
    StatementCreate,
    VerdictCreate,
)

router = APIRouter()


def require_editor(request: Request) -> None:
    if settings.token and request.headers.get("Authorization") != f"Bearer {settings.token}":
        raise HTTPException(
            status_code=401,
            detail="Jeton requis : Authorization: Bearer <CREDIVERBI_TOKEN>",
        )


def person_to_dict(person: Person) -> dict:
    return {
        "id": person.id,
        "name": person.name,
        "role": person.role,
        "organization_id": person.organization_id,
        "organization_name": person.organization.name if person.organization else None,
        "is_public_figure": person.is_public_figure,
    }


def verdict_to_dict(verdict: Verdict) -> dict:
    return {
        "id": verdict.id,
        "statement_id": verdict.statement_id,
        "rating": verdict.rating.value,
        "justification": verdict.justification,
        "created_by": verdict.created_by,
        "created_at": verdict.created_at.isoformat() if verdict.created_at else None,
        "is_current": verdict.replaced_by_id is None,
        "replaced_by_id": verdict.replaced_by_id,
        "sources": [
            {"id": s.id, "url": s.url, "title": s.title} for s in verdict.sources
        ],
        "responses": [
            {
                "id": r.id,
                "author_name": r.author_name,
                "author_capacity": r.author_capacity,
                "content": r.content,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in verdict.responses
        ],
    }


def statement_to_dict(statement: Statement, detail: bool = False) -> dict:
    current = services.current_verdict(statement)
    data = {
        "id": statement.id,
        "person_id": statement.person_id,
        "person_name": statement.person.name if statement.person else None,
        "organization_name": (
            statement.person.organization.name
            if statement.person and statement.person.organization
            else None
        ),
        "quote": statement.quote,
        "context": statement.context,
        "source_url": statement.source_url,
        "source_title": statement.source_title,
        "said_at": statement.said_at.isoformat() if statement.said_at else None,
        "created_at": statement.created_at.isoformat() if statement.created_at else None,
        "current_verdict": verdict_to_dict(current) if current else None,
    }
    if detail:
        data["verdict_history"] = [verdict_to_dict(v) for v in statement.verdicts]
    return data


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/organizations", status_code=201, dependencies=[Depends(require_editor)])
def create_organization(payload: OrganizationCreate, db: Session = Depends(get_db)):
    if db.query(Organization).filter(Organization.name == payload.name).first():
        raise HTTPException(status_code=400, detail="Organisation déjà enregistrée")
    org = Organization(name=payload.name, kind=payload.kind)
    db.add(org)
    db.commit()
    db.refresh(org)
    return {"id": org.id, "name": org.name, "kind": org.kind}


@router.get("/organizations")
def list_organizations(db: Session = Depends(get_db)):
    orgs = db.query(Organization).order_by(Organization.name).all()
    return [{"id": o.id, "name": o.name, "kind": o.kind} for o in orgs]


@router.post("/persons", status_code=201, dependencies=[Depends(require_editor)])
def create_person(payload: PersonCreate, db: Session = Depends(get_db)):
    if payload.organization_id is not None and db.get(Organization, payload.organization_id) is None:
        raise HTTPException(status_code=400, detail="Organisation inconnue")
    person = Person(**payload.model_dump())
    db.add(person)
    db.commit()
    db.refresh(person)
    return person_to_dict(person)


@router.get("/persons")
def list_persons(db: Session = Depends(get_db)):
    persons = (
        db.query(Person).filter(Person.deleted_at.is_(None)).order_by(Person.name).all()
    )
    return [person_to_dict(p) for p in persons]


@router.get("/persons/{person_id}")
def get_person(person_id: int, db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if person is None or person.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Personne inconnue")
    data = person_to_dict(person)
    data["index"] = services.person_index(db, person_id)
    return data


@router.delete("/persons/{person_id}", dependencies=[Depends(require_editor)])
def delete_person(person_id: int, db: Session = Depends(get_db)):
    person = db.get(Person, person_id)
    if person is None or person.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Personne inconnue")
    person.deleted_at = func.now()
    db.commit()
    return {"status": "supprimée", "id": person_id}


@router.post("/statements", status_code=201, dependencies=[Depends(require_editor)])
def create_statement(payload: StatementCreate, db: Session = Depends(get_db)):
    person = db.get(Person, payload.person_id)
    if person is None or person.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Personne inconnue")
    if not person.is_public_figure:
        raise HTTPException(
            status_code=400,
            detail="Seules les personnalités publiques (is_public_figure=true) "
            "peuvent faire l'objet d'une déclaration",
        )
    statement = Statement(**payload.model_dump())
    db.add(statement)
    db.commit()
    db.refresh(statement)
    return statement_to_dict(statement)


@router.get("/statements")
def list_statements(
    person_id: int | None = None,
    rating: VerdictRating | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Statement).join(Person).filter(Person.deleted_at.is_(None))
    if person_id is not None:
        query = query.filter(Statement.person_id == person_id)
    if rating is not None:
        query = query.join(
            Verdict,
            (Verdict.statement_id == Statement.id) & (Verdict.replaced_by_id.is_(None)),
        ).filter(Verdict.rating == rating)
    statements = query.order_by(Statement.created_at.desc()).limit(100).all()
    return [statement_to_dict(s) for s in statements]


@router.get("/statements/{statement_id}")
def get_statement(statement_id: int, db: Session = Depends(get_db)):
    statement = db.get(Statement, statement_id)
    if statement is None:
        raise HTTPException(status_code=404, detail="Déclaration inconnue")
    return statement_to_dict(statement, detail=True)


@router.post(
    "/statements/{statement_id}/verdicts",
    status_code=201,
    dependencies=[Depends(require_editor)],
)
def create_verdict(
    statement_id: int, payload: VerdictCreate, db: Session = Depends(get_db)
):
    statement = db.get(Statement, statement_id)
    if statement is None:
        raise HTTPException(status_code=404, detail="Déclaration inconnue")
    superseded = None
    if payload.supersedes is not None:
        superseded = db.get(Verdict, payload.supersedes)
        if (
            superseded is None
            or superseded.statement_id != statement_id
            or superseded.replaced_by_id is not None
        ):
            raise HTTPException(
                status_code=400,
                detail="Verdict à remplacer invalide : inconnu, déjà remplacé "
                "ou rattaché à une autre déclaration",
            )
    verdict = Verdict(
        statement_id=statement_id,
        rating=payload.rating,
        justification=payload.justification,
        created_by=payload.created_by,
    )
    db.add(verdict)
    db.flush()
    for source in payload.sources:
        db.add(VerdictSource(verdict_id=verdict.id, url=source.url, title=source.title))
    if superseded is not None:
        superseded.replaced_by_id = verdict.id
    db.commit()
    db.refresh(verdict)
    return verdict_to_dict(verdict)


@router.get("/statements/{statement_id}/verdicts")
def list_verdicts(statement_id: int, db: Session = Depends(get_db)):
    statement = db.get(Statement, statement_id)
    if statement is None:
        raise HTTPException(status_code=404, detail="Déclaration inconnue")
    return [verdict_to_dict(v) for v in statement.verdicts]


@router.post(
    "/verdicts/{verdict_id}/responses",
    status_code=201,
    dependencies=[Depends(require_editor)],
)
def create_response(
    verdict_id: int, payload: ResponseCreate, db: Session = Depends(get_db)
):
    verdict = db.get(Verdict, verdict_id)
    if verdict is None:
        raise HTTPException(status_code=404, detail="Verdict inconnu")
    response = Response(verdict_id=verdict_id, **payload.model_dump())
    db.add(response)
    db.commit()
    db.refresh(response)
    return {
        "id": response.id,
        "verdict_id": response.verdict_id,
        "author_name": response.author_name,
        "author_capacity": response.author_capacity,
        "content": response.content,
        "created_at": response.created_at.isoformat() if response.created_at else None,
    }


@router.get("/index")
def global_index(db: Session = Depends(get_db)):
    return {
        "methodology": services.METHODOLOGY,
        "persons": services.all_persons_index(db),
        "organizations": services.all_organizations_index(db),
    }


@router.get("/index/persons/{person_id}")
def person_index(person_id: int, db: Session = Depends(get_db)):
    index = services.person_index(db, person_id)
    if index is None:
        raise HTTPException(status_code=404, detail="Personne inconnue")
    return index


@router.get("/index/organizations/{organization_id}")
def organization_index(organization_id: int, db: Session = Depends(get_db)):
    index = services.organization_index(db, organization_id)
    if index is None:
        raise HTTPException(status_code=404, detail="Organisation inconnue")
    return index

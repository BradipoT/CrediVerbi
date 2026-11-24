from sqlalchemy.orm import Session

from .models import (
    Organization,
    Person,
    Statement,
    Verdict,
    VerdictRating,
)

RATING_SCORES = {
    VerdictRating.VRAI: 1.0,
    VerdictRating.PARTIELLEMENT_VRAI: 0.5,
    VerdictRating.TROMPLEUR: 0.25,
    VerdictRating.FAUX: 0.0,
}

VISIBLE_STATUSES = ("published", "under_review")

METHODOLOGY = (
    "Indice = moyenne des notes des verdicts actifs de la personne ou de "
    "l'organisation : vrai = 1,0 ; partiellement vrai = 0,5 ; trompeur = 0,25 ; "
    "faux = 0 ; indéterminé compté à part et exclu du calcul. Un seul verdict "
    "actif par déclaration : une correction remplace le verdict précédent, qui "
    "reste consultable dans l'historique."
)


def current_verdict(statement: Statement) -> Verdict | None:
    for verdict in statement.verdicts:
        if verdict.replaced_by_id is None:
            return verdict
    return None


def _build_index(statements, subject: dict) -> dict:
    counts = {rating.value: 0 for rating in VerdictRating}
    scored_count = 0
    score_sum = 0.0
    for statement in statements:
        verdict = current_verdict(statement)
        if verdict is None:
            continue
        counts[verdict.rating.value] += 1
        score = RATING_SCORES.get(verdict.rating)
        if score is not None:
            score_sum += score
            scored_count += 1
    return {
        "subject": subject,
        "active_verdicts": sum(counts.values()),
        "counts": counts,
        "scored_verdicts": scored_count,
        "score": round(score_sum / scored_count, 3) if scored_count else None,
        "methodology": METHODOLOGY,
    }


def person_index(db: Session, person_id: int) -> dict | None:
    person = db.get(Person, person_id)
    if person is None or person.deleted_at is not None:
        return None
    subject = {
        "type": "person",
        "id": person.id,
        "name": person.name,
        "role": person.role,
        "organization": person.organization.name if person.organization else None,
    }
    statements = [s for s in person.statements if s.status in VISIBLE_STATUSES]
    return _build_index(statements, subject)


def organization_index(db: Session, organization_id: int) -> dict | None:
    org = db.get(Organization, organization_id)
    if org is None:
        return None
    statements = (
        db.query(Statement)
        .join(Person)
        .filter(
            Person.organization_id == org.id,
            Person.deleted_at.is_(None),
            Statement.status.in_(VISIBLE_STATUSES),
        )
        .all()
    )
    subject = {"type": "organization", "id": org.id, "name": org.name, "kind": org.kind}
    return _build_index(statements, subject)


def all_persons_index(db: Session) -> list[dict]:
    persons = (
        db.query(Person).filter(Person.deleted_at.is_(None)).order_by(Person.name).all()
    )
    return [person_index(db, p.id) for p in persons]


def all_organizations_index(db: Session) -> list[dict]:
    orgs = db.query(Organization).order_by(Organization.name).all()
    return [organization_index(db, o.id) for o in orgs]

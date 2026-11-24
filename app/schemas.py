from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .models import VerdictRating


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="autre", max_length=50)


class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str | None = Field(default=None, max_length=200)
    organization_id: int | None = None
    is_public_figure: bool = False


class SourceCreate(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    title: str | None = Field(default=None, max_length=500)


class StatementCreate(BaseModel):
    person_id: int
    quote: str = Field(min_length=1)
    context: str | None = None
    source_url: str | None = Field(default=None, max_length=2000)
    source_title: str | None = Field(default=None, max_length=500)
    said_at: date | None = None


class VerdictCreate(BaseModel):
    rating: VerdictRating
    justification: str = Field(min_length=1)
    created_by: str | None = Field(default=None, max_length=200)
    sources: list[SourceCreate] = Field(min_length=1)
    supersedes: int | None = None


class ResponseCreate(BaseModel):
    author_name: str = Field(min_length=1, max_length=200)
    author_capacity: str | None = Field(default=None, max_length=200)
    content: str = Field(min_length=1)


class AppealCreate(BaseModel):
    reason: str = Field(min_length=1)


class ModerationDecision(BaseModel):
    action: Literal["approve", "reject"]
    rating: VerdictRating | None = None
    justification: str | None = None
    sources: list[SourceCreate] = Field(default_factory=list)
    decided_by: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check_approve(self):
        if self.action == "approve" and (
            self.rating is None or not (self.justification or "").strip() or not self.sources
        ):
            raise ValueError(
                "Approuver exige un verdict complet : note + justification + au moins une source"
            )
        return self


class AppealResolve(BaseModel):
    resolution: Literal["keep", "update", "remove"]
    rating: VerdictRating | None = None
    justification: str | None = None
    sources: list[SourceCreate] = Field(default_factory=list)
    resolved_by: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check_update(self):
        if self.resolution == "update" and (
            self.rating is None or not (self.justification or "").strip() or not self.sources
        ):
            raise ValueError(
                "Modifier le verdict exige un verdict complet : note + justification + au moins une source"
            )
        return self

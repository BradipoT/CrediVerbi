from datetime import date

from pydantic import BaseModel, Field

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

"""Schema for the LinkedIn job-posting summary.

This Pydantic model defines the fields that Claude fills via structured output.
Identifiers and field descriptions are in English (to match the rest of this
codebase), but the VALUES Claude produces are written in TURKISH: the whole point
of the summary panel is to let the user read long English job posts quickly in
Turkish. Fields that are not present in the posting are left as "" / empty list.
(Plain `str` with "" instead of `str | None`: nullable fields generate `anyOf`
unions in the JSON schema, which count heavily toward the structured-outputs
complexity limit and caused 400 "Schema is too complex".)

IMPORTANT: keep field descriptions SHORT. The structured-outputs API has a schema
complexity limit and descriptions count toward it — long descriptions cause a
400 "Schema is too complex" error. Detailed extraction rules belong in the
SYSTEM_PROMPT in summary_api.py, not here.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class WorkType(str, Enum):
    """Work arrangement stated in the posting."""

    REMOTE = "remote"
    HYBRID = "hybrid"
    ON_SITE = "on-site"
    UNSPECIFIED = "unspecified"


class JobSummary(BaseModel):
    """At-a-glance job summary. Free-text values in Turkish; deliberately terse."""

    job_title: str = Field(
        default="", description="İlanda yazdığı haliyle pozisyon başlığı."
    )
    company: str = Field(
        default="", description="İlanda yazdığı haliyle işe alan şirketin adı."
    )
    role_summary: str = Field(
        description="1-2 kısa Türkçe cümle: adayın ne inşa edeceği/ne yapacağı."
    )
    work_type: WorkType = Field(
        description="Çalışma düzeni: remote, hybrid, on-site ya da unspecified."
    )
    work_type_note: str = Field(
        default="",
        description="Çok kısa Türkçe konum/saat dilimi koşulu, ör. 'İstanbul tercihli'.",
    )
    visa_sponsorship: str = Field(
        default="", description="Çok kısa Türkçe vize/sponsorluk notu; genellikle boş."
    )
    stack: list[list[str]] = Field(
        default_factory=list,
        description="Zorunlu teknolojiler, en fazla 6 grup; iç liste 'veya' alternatiflerini tutar.",
    )
    stack_known: list[list[bool]] = Field(
        default_factory=list,
        description="Sunucu doldurur: her stack seçeneği aday profilinde var mı?",
    )

    @field_validator("stack", mode="before")
    @classmethod
    def _wrap_bare_options(cls, value: object) -> object:
        """Tolerate a flat ['Docker', 'Redis'] from the model: each item is its own group.

        The prompt asks for a list of alternative-groups, but a plain string slips
        through often enough that rejecting it would burn the single JSON retry.
        """
        if isinstance(value, list):
            return [[item] if isinstance(item, str) else item for item in value]
        return value
    fit_score: int = Field(
        default=0, description="Aday profiline göre 0-100 uyum; bilinmiyorsa 0."
    )
    fit_reason: str = Field(
        default="",
        description="Çok kısa tek bir Türkçe yan cümle: 70+ ise uyanlar, değilse yalnızca eksikler.",
    )
    min_experience: str = Field(
        default="", description="Asgari deneyim, çok kısa Türkçe, ör. '3+ yıl'."
    )


class SummarizeRequest(BaseModel):
    """Request body for the /summarize endpoint."""

    text: str = Field(description="The job description text (may be in English).")
    title: str | None = Field(default=None, description="Job title.")
    company: str | None = Field(default=None, description="Company name.")
    location: str | None = Field(default=None, description="Location.")
    job_id: str | None = Field(
        default=None,
        description="LinkedIn job id; used as the server-side summary cache key.",
    )
    refresh: bool = Field(
        default=False,
        description="If true, ignore the cached summary and recompute, overwriting it.",
    )


class CoverLetterRequest(BaseModel):
    """Request body for the /cover-letter endpoint.

    Carries no job text: the letter is built from the CV and job description already
    saved on disk when the CV was generated, which is what makes it work after the
    posting is gone.
    """

    job_id: str = Field(description="LinkedIn job id; resolved to a CV No via the sheet.")
    lang: str = Field(default="en", description="Letter language: 'en' or 'tr'.")
    force: bool = Field(
        default=False,
        description="If true, regenerate even if a letter already exists (overwrites it).",
    )


class CoverLetterResponse(BaseModel):
    """Response body for the /cover-letter endpoint."""

    text: str = Field(description="The cover letter markdown.")
    cv_no: int = Field(description="CV No the letter belongs to.")
    lang: str = Field(description="Language the letter was written in.")
    created: bool = Field(
        description="True if the model was just called; False if read from disk."
    )


class AddJobRequest(BaseModel):
    """Request body for /add-job — the panel's "Ekle" button.

    Replaces the Huntr import as the "new job -> sheet row" source. It carries the
    posting text the panel already has so it can be STAGED: the poller's guest-view
    scrape stays primary, but when that fails (expired posting, LinkedIn wall) the CV is
    still generated from what the user actually read.
    """

    job_id: str = Field(description="LinkedIn job id (digits): row identity and file key.")
    url: str = Field(default="", description="Posting URL; canonicalized server-side.")
    title: str = Field(default="", max_length=300, description="Position title -> column L.")
    company: str = Field(default="", max_length=300, description="Company -> column J.")
    description: str = Field(
        default="",
        max_length=200_000,
        description="Posting text, staged as the CV-generation fallback.",
    )


class AddJobResponse(BaseModel):
    """Response body for /add-job."""

    status: str = Field(description="'added' (row appended) or 'exists' (already tracked).")
    row: int = Field(description="Sheet row number of the new or existing row.")
    cv_no: str = Field(
        default="",
        # A STRING, not an int: column N legitimately holds the non-numeric "Yok" marker.
        description="Raw column N: '' (pending), a number, or the 'Yok' marker.",
    )
    staged: bool = Field(
        default=False, description="True if the posting text was stored as the fallback."
    )

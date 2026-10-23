"""LinkedIn iş ilanı özetinin şeması.

Bu Pydantic modeli, panel özetinin dolduracağı alanları tanımlar. Tanımlayıcılar
İngilizce, ama Claude'un ürettiği DEĞERLER TÜRKÇE yazılır: özet panelinin bütün amacı,
kullanıcının uzun İngilizce ilanları Türkçe olarak hızlıca okumasını sağlamak. İlanda
olmayan alanlar "" / boş liste olarak bırakılır. (`str | None` yerine "" ile düz `str`:
null olabilen alanlar JSON şemasında `anyOf` birleşimleri üretir; bunlar structured
outputs karmaşıklık sınırına ağır sayılıyor ve 400 "Schema is too complex"e yol açtı.)

ÖNEMLİ: alan açıklamalarını KISA tut. Şema prompt'a gömülür; ayrıntılı çıkarma kuralları
buraya değil, prompts/ozet_sistem.md'ye aittir.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class WorkType(str, Enum):
    """İlanda belirtilen çalışma düzeni."""

    REMOTE = "remote"
    HYBRID = "hybrid"
    ON_SITE = "on-site"
    UNSPECIFIED = "unspecified"


class JobSummary(BaseModel):
    """Tek bakışta ilan özeti. Serbest metin değerleri Türkçe; bilerek kısa."""

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
        """Modelden gelen düz bir ['Docker', 'Redis']'i tolere eder: her öğe kendi grubudur.

        Prompt alternatif gruplarından oluşan bir liste istiyor, ama düz bir metin yeterince sık
        sızıyor; reddetmek tek JSON yeniden denemesini boşa harcardı.
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
    """/summarize uç noktasının istek gövdesi."""

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
    """/cover-letter uç noktasının istek gövdesi.

    İlan metni taşımaz: mektup, CV üretildiğinde diske zaten kaydedilmiş CV ve ilan metninden
    kurulur; ilan kalktıktan sonra da çalışmasını sağlayan budur.
    """

    job_id: str = Field(description="LinkedIn job id; resolved to a CV No via the sheet.")
    lang: str = Field(default="en", description="Letter language: 'en' or 'tr'.")
    force: bool = Field(
        default=False,
        description="If true, regenerate even if a letter already exists (overwrites it).",
    )


class CoverLetterResponse(BaseModel):
    """/cover-letter uç noktasının cevap gövdesi."""

    text: str = Field(description="The cover letter markdown.")
    cv_no: int = Field(description="CV No the letter belongs to.")
    lang: str = Field(description="Language the letter was written in.")
    created: bool = Field(
        description="True if the model was just called; False if read from disk."
    )


class AddJobRequest(BaseModel):
    """/add-job'un istek gövdesi — panelin "Ekle" butonu.

    "Yeni ilan -> sheet satırı" kaynağı olarak Huntr aktarımının yerini aldı. Panelin zaten
    elinde olan ilan metnini taşır ki KAYDEDİLEBİLSİN: misafir görünümlü scrape birincil kalır,
    ama o başarısız olursa (kalkmış ilan, LinkedIn duvarı) `--allow-staged` ile CV yine de
    kullanıcının gerçekten okuduğu metinden üretilebilir.
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
    """/add-job'un cevap gövdesi."""

    status: str = Field(description="'added' (row appended) or 'exists' (already tracked).")
    row: int = Field(description="Sheet row number of the new or existing row.")
    cv_no: str = Field(
        default="",
        # Bir METİN, int değil: N sütunu meşru olarak sayısal olmayan "Yok" işaretçisini tutar.
        description="Raw column N: '' (pending), a number, or the 'Yok' marker.",
    )
    staged: bool = Field(
        default=False, description="True if the posting text was stored as the fallback."
    )

"""Configuration for the parser.

One immutable settings object, passed as an argument to every stage. Normalization
reads OpenAI settings from ``NormalizeConfig`` (and ``OPENAI_*`` env via
``normalize.llm``); PDF stages do not read the environment.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FontThresholds(BaseModel):
    """Font-size boundaries for the 3-tier heading hierarchy.

    Calibrated on the EL Education teacher guide (MarkPro headings, MercuryTextG2
    body). A different publisher may need different thresholds — which is exactly
    why they live in config rather than in the code.
    """

    major_min_size: float = 12.5
    section_min_size: float = 10.4
    section_max_size: float = 11.6
    runin_min_size: float = 9.0
    runin_max_size: float = 9.9
    major_font_hint: str = "MarkPro"


class NormalizeConfig(BaseModel):
    """Stage-3 ELA curriculum-normalization settings (OpenAI only)."""

    model_config = ConfigDict(extra="forbid")

    # Empty → OPENAI_MODEL env → normalize.llm.DEFAULT_MODEL
    model: str = ""
    cache_dir: str = ".normalize_cache"
    max_tokens: int | None = None
    # If None, key is read from OPENAI_API_KEY (via .env / environment).
    openai_api_key: str | None = None


class Config(BaseModel):
    """Top-level parser configuration."""

    model_config = ConfigDict(extra="forbid")

    # Primary content engine. 'docling' recovers rich semantic structure and tables
    # (the main path); 'pymupdf' is the lightweight fallback that divides by font tier.
    # When engine='docling', Docling must be installed — there is no silent downgrade
    # for a missing package (runtime parse failures may still degrade per-lesson).
    engine: Literal["docling", "pymupdf"] = "docling"

    ocr_mode: Literal["auto", "on", "off"] = "auto"
    ocr_text_coverage_threshold: float = 0.80

    # Opt-in: when Docling lessons exist, independently re-divide those lessons with
    # PyMuPDF and FAIL on structural disagreement (verifier V15).
    cross_engine_structural_check: bool = False

    docling_tables: bool = True
    docling_cache_dir: str = ".docling_cache"

    fonts: FontThresholds = Field(default_factory=FontThresholds)

    cover_scan_pages: int = 3
    agenda_min_minutes: int = 45
    agenda_max_minutes: int = 75

    section_headers: tuple[str, ...] = (
        "CCS Standards",
        "Daily Learning Target",
        "Ongoing Assessment",
        "Agenda",
        "Materials",
        "Vocabulary",
        "Supporting English Language Learners",
        "Universal Design for Learning",
    )

    instructional_sections: tuple[str, ...] = (
        "Opening",
        "Work Time",
        "Closing and Assessment",
    )

    required_sections: tuple[str, ...] = (
        "CCS Standards",
        "Opening",
        "Work Time",
        "Closing and Assessment",
    )

    normalize: NormalizeConfig = Field(default_factory=NormalizeConfig)

    export_printed_pages: bool = True

"""Runtime configuration, read from environment variables with sensible defaults."""

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass
class Config:
    # Storage
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", BASE_DIR / "instance")))
    roster_path: Path = field(default_factory=lambda: Path(os.getenv("ROSTER_PATH", BASE_DIR / "data" / "roster.sample.csv")))

    # Organiser access
    admin_token: str = field(default_factory=lambda: os.getenv("ADMIN_TOKEN", "change-me"))

    # Eligibility rules
    eligible_levels: list[str] = field(default_factory=lambda: _list(
        os.getenv("ELIGIBLE_LEVELS", "PhD,Masters,Honours,PGDip,PGCert")
    ))
    eligible_faculty: str = field(default_factory=lambda: os.getenv("ELIGIBLE_FACULTY", "Science"))
    email_domains: list[str] = field(default_factory=lambda: _list(
        os.getenv("EMAIL_DOMAINS", "aucklanduni.ac.nz")
    ))
    student_id_pattern: str = field(default_factory=lambda: os.getenv("STUDENT_ID_PATTERN", r"^\d{7,10}$"))

    # Poster rules (A1 = 594 x 841 mm)
    a1_tolerance_mm: float = field(default_factory=lambda: float(os.getenv("A1_TOLERANCE_MM", "5")))
    min_image_dpi: int = field(default_factory=lambda: int(os.getenv("MIN_IMAGE_DPI", "150")))
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "50")))

    # Event
    event_name: str = field(default_factory=lambda: os.getenv("EVENT_NAME", "Postgraduate Science Research Showcase"))
    submissions_close: str = field(default_factory=lambda: os.getenv("SUBMISSIONS_CLOSE", ""))  # ISO date, optional

    @property
    def db_path(self) -> Path:
        return self.data_dir / "submissions.db"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "posters"

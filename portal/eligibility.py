"""Postgraduate eligibility checks against the faculty's enrolment roster.

The roster is a CSV export (student_id, email, name, programme, level, faculty).
In production this would be the enrolment export organisers already receive;
the sample file in data/ holds fictional students for local testing.
"""

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EligibilityResult:
    eligible: bool
    errors: list[str] = field(default_factory=list)
    student: dict | None = None

    def to_dict(self) -> dict:
        student = None
        if self.student:
            student = {k: self.student[k] for k in ("name", "programme", "level")}
        return {"eligible": self.eligible, "errors": self.errors, "student": student}


class Roster:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._by_id: dict[str, dict] = {}
        self.reload()

    def reload(self) -> None:
        self._by_id.clear()
        with self.path.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
                if row.get("student_id"):
                    self._by_id[row["student_id"]] = row

    def get(self, student_id: str) -> dict | None:
        return self._by_id.get(student_id)

    def __len__(self) -> int:
        return len(self._by_id)


def check_eligibility(student_id: str, email: str, roster: Roster, config) -> EligibilityResult:
    student_id = (student_id or "").strip()
    email = (email or "").strip().lower()
    errors: list[str] = []

    if not re.fullmatch(config.student_id_pattern, student_id):
        errors.append("Enter your student ID number (digits only, as shown on your student card).")

    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    if domain not in [d.lower() for d in config.email_domains]:
        allowed = " or ".join(f"@{d}" for d in config.email_domains)
        errors.append(f"Use your university student email ({allowed}).")

    if errors:
        return EligibilityResult(False, errors)

    student = roster.get(student_id)
    if student is None:
        return EligibilityResult(False, [
            "We couldn't find this student ID in the current postgraduate enrolment list. "
            "If you think this is wrong, contact the organisers before the deadline."
        ])

    if student.get("email", "").lower() != email:
        return EligibilityResult(False, ["This email doesn't match the one on record for this student ID."])

    level_ok = student.get("level", "").lower() in [lvl.lower() for lvl in config.eligible_levels]
    if not level_ok:
        return EligibilityResult(False, [
            f"The showcase is open to postgraduate students only "
            f"({', '.join(config.eligible_levels)}). Your enrolment is listed as "
            f"{student.get('level') or 'unknown'}."
        ])

    if config.eligible_faculty and student.get("faculty", "").lower() != config.eligible_faculty.lower():
        return EligibilityResult(False, [
            f"The showcase is open to students enrolled in the Faculty of {config.eligible_faculty}."
        ])

    return EligibilityResult(True, [], student)

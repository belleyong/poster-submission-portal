"""Postgraduate eligibility checks against the faculty's enrolment roster.

The roster is a CSV export (student_id, email, name, programme, level, faculty).
Organisers upload each year's export from the dashboard; it is checked by
check_roster_file() before replacing the live roster. The sample file in data/
holds fictional students for local testing.
"""

import csv
import io
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


ROSTER_COLUMNS = ["student_id", "email", "name", "programme", "level", "faculty"]
MAX_EXAMPLES = 5


def _normalise_row(row: dict) -> dict:
    return {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}


def decode_csv(data: bytes) -> str:
    """Decode a CSV saved by Excel either as 'CSV UTF-8' or plain 'CSV' (Windows-1252)."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


class Roster:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._by_id: dict[str, dict] = {}
        self.reload()

    def reload(self) -> None:
        by_id = {}
        with self.path.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                row = _normalise_row(row)
                if row.get("student_id"):
                    by_id[row["student_id"]] = row
        self._by_id = by_id

    def use(self, path: Path) -> None:
        self.path = Path(path)
        self.reload()

    def get(self, student_id: str) -> dict | None:
        return self._by_id.get(student_id)

    def __len__(self) -> int:
        return len(self._by_id)


@dataclass
class RosterCheck:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    text: str = ""
    total: int = 0
    eligible: int = 0
    by_level: dict[str, int] = field(default_factory=dict)


def _examples(items: list[str]) -> str:
    shown = ", ".join(items[:MAX_EXAMPLES])
    return shown + (f" and {len(items) - MAX_EXAMPLES} more" if len(items) > MAX_EXAMPLES else "")


def check_roster_file(data: bytes, config) -> RosterCheck:
    """Validate an uploaded enrolment CSV before it replaces the live roster."""
    text = decode_csv(data)
    reader = csv.DictReader(io.StringIO(text, newline=""))
    headers = [h.strip().lower() for h in (reader.fieldnames or []) if h]
    missing = [c for c in ROSTER_COLUMNS if c not in headers]
    if missing:
        return RosterCheck(False, [
            f"The file is missing these columns: {', '.join(missing)}. "
            f"The first row must be: {','.join(ROSTER_COLUMNS)}"
        ])

    rows = [_normalise_row(r) for r in reader]
    rows = [r for r in rows if any(r.values())]
    if not rows:
        return RosterCheck(False, ["The file has column headings but no students."])

    errors: list[str] = []
    warnings: list[str] = []
    eligible_levels = {lvl.lower() for lvl in config.eligible_levels}
    faculty = (config.eligible_faculty or "").lower()
    domains = {d.lower() for d in config.email_domains}

    seen: dict[str, int] = {}
    blank_ids, bad_ids, bad_emails = [], [], []
    by_level: dict[str, int] = {}
    other_faculty: dict[str, int] = {}
    eligible = 0

    for line, row in enumerate(rows, start=2):
        sid = row.get("student_id", "")
        if not sid:
            blank_ids.append(f"row {line}")
            continue
        seen[sid] = seen.get(sid, 0) + 1
        if not re.fullmatch(config.student_id_pattern, sid):
            bad_ids.append(sid)
        email = row.get("email", "").lower()
        if email.rsplit("@", 1)[-1] not in domains:
            bad_emails.append(sid)
        level = row.get("level", "") or "(blank)"
        by_level[level] = by_level.get(level, 0) + 1
        fac = row.get("faculty", "")
        if faculty and fac.lower() != faculty:
            other_faculty[fac or "(blank)"] = other_faculty.get(fac or "(blank)", 0) + 1
        can_enter = (re.fullmatch(config.student_id_pattern, sid)
                     and email.rsplit("@", 1)[-1] in domains
                     and level.lower() in eligible_levels
                     and (not faculty or fac.lower() == faculty))
        if can_enter:
            eligible += 1

    dupes = [sid for sid, n in seen.items() if n > 1]
    if dupes:
        errors.append(f"These student IDs appear more than once: {_examples(dupes)}. Remove the duplicates and upload again.")
    if blank_ids:
        errors.append(f"Some rows have no student ID ({_examples(blank_ids)}).")
    if not eligible and not errors:
        errors.append(
            f"No one in this file would be able to enter. The level column must say one of "
            f"{', '.join(config.eligible_levels)}, the faculty column must say {config.eligible_faculty}, "
            f"and emails must end in @{' or @'.join(config.email_domains)}. "
            f"This file has levels: {', '.join(sorted(by_level))}."
        )

    unknown_levels = {lvl: n for lvl, n in by_level.items() if lvl.lower() not in eligible_levels}
    if unknown_levels:
        listed = ", ".join(f"{lvl} ({n})" for lvl, n in sorted(unknown_levels.items()))
        warnings.append(
            f"Students with these levels will be told they're not eligible: {listed}. "
            f"If any of these are postgraduate, rename them to one of {', '.join(config.eligible_levels)}."
        )
    if other_faculty:
        listed = ", ".join(f"{f} ({n})" for f, n in sorted(other_faculty.items()))
        warnings.append(f"Students from other faculties won't be eligible: {listed}.")
    if bad_ids:
        warnings.append(f"These student IDs don't look like normal IDs, so those students can't enter: {_examples(bad_ids)}.")
    if bad_emails:
        warnings.append(f"These students don't have a university email in the file, so they can't enter: {_examples(bad_emails)}.")

    return RosterCheck(not errors, errors, warnings, text, len(rows), eligible, by_level)


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

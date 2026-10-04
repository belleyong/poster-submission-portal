# Automated Entry Validation Portal

A submission portal for the Faculty of Science **Postgraduate Science Research Showcase** poster competition. It replaces the Qualtrics form, which needed every entry checked by hand.

Problems with the old process:

- **Ineligible entries.** Undergraduates and students from other faculties could submit.
- **Wrong poster sizes.** Posters arrived at A0, A3 or A4, or as low-resolution images, and organisers only found out during manual review.

The portal checks both of these while the entrant fills in the form, so they get instant feedback and can fix problems before they submit. The server runs every check again on submission, so organisers only ever see entries that are valid.

## What it does

**For entrants** (`/`)

1. **Eligibility check.** The student ID and university email are matched against the faculty's postgraduate enrolment roster. Programme level (PhD, Masters, Honours, PGDip, PGCert) and faculty are both checked. Each student can submit only one entry.
2. **Research details.** Department, supervisor, title and an abstract with a live 250-word counter.
3. **A1 poster check at upload.**
   - **PDFs** are measured from the page box (594 × 841 mm, portrait or landscape, ±5 mm), must be a single page and must not be password-protected. If the size is wrong, the message names the size it detected, for example *"It looks like A4; re-export at A1"*.
   - **PNG and JPEG files** must have A1 proportions and enough pixels to print at 150 DPI (at least 3508 × 4967 px).
   - A small preview draws the uploaded page next to the A1 outline.
4. **Submit.** The button stays disabled until every check has passed. The entrant then gets a reference number, for example `PGS-2026-0001`.

**For organisers** (`/admin`, protected by an access code)

- Summary counts and a table of all entries, each with a link to its poster file
- Status tracking for each entry: received, accepted or withdrawn
- One-click CSV export for judging and catalogue preparation
- A button to reload the roster when a new enrolment export arrives

## Running it

The portal needs Python 3.11 or newer.

```bash
pip install -r requirements.txt
ADMIN_TOKEN=choose-a-code python run.py
# open http://localhost:5000
```

The sample roster in `data/roster.sample.csv` contains only fictional students. You can use them to try the portal:

| Student ID | Email | Result |
|---|---|---|
| 100000001 | a.tester@aucklanduni.ac.nz | Eligible (PhD) |
| 100000005 | e.under@aucklanduni.ac.nz | Rejected (undergraduate) |
| 100000006 | f.other@aucklanduni.ac.nz | Rejected (Engineering) |

## Configuration

All settings are environment variables.

| Variable | Default | Purpose |
|---|---|---|
| `ADMIN_TOKEN` | `change-me` | Access code for the organiser dashboard |
| `SECRET_KEY` | random | Flask session key (set it in production) |
| `ROSTER_PATH` | `data/roster.sample.csv` | Enrolment CSV with the columns `student_id,email,name,programme,level,faculty` |
| `DATA_DIR` | `instance/` | Location of the database and uploaded posters |
| `ELIGIBLE_LEVELS` | `PhD,Masters,Honours,PGDip,PGCert` | Programme levels that may enter |
| `ELIGIBLE_FACULTY` | `Science` | Faculty that may enter |
| `EMAIL_DOMAINS` | `aucklanduni.ac.nz` | Accepted email domains |
| `A1_TOLERANCE_MM` | `5` | Allowed difference from 594 × 841 mm |
| `MIN_IMAGE_DPI` | `150` | Minimum print resolution for image posters |
| `MAX_UPLOAD_MB` | `50` | Maximum upload size |
| `SUBMISSIONS_CLOSE` | (none) | Last date entries are accepted, in ISO format (for example `2026-11-30`) |

## Tests

```bash
python -m unittest -v
```

The suite has 33 tests. They cover:

- eligibility rules
- PDF sizes (A1 in both orientations, rounding tolerance, A0, A4, multi-page and corrupt files)
- image proportions and resolution
- server-side re-validation
- duplicate entries
- deadlines
- the organiser dashboard and CSV export

## Project structure

```
portal/
  app.py           Flask routes: entrant API, submission, organiser dashboard
  eligibility.py   Roster loading and postgraduate eligibility rules
  poster.py        A1 dimension checks for PDF, PNG and JPEG
  store.py         SQLite storage
  config.py        Environment-based settings
  templates/       Entrant form, organiser login and dashboard
  static/          Styles and the live-validation script
data/              Sample (fictional) roster
tests/             Unit and API tests
```

## Next steps

- Connect the roster to the university's identity provider (SSO), so students don't need to type their ID
- Send confirmation emails to entrants
- Add judging score sheets to the organiser dashboard

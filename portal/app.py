"""Flask app: entrant submission flow, live validation API and organiser dashboard."""

import csv
import hmac
import io
import os
import secrets
from datetime import date
from functools import wraps
from pathlib import Path

from flask import (Flask, Response, abort, jsonify, redirect, render_template, request,
                   send_file, session, url_for)

from .config import Config
from .eligibility import Roster, check_eligibility
from .poster import check_poster
from .store import STATUSES, Store

ABSTRACT_WORD_LIMIT = 250
TEXT_LIMITS = {"department": 120, "supervisor": 120, "title": 200}


def create_app(config: Config | None = None) -> Flask:
    config = config or Config()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = (config.max_upload_mb + 1) * 1024 * 1024
    app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)

    config.upload_dir.mkdir(parents=True, exist_ok=True)
    roster = Roster(config.roster_path)
    store = Store(config.db_path)
    app.extensions["portal"] = {"config": config, "roster": roster, "store": store}

    def submissions_open() -> bool:
        if not config.submissions_close:
            return True
        return date.today() <= date.fromisoformat(config.submissions_close)

    def admin_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if not session.get("admin"):
                return redirect(url_for("admin_login", next=request.path))
            return view(*args, **kwargs)
        return wrapper

    # ---------- Entrant pages ----------

    @app.get("/")
    def index():
        return render_template("index.html", config=config, is_open=submissions_open(),
                               word_limit=ABSTRACT_WORD_LIMIT)

    @app.post("/api/check/eligibility")
    def api_check_eligibility():
        body = request.get_json(silent=True) or request.form
        result = check_eligibility(body.get("student_id", ""), body.get("email", ""), roster, config)
        payload = result.to_dict()
        if result.eligible and store.find_by_student(result.student["student_id"]):
            payload.update(eligible=False, errors=[
                "You've already submitted an entry. Contact the organisers if you need to replace it."
            ])
        return jsonify(payload)

    @app.post("/api/check/poster")
    def api_check_poster():
        file = request.files.get("poster")
        if not file or not file.filename:
            return jsonify({"ok": False, "errors": ["Choose a poster file to upload."], "warnings": [], "details": {}})
        return jsonify(check_poster(file.filename, file.read(), config).to_dict())

    @app.post("/api/submissions")
    def api_submit():
        if not submissions_open():
            return jsonify({"ok": False, "errors": ["Submissions for this year's showcase have closed."]}), 403

        form = request.form
        errors: list[str] = []

        # Re-run every check server-side; the browser checks are for feedback only.
        elig = check_eligibility(form.get("student_id", ""), form.get("email", ""), roster, config)
        if not elig.eligible:
            return jsonify({"ok": False, "step": "eligibility", "errors": elig.errors}), 422
        student = elig.student
        if store.find_by_student(student["student_id"]):
            return jsonify({"ok": False, "step": "eligibility",
                            "errors": ["You've already submitted an entry."]}), 409

        fields = {k: (form.get(k) or "").strip() for k in ("department", "supervisor", "title", "abstract")}
        labels = {"department": "Department or school", "supervisor": "Supervisor",
                  "title": "Poster title", "abstract": "Abstract"}
        for key, label in labels.items():
            if not fields[key]:
                errors.append(f"{label} is required.")
            elif key in TEXT_LIMITS and len(fields[key]) > TEXT_LIMITS[key]:
                errors.append(f"{label} must be {TEXT_LIMITS[key]} characters or fewer.")
        words = len(fields["abstract"].split())
        if words > ABSTRACT_WORD_LIMIT:
            errors.append(f"Abstract is {words} words; the limit is {ABSTRACT_WORD_LIMIT}.")
        if form.get("declaration") not in ("on", "true", "1"):
            errors.append("Confirm the declaration before submitting.")
        if errors:
            return jsonify({"ok": False, "step": "details", "errors": errors}), 422

        file = request.files.get("poster")
        if not file or not file.filename:
            return jsonify({"ok": False, "step": "poster", "errors": ["Upload your poster."]}), 422
        data = file.read()
        poster = check_poster(file.filename, data, config)
        if not poster.ok:
            return jsonify({"ok": False, "step": "poster", "errors": poster.errors}), 422

        ext = Path(file.filename).suffix.lower()
        stored_name = f"{secrets.token_hex(16)}{ext}"
        (config.upload_dir / stored_name).write_bytes(data)

        record = store.add({
            "student_id": student["student_id"],
            "email": student["email"].lower(),
            "name": student["name"],
            "programme": student["programme"],
            "level": student["level"],
            **fields,
            "file_name": Path(file.filename).name[:200],
            "stored_file": stored_name,
            "file_type": poster.details.get("type", ext.lstrip(".")),
            "poster_width_mm": poster.details.get("width_mm"),
            "poster_height_mm": poster.details.get("height_mm"),
            "orientation": poster.details.get("orientation"),
        })
        return jsonify({"ok": True, "reference": record["reference"], "name": record["name"]})

    @app.errorhandler(413)
    def too_large(_):
        return jsonify({"ok": False, "errors": [f"This file is over {config.max_upload_mb} MB."]}), 413

    # ---------- Organiser dashboard ----------

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        error = None
        if request.method == "POST":
            if hmac.compare_digest(request.form.get("token", ""), config.admin_token):
                session["admin"] = True
                nxt = request.args.get("next", "")
                return redirect(nxt if nxt.startswith("/admin") else url_for("admin"))
            error = "That access code isn't right."
        return render_template("login.html", config=config, error=error)

    @app.post("/admin/logout")
    def admin_logout():
        session.clear()
        return redirect(url_for("admin_login"))

    @app.get("/admin")
    @admin_required
    def admin():
        subs = store.all()
        counts = {s: sum(1 for r in subs if r["status"] == s) for s in STATUSES}
        levels: dict[str, int] = {}
        for r in subs:
            levels[r["level"]] = levels.get(r["level"], 0) + 1
        return render_template("admin.html", config=config, submissions=subs, counts=counts,
                               levels=levels, statuses=STATUSES, roster_size=len(roster))

    @app.post("/admin/submissions/<sid>/status")
    @admin_required
    def admin_status(sid):
        if not store.set_status(sid, request.form.get("status", "")):
            abort(400)
        return redirect(url_for("admin"))

    @app.get("/admin/submissions/<sid>/poster")
    @admin_required
    def admin_poster(sid):
        sub = store.get(sid) or abort(404)
        path = config.upload_dir / sub["stored_file"]
        if not path.exists():
            abort(404)
        return send_file(path, download_name=f"{sub['reference']}{path.suffix}", as_attachment=False)

    @app.get("/admin/export.csv")
    @admin_required
    def admin_export():
        cols = ["reference", "created_at", "status", "name", "student_id", "email", "programme", "level",
                "department", "supervisor", "title", "abstract", "file_type", "orientation",
                "poster_width_mm", "poster_height_mm"]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(store.all())
        return Response(buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=showcase-submissions.csv"})

    @app.post("/admin/roster/reload")
    @admin_required
    def admin_reload_roster():
        roster.reload()
        return redirect(url_for("admin"))

    return app

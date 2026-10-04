import io
import tempfile
import unittest
from pathlib import Path

from portal.app import create_app
from portal.config import Config
from tests.helpers import make_image, make_pdf

ROSTER = Path(__file__).resolve().parent.parent / "data" / "roster.sample.csv"


def entry(**overrides):
    data = {
        "student_id": "100000001",
        "email": "a.tester@aucklanduni.ac.nz",
        "department": "School of Biological Sciences",
        "supervisor": "Dr Example",
        "title": "Kauri dieback resistance markers",
        "abstract": "A short abstract about the research.",
        "declaration": "on",
    }
    data.update(overrides)
    return data


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Config(data_dir=Path(self.tmp.name), roster_path=ROSTER, admin_token="secret")
        self.app = create_app(self.config)
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def submit(self, poster=None, name="poster.pdf", **overrides):
        data = entry(**overrides)
        data["poster"] = (io.BytesIO(poster if poster is not None else make_pdf(594, 841)), name)
        return self.client.post("/api/submissions", data=data, content_type="multipart/form-data")

    def test_home_page_renders(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Check eligibility", res.data)

    def test_eligibility_api(self):
        ok = self.client.post("/api/check/eligibility", json={"student_id": "100000002", "email": "b.sample@aucklanduni.ac.nz"})
        self.assertTrue(ok.get_json()["eligible"])
        self.assertNotIn("email", ok.get_json()["student"])
        bad = self.client.post("/api/check/eligibility", json={"student_id": "100000005", "email": "e.under@aucklanduni.ac.nz"})
        self.assertFalse(bad.get_json()["eligible"])

    def test_poster_api(self):
        res = self.client.post("/api/check/poster", data={"poster": (io.BytesIO(make_pdf(210, 297)), "p.pdf")},
                               content_type="multipart/form-data")
        body = res.get_json()
        self.assertFalse(body["ok"])
        self.assertIn("A4", body["errors"][0])

    def test_valid_submission_is_stored(self):
        res = self.submit()
        body = res.get_json()
        self.assertEqual(res.status_code, 200, body)
        self.assertTrue(body["reference"].startswith("PGS-"))
        self.assertEqual(len(list(self.config.upload_dir.iterdir())), 1)

    def test_image_submission_is_stored(self):
        res = self.submit(poster=make_image(3508, 4967), name="poster.png")
        self.assertEqual(res.status_code, 200, res.get_json())

    def test_duplicate_submission_rejected(self):
        self.submit()
        res = self.submit()
        self.assertEqual(res.status_code, 409)
        check = self.client.post("/api/check/eligibility", json={"student_id": "100000001", "email": "a.tester@aucklanduni.ac.nz"})
        self.assertFalse(check.get_json()["eligible"])

    def test_server_rejects_ineligible_even_if_browser_skipped(self):
        res = self.submit(student_id="100000005", email="e.under@aucklanduni.ac.nz")
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.get_json()["step"], "eligibility")

    def test_server_rejects_non_a1_poster(self):
        res = self.submit(poster=make_pdf(841, 1189))
        self.assertEqual(res.status_code, 422)
        self.assertEqual(res.get_json()["step"], "poster")
        self.assertFalse(any(self.config.upload_dir.iterdir()))

    def test_missing_fields_and_long_abstract(self):
        res = self.submit(title="", abstract="word " * 300, declaration="")
        errors = " ".join(res.get_json()["errors"])
        self.assertIn("Poster title is required", errors)
        self.assertIn("300 words", errors)
        self.assertIn("declaration", errors)

    def test_closed_submissions(self):
        self.config.submissions_close = "2000-01-01"
        self.assertEqual(self.submit().status_code, 403)

    def test_admin_requires_login(self):
        self.assertEqual(self.client.get("/admin").status_code, 302)
        self.assertEqual(self.client.get("/admin/export.csv").status_code, 302)
        bad = self.client.post("/admin/login", data={"token": "wrong"})
        self.assertIn(b"isn&#39;t right", bad.data)

    def test_admin_dashboard_export_and_status(self):
        sub_ref = self.submit().get_json()["reference"]
        self.client.post("/admin/login", data={"token": "secret"})
        page = self.client.get("/admin")
        self.assertIn(sub_ref.encode(), page.data)

        csv_text = self.client.get("/admin/export.csv").data.decode()
        self.assertIn(sub_ref, csv_text)
        self.assertIn("Kauri dieback", csv_text)

        store = self.app.extensions["portal"]["store"]
        sid = store.all()[0]["id"]
        self.client.post(f"/admin/submissions/{sid}/status", data={"status": "accepted"})
        self.assertEqual(store.get(sid)["status"], "accepted")
        self.assertEqual(self.client.get(f"/admin/submissions/{sid}/poster").status_code, 200)



HEADER = "student_id,email,name,programme,level,faculty\n"


class RosterUploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Config(data_dir=Path(self.tmp.name), roster_path=ROSTER, admin_token="secret")
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.client.post("/admin/login", data={"token": "secret"})

    def tearDown(self):
        self.tmp.cleanup()

    def upload(self, text, name="roster.csv", encoding="utf-8"):
        data = {"roster": (io.BytesIO(text.encode(encoding)), name)}
        self.client.post("/admin/roster/upload", data=data, content_type="multipart/form-data")
        return self.client.get("/admin").data.decode()

    def eligible(self, sid, email):
        res = self.client.post("/api/check/eligibility", json={"student_id": sid, "email": email})
        return res.get_json()["eligible"]

    def test_upload_replaces_roster(self):
        page = self.upload(HEADER + "2000001,new.student@aucklanduni.ac.nz,New Student,MSc,Masters,Science\n")
        self.assertIn("Roster updated", page)
        self.assertNotIn("previous roster was backed up", page)
        self.assertTrue(self.eligible("2000001", "new.student@aucklanduni.ac.nz"))
        self.assertFalse(self.eligible("100000001", "a.tester@aucklanduni.ac.nz"))  # last year's list is gone

    def test_uploaded_roster_survives_restart(self):
        self.upload(HEADER + "2000001,new.student@aucklanduni.ac.nz,New Student,MSc,Masters,Science\n")
        client = create_app(self.config).test_client()
        res = client.post("/api/check/eligibility", json={"student_id": "2000001", "email": "new.student@aucklanduni.ac.nz"})
        self.assertTrue(res.get_json()["eligible"])

    def test_second_upload_backs_up_first(self):
        self.upload(HEADER + "2000001,a@aucklanduni.ac.nz,A,MSc,Masters,Science\n")
        self.upload(HEADER + "2000002,b@aucklanduni.ac.nz,B,MSc,Masters,Science\n")
        backups = list((self.config.data_dir / "roster-backups").iterdir())
        self.assertEqual(len(backups), 1)
        self.assertIn("2000001", backups[0].read_text())

    def test_missing_columns_rejected_and_roster_unchanged(self):
        page = self.upload("id,email\n123,x@aucklanduni.ac.nz\n")
        self.assertIn("wasn't changed", page)
        self.assertIn("missing these columns", page)
        self.assertTrue(self.eligible("100000001", "a.tester@aucklanduni.ac.nz"))

    def test_duplicate_ids_rejected(self):
        page = self.upload(HEADER + "2000001,a@aucklanduni.ac.nz,A,MSc,Masters,Science\n"
                                    "2000001,b@aucklanduni.ac.nz,B,MSc,Masters,Science\n")
        self.assertIn("more than once", page)

    def test_unrecognised_levels_rejected_when_no_one_eligible(self):
        page = self.upload(HEADER + "2000001,a@aucklanduni.ac.nz,A,PhD Biology,Doctoral,Science\n")
        self.assertIn("No one in this file would be able to enter", page)
        self.assertIn("Doctoral", page)

    def test_warnings_for_partial_problems(self):
        page = self.upload(HEADER + "2000001,a@aucklanduni.ac.nz,A,MSc,Masters,Science\n"
                                    "2000002,b@aucklanduni.ac.nz,B,PhD,Doctoral,Science\n"
                                    "2000003,c@gmail.com,C,MSc,Masters,Science\n")
        self.assertIn("Roster updated", page)
        self.assertIn("3 students loaded, 1 of them able to enter", page)
        self.assertIn("Doctoral (1)", page)
        self.assertIn("2000003", page)

    def test_excel_plain_csv_encoding_accepted(self):
        page = self.upload(HEADER + "2000001,a@aucklanduni.ac.nz,Zoë Müller,MSc,Masters,Science\n", encoding="cp1252")
        self.assertIn("Roster updated", page)

    def test_non_csv_rejected(self):
        self.assertIn("Upload a .csv file", self.upload("x", name="roster.xlsx"))

    def test_template_and_current_downloads(self):
        self.assertIn(b"student_id,email", self.client.get("/admin/roster/template.csv").data)
        self.assertIn(b"100000001", self.client.get("/admin/roster/current.csv").data)

    def test_upload_requires_login(self):
        client = self.app.test_client()
        res = client.post("/admin/roster/upload", data={"roster": (io.BytesIO(b"x"), "r.csv")},
                          content_type="multipart/form-data")
        self.assertEqual(res.status_code, 302)
        self.assertTrue(self.eligible("100000001", "a.tester@aucklanduni.ac.nz"))


if __name__ == "__main__":
    unittest.main()

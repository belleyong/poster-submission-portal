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


if __name__ == "__main__":
    unittest.main()

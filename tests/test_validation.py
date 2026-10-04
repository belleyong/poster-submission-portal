import unittest
from pathlib import Path

from portal.config import Config
from portal.eligibility import Roster, check_eligibility
from portal.poster import check_poster
from tests.helpers import make_image, make_pdf

ROSTER = Path(__file__).resolve().parent.parent / "data" / "roster.sample.csv"


class PosterTests(unittest.TestCase):
    def setUp(self):
        self.config = Config()

    def check(self, name, data):
        return check_poster(name, data, self.config)

    def test_a1_portrait_pdf_passes(self):
        result = self.check("poster.pdf", make_pdf(594, 841))
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.details["orientation"], "portrait")

    def test_a1_landscape_pdf_passes(self):
        result = self.check("poster.pdf", make_pdf(841, 594))
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.details["orientation"], "landscape")

    def test_small_rounding_is_tolerated(self):
        self.assertTrue(self.check("p.pdf", make_pdf(596, 838)).ok)

    def test_a0_pdf_fails_with_hint(self):
        result = self.check("p.pdf", make_pdf(841, 1189))
        self.assertFalse(result.ok)
        self.assertIn("A0", result.errors[0])

    def test_a4_pdf_fails_with_hint(self):
        result = self.check("p.pdf", make_pdf(210, 297))
        self.assertFalse(result.ok)
        self.assertIn("A4", result.errors[0])

    def test_multi_page_pdf_fails(self):
        result = self.check("p.pdf", make_pdf(594, 841, pages=2))
        self.assertFalse(result.ok)
        self.assertIn("2 pages", result.errors[0])

    def test_corrupt_pdf_fails(self):
        self.assertFalse(self.check("p.pdf", b"%PDF-1.4 nonsense").ok)

    def test_a1_image_at_150_dpi_passes(self):
        self.assertTrue(self.check("p.png", make_image(3508, 4967)).ok)

    def test_low_res_image_fails(self):
        result = self.check("p.png", make_image(1000, 1414))
        self.assertFalse(result.ok)
        self.assertIn("low-resolution", result.errors[0])

    def test_wrong_ratio_image_fails(self):
        result = self.check("p.png", make_image(4000, 4000))
        self.assertFalse(result.ok)
        self.assertIn("proportions", result.errors[0])

    def test_jpeg_gets_warning(self):
        result = self.check("p.jpg", make_image(3508, 4967, "JPEG"))
        self.assertTrue(result.ok)
        self.assertTrue(result.warnings)

    def test_unsupported_extension_fails(self):
        self.assertFalse(self.check("poster.pptx", b"PK..").ok)

    def test_oversized_file_fails(self):
        self.config.max_upload_mb = 0
        self.assertFalse(self.check("p.pdf", make_pdf(594, 841)).ok)


class EligibilityTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(roster_path=ROSTER)
        self.roster = Roster(ROSTER)

    def check(self, sid, email):
        return check_eligibility(sid, email, self.roster, self.config)

    def test_phd_student_eligible(self):
        result = self.check("100000001", "a.tester@aucklanduni.ac.nz")
        self.assertTrue(result.eligible, result.errors)
        self.assertEqual(result.student["level"], "PhD")

    def test_email_is_case_insensitive(self):
        self.assertTrue(self.check("100000002", "B.Sample@AucklandUni.ac.nz").eligible)

    def test_undergraduate_rejected(self):
        result = self.check("100000005", "e.under@aucklanduni.ac.nz")
        self.assertFalse(result.eligible)
        self.assertIn("postgraduate", result.errors[0])

    def test_other_faculty_rejected(self):
        result = self.check("100000006", "f.other@aucklanduni.ac.nz")
        self.assertFalse(result.eligible)
        self.assertIn("Science", result.errors[0])

    def test_unknown_id_rejected(self):
        self.assertFalse(self.check("199999999", "x@aucklanduni.ac.nz").eligible)

    def test_mismatched_email_rejected(self):
        result = self.check("100000001", "b.sample@aucklanduni.ac.nz")
        self.assertFalse(result.eligible)
        self.assertIn("doesn't match", result.errors[0])

    def test_personal_email_rejected(self):
        result = self.check("100000001", "ava@gmail.com")
        self.assertFalse(result.eligible)
        self.assertIn("student email", result.errors[0])

    def test_bad_id_format_rejected(self):
        self.assertFalse(self.check("abc", "a.tester@aucklanduni.ac.nz").eligible)


if __name__ == "__main__":
    unittest.main()

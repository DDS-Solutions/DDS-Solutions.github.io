import importlib.util
import json
import shutil
import unittest
from pathlib import Path


VALIDATOR_PATH = Path(__file__).resolve().parents[1] / "validate_site.py"
SPEC = importlib.util.spec_from_file_location("validate_site", VALIDATOR_PATH)
validate_site = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_site)

VALID_FINGERPRINT = (
    "14:6D:E9:83:C5:73:06:50:D8:EE:B9:95:2F:34:FC:64:"
    "16:A0:83:42:E6:1D:BE:A8:8A:04:96:B2:3F:CF:44:E5"
)


class SiteValidatorTests(unittest.TestCase):
    def setUp(self):
        validate_site.errors.clear()
        validate_site.warnings.clear()
        self.root = Path(__file__).resolve().parent / ".test-work" / self._testMethodName
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write_assetlinks(self, fingerprint=VALID_FINGERPRINT):
        target_dir = self.root / ".well-known"
        target_dir.mkdir(parents=True)
        payload = [{
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": validate_site.EXPECTED_PACKAGE_NAME,
                "sha256_cert_fingerprints": [fingerprint],
            },
        }]
        (target_dir / "assetlinks.json").write_text(json.dumps(payload), encoding="utf-8")

    def write_robots(self):
        (self.root / "robots.txt").write_text(
            "User-agent: *\n"
            "Allow: /\n"
            "Disallow: /use-case-template.html\n"
            f"Sitemap: {validate_site.EXPECTED_SITE_ORIGIN}/sitemap.xml\n",
            encoding="utf-8",
        )

    def write_sitemap(self, urls):
        entries = "".join(f"<url><loc>{url}</loc></url>" for url in urls)
        (self.root / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{entries}</urlset>",
            encoding="utf-8",
        )

    def test_valid_assetlinks_passes(self):
        self.write_assetlinks()

        validate_site.validate_assetlinks(self.root)

        self.assertEqual([], validate_site.errors)
        self.assertEqual([], validate_site.warnings)

    def test_placeholder_fingerprint_is_blocking_by_default(self):
        self.write_assetlinks("XX:XX:XX...REPLACE_WITH_REAL_KEY...XX:XX")

        validate_site.validate_assetlinks(self.root)

        self.assertTrue(any("Placeholder SHA-256" in error for error in validate_site.errors))

    def test_placeholder_can_only_be_downgraded_explicitly(self):
        self.write_assetlinks("XX:XX:XX...REPLACE_WITH_REAL_KEY...XX:XX")

        validate_site.validate_assetlinks(self.root, allow_placeholder_fingerprint=True)

        self.assertEqual([], validate_site.errors)
        self.assertTrue(any("Placeholder SHA-256" in warning for warning in validate_site.warnings))

    def test_missing_robots_and_sitemap_are_errors(self):
        validate_site.validate_robots_and_sitemap(self.root)

        self.assertTrue(any("Missing robots.txt" in error for error in validate_site.errors))
        self.assertTrue(any("Missing sitemap.xml" in error for error in validate_site.errors))

    def test_nojekyll_is_required_to_publish_well_known_directory(self):
        validate_site.validate_github_pages_config(self.root)

        self.assertTrue(any("Missing .nojekyll" in error for error in validate_site.errors))

        validate_site.errors.clear()
        (self.root / ".nojekyll").touch()
        validate_site.validate_github_pages_config(self.root)

        self.assertEqual([], validate_site.errors)

    def test_sitemap_must_include_every_public_html_page(self):
        (self.root / "index.html").write_text("<!doctype html>", encoding="utf-8")
        (self.root / "privacy.html").write_text("<!doctype html>", encoding="utf-8")
        self.write_robots()
        self.write_sitemap([f"{validate_site.EXPECTED_SITE_ORIGIN}/"])

        validate_site.validate_robots_and_sitemap(self.root)

        self.assertTrue(any("privacy.html" in error for error in validate_site.errors))

    def test_html_requires_exactly_one_main_landmark(self):
        page = self.root / "index.html"
        page.write_text(
            '<!doctype html><html><head>'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; script-src \'self\'">'
            '</head><body><p>No main landmark</p></body></html>',
            encoding="utf-8",
        )

        validate_site.validate_html_file(page, self.root)

        self.assertTrue(any("exactly one <main>" in error for error in validate_site.errors))


if __name__ == "__main__":
    unittest.main()

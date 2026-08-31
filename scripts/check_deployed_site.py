#!/usr/bin/env python3
import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


EXPECTED_PACKAGE_NAME = "com.ddssolutions.remotecamera"
FINGERPRINT_PATTERN = re.compile(r"(?:[0-9A-F]{2}:){31}[0-9A-F]{2}")
MISLEADING_PRICE_PHRASES = (
    "free pet monitor app",
    "free baby monitor app",
    "get started for one very low price",
)


class LandmarkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.main_count = 0
        self.has_skip_link = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag.lower() == "main":
            self.main_count += 1
        if tag.lower() == "a" and attributes.get("href") == "#main-content":
            self.has_skip_link = True


def fetch(url, attempts=3):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            request = Request(url, headers={"User-Agent": "dds-solutions-production-smoke/1.0"})
            with urlopen(request, timeout=20) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                if response.geturl() != url:
                    raise RuntimeError(f"unexpected redirect to {response.geturl()}")
                return response.read(), response.headers.get_content_type()
        except (HTTPError, URLError, TimeoutError, RuntimeError) as error:
            last_error = error
            if attempt < attempts:
                time.sleep(5)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def require_content_type(url, actual, allowed):
    if actual not in allowed:
        raise RuntimeError(f"{url} returned content type '{actual}', expected one of {sorted(allowed)}")


def validate_assetlinks(origin):
    url = f"{origin}/.well-known/assetlinks.json"
    raw, content_type = fetch(url)
    require_content_type(url, content_type, {"application/json"})
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list) or not data:
        raise RuntimeError("assetlinks.json must contain a non-empty array")

    for statement in data:
        target = statement.get("target", {}) if isinstance(statement, dict) else {}
        if target.get("package_name") != EXPECTED_PACKAGE_NAME:
            continue
        fingerprints = target.get("sha256_cert_fingerprints", [])
        if not fingerprints:
            raise RuntimeError("assetlinks.json has no production signing fingerprint")
        for fingerprint in fingerprints:
            if "REPLACE_WITH_REAL_KEY" in fingerprint or not FINGERPRINT_PATTERN.fullmatch(fingerprint):
                raise RuntimeError("assetlinks.json contains a placeholder or malformed signing fingerprint")
        return
    raise RuntimeError(f"assetlinks.json has no statement for {EXPECTED_PACKAGE_NAME}")


def validate_sitemap_and_pages(origin):
    sitemap_url = f"{origin}/sitemap.xml"
    raw, content_type = fetch(sitemap_url)
    require_content_type(sitemap_url, content_type, {"application/xml", "text/xml"})
    root = ET.fromstring(raw)
    locations = [element.text.strip() for element in root.iter()
                 if element.tag.split("}")[-1] == "loc" and element.text]
    if not locations:
        raise RuntimeError("sitemap.xml contains no URLs")

    for url in locations:
        page_raw, page_type = fetch(url)
        require_content_type(url, page_type, {"text/html"})
        html = page_raw.decode("utf-8")
        parser = LandmarkParser()
        parser.feed(html)
        if parser.main_count != 1:
            raise RuntimeError(f"{url} contains {parser.main_count} main landmarks")
        if not parser.has_skip_link:
            raise RuntimeError(f"{url} is missing the skip-to-content link")
        lower_html = html.lower()
        for phrase in MISLEADING_PRICE_PHRASES:
            if phrase in lower_html:
                raise RuntimeError(f"{url} still contains misleading price phrase '{phrase}'")


def main():
    parser = argparse.ArgumentParser(description="Verify the deployed GitHub Pages site.")
    parser.add_argument("--origin", default="https://dds-solutions.github.io")
    args = parser.parse_args()
    origin = args.origin.rstrip("/")

    robots_url = f"{origin}/robots.txt"
    _, robots_type = fetch(robots_url)
    require_content_type(robots_url, robots_type, {"text/plain"})

    script_url = f"{origin}/js/app.js"
    _, script_type = fetch(script_url)
    require_content_type(script_url, script_type,
                         {"application/javascript", "text/javascript"})

    validate_assetlinks(origin)
    validate_sitemap_and_pages(origin)
    print("Production smoke checks passed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Production smoke checks failed: {error}", file=sys.stderr)
        sys.exit(1)

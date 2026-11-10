#!/usr/bin/env python3
import argparse
from collections import Counter
import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

# Global error / warning collectors
errors = []
warnings = []

EXPECTED_PACKAGE_NAME = "com.ddssolutions.remotecamera"
EXPECTED_SITE_ORIGIN = "https://dds-solutions.github.io"
FINGERPRINT_PATTERN = re.compile(r"(?:[0-9A-F]{2}:){31}[0-9A-F]{2}")
NON_INDEXED_PAGES = {'use-case-template.html', '404.html'}
MISLEADING_PRICE_PHRASES = (
    "free pet monitor app",
    "free baby monitor app",
    "get started for one very low price",
)

def log_error(file_path, line_num, message):
    error_str = f"[FAIL] {file_path}:{line_num} - {message}"
    errors.append(error_str)

def log_warning(file_path, line_num, message):
    warn_str = f"[WARN] {file_path}:{line_num} - {message}"
    warnings.append(warn_str)

def log_info(message):
    print(f"[INFO] {message}")

class SiteHTMLParser(HTMLParser):
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        self.has_csp = False
        self.csp_content = ""
        self.has_noindex = False
        self.has_title = False
        self.in_title = False
        self.title_text = ""
        self.has_description = False
        self.has_canonical = False
        self.main_count = 0
        self.ids = set()
        self.current_tag = None
        self.current_attrs = {}
        self.in_script = False
        self.script_type = None
        self.script_content = ""
        self.script_line = 0

        self.assets_to_check = []  # List of (attr, path, line)
        self.links_to_check = []   # List of (href, line)

    def handle_starttag(self, tag, attrs):
        # Gracefully handle valueless attributes where v is None
        attr_dict = {k.lower(): (v if v is not None else "") for k, v in attrs}
        line_num = self.getpos()[0]

        if 'id' in attr_dict and attr_dict['id'].strip():
            self.ids.add(attr_dict['id'].strip())

        if tag.lower() == 'title':
            self.has_title = True
            self.in_title = True

        # Check CSP meta tag and robots meta tag
        if tag.lower() == 'meta':
            http_equiv = (attr_dict.get('http-equiv') or '').lower()
            if http_equiv == 'content-security-policy':
                self.has_csp = True
                self.csp_content = attr_dict.get('content') or ''

            meta_name = (attr_dict.get('name') or '').lower()
            if meta_name == 'robots':
                content_val = (attr_dict.get('content') or '').lower()
                if 'noindex' in content_val:
                    self.has_noindex = True
            elif meta_name == 'description':
                if (attr_dict.get('content') or '').strip():
                    self.has_description = True

        if tag.lower() == 'main':
            self.main_count += 1

        # Single-pass check for inline event handlers and javascript: URIs
        for attr_name, attr_val in attrs:
            attr_name_lower = attr_name.lower()
            if attr_name_lower.startswith('on'):
                log_error(self.file_path, line_num, f"Forbidden inline event handler found: '{attr_name}=\"{attr_val}\"'")
            if attr_val and attr_val.strip().lower().startswith('javascript:'):
                log_error(self.file_path, line_num, f"Forbidden 'javascript:' URI found in attribute '{attr_name}'")

        # Collect local assets and check SRI on external assets
        if tag.lower() == 'img' and 'src' in attr_dict:
            self.assets_to_check.append(('src', attr_dict['src'], line_num))
        elif tag.lower() == 'script' and 'src' in attr_dict:
            src_val = attr_dict['src']
            self.assets_to_check.append(('src', src_val, line_num))
            # SRI check for external scripts
            if src_val.startswith('http://') or src_val.startswith('https://'):
                if 'integrity' not in attr_dict or 'crossorigin' not in attr_dict:
                    log_error(self.file_path, line_num, f"External script '{src_val}' missing 'integrity' or 'crossorigin' attribute")
        elif tag.lower() == 'link' and 'href' in attr_dict:
            href_val = attr_dict['href']
            rel_val = (attr_dict.get('rel') or '').lower()
            if rel_val == 'canonical' and href_val.strip():
                self.has_canonical = True
            if rel_val in ['stylesheet', 'icon', 'shortcut icon', 'apple-touch-icon', 'preload']:
                self.assets_to_check.append(('href', href_val, line_num))
            # SRI check for external stylesheets
            if rel_val == 'stylesheet' and (href_val.startswith('http://') or href_val.startswith('https://')):
                if 'integrity' not in attr_dict or 'crossorigin' not in attr_dict:
                    log_error(self.file_path, line_num, f"External stylesheet '{href_val}' missing 'integrity' or 'crossorigin' attribute")

        # Collect internal links (<a href>)
        if tag.lower() == 'a' and 'href' in attr_dict:
            self.links_to_check.append((attr_dict['href'], line_num))

        # Check for inline script blocks
        if tag.lower() == 'script':
            self.in_script = True
            self.script_type = (attr_dict.get('type') or '').lower()
            self.script_content = ""
            self.script_line = line_num
            # If script tag has src, it's external script file link, not inline block
            if 'src' in attr_dict:
                self.in_script = False

    def handle_data(self, data):
        if self.in_title:
            self.title_text += data
        if self.in_script:
            self.script_content += data

    def handle_endtag(self, tag):
        if tag.lower() == 'title':
            self.in_title = False
        if tag.lower() == 'script' and self.in_script:
            self.in_script = False
            content_stripped = self.script_content.strip()
            if content_stripped:
                if self.script_type == 'application/ld+json':
                    # Validate JSON-LD syntax
                    try:
                        json.loads(content_stripped)
                    except json.JSONDecodeError as e:
                        log_error(self.file_path, self.script_line, f"Invalid JSON-LD syntax: {e}")
                else:
                    # Executable inline script found
                    log_error(self.file_path, self.script_line, "Forbidden executable inline <script> block found")

def parse_csp(csp_str):
    directives = {}
    for part in csp_str.split(';'):
        tokens = part.strip().split()
        if tokens:
            directives[tokens[0].lower()] = tokens[1:]
    return directives

def validate_html_file(file_path, root_dir):
    rel_path = file_path.relative_to(root_dir)
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    parser = SiteHTMLParser(rel_path)
    parser.feed(content)

    # 1. CSP Check
    if not parser.has_csp:
        log_error(rel_path, 1, "Missing <meta http-equiv=\"Content-Security-Policy\"> tag")
    else:
        directives = parse_csp(parser.csp_content)
        script_src = directives.get('script-src', [])
        if "'unsafe-inline'" in script_src:
            log_error(rel_path, 1, "CSP 'script-src' contains unsafe-inline")
        for tokens in directives.values():
            for token in tokens:
                if "fonts.googleapis.com" in token or "fonts.gstatic.com" in token:
                    log_error(rel_path, 1, "CSP contains legacy Google Fonts domain rules")

    # 2. Insecure http:// Protocol Audit (ignoring standard XML schemas)
    http_matches = re.findall(r'http://(?!www\.w3\.org|schema\.org)[^\s"\'<>]+', content)
    if http_matches:
        for match in set(http_matches):
            log_error(rel_path, 1, f"Insecure 'http://' URL found: {match}")

    # Each page must expose exactly one primary-content landmark.
    if parser.main_count != 1:
        log_error(rel_path, 1, f"Expected exactly one <main> landmark, found {parser.main_count}")

    # 3. Asset Existence Check
    for attr, target, line_num in parser.assets_to_check:
        if target.startswith('http://') or target.startswith('https://') or target.startswith('data:'):
            continue
        clean_target = target.split('?')[0].split('#')[0]
        if clean_target.startswith('/'):
            asset_path = root_dir / clean_target.lstrip('/')
        else:
            asset_path = (file_path.parent / clean_target).resolve()

        if not asset_path.exists():
            log_error(rel_path, line_num, f"Referenced local asset does not exist: '{target}' (Resolved: {asset_path.name})")

    # 4. Local Link & Fragment Existence Check
    for href, line_num in parser.links_to_check:
        if href.startswith('#'):
            if len(href) > 1 and href[1:] not in parser.ids:
                log_error(rel_path, line_num, f"Broken internal fragment link '{href}' (no matching id='{href[1:]}')")
            continue
        if href.startswith('http://') or href.startswith('https://') or href.startswith('mailto:') or href.startswith('tel:'):
            continue
        clean_href = href.split('?')[0].split('#')[0]
        if not clean_href:
            continue
        if clean_href.startswith('/'):
            link_path = root_dir / clean_href.lstrip('/')
        else:
            link_path = (file_path.parent / clean_href).resolve()

        if not link_path.exists():
            log_error(rel_path, line_num, f"Referenced local link target does not exist: '{href}'")

    # 5. Non-indexed vs Indexed SEO metadata audit
    if file_path.name in NON_INDEXED_PAGES:
        if not parser.has_noindex:
            log_error(rel_path, 1, f"Non-indexed page '{file_path.name}' is missing '<meta name=\"robots\" content=\"noindex\">'")
    else:
        if not parser.has_title or not parser.title_text.strip():
            log_error(rel_path, 1, "Missing or empty <title> tag on indexed public page")
        if not parser.has_description:
            log_error(rel_path, 1, "Missing <meta name=\"description\"> tag on indexed public page")
        if not parser.has_canonical:
            log_error(rel_path, 1, "Missing <link rel=\"canonical\"> tag on indexed public page")

    # 6. Misleading pricing phrase audit
    content_lower = content.lower()
    for phrase in MISLEADING_PRICE_PHRASES:
        if phrase in content_lower:
            log_error(rel_path, 1, f"Misleading pricing phrase found: '{phrase}'")

def validate_assetlinks(root_dir, allow_placeholder_fingerprint=False):
    assetlinks_path = root_dir / '.well-known' / 'assetlinks.json'
    if not assetlinks_path.exists():
        log_error(".well-known/assetlinks.json", 1, "Missing .well-known/assetlinks.json file")
        return

    try:
        data = json.loads(assetlinks_path.read_text(encoding='utf-8'))
        if not isinstance(data, list) or not data:
            log_error(".well-known/assetlinks.json", 1, "Root value must be a non-empty JSON array")
            return

        expected_statement_found = False
        for index, entry in enumerate(data, start=1):
            if not isinstance(entry, dict):
                log_error(".well-known/assetlinks.json", 1, f"Statement {index} must be a JSON object")
                continue

            relation = entry.get('relation')
            if not isinstance(relation, list) or 'delegate_permission/common.handle_all_urls' not in relation:
                log_error(".well-known/assetlinks.json", 1,
                          f"Statement {index} is missing relation 'delegate_permission/common.handle_all_urls'")

            target = entry.get('target')
            if not isinstance(target, dict):
                log_error(".well-known/assetlinks.json", 1, f"Statement {index} is missing a valid target object")
                continue

            if target.get('namespace') != 'android_app':
                log_error(".well-known/assetlinks.json", 1,
                          f"Statement {index} target namespace must be 'android_app'")

            package_name = target.get('package_name')
            if package_name != EXPECTED_PACKAGE_NAME:
                log_error(".well-known/assetlinks.json", 1,
                          f"Statement {index} package_name must be '{EXPECTED_PACKAGE_NAME}', found '{package_name}'")
            else:
                expected_statement_found = True

            fingerprints = target.get('sha256_cert_fingerprints')
            if not isinstance(fingerprints, list) or not fingerprints:
                log_error(".well-known/assetlinks.json", 1,
                          f"Statement {index} must contain at least one SHA-256 certificate fingerprint")
                continue

            for fp in fingerprints:
                if not isinstance(fp, str):
                    log_error(".well-known/assetlinks.json", 1,
                              f"Statement {index} contains a non-string certificate fingerprint")
                    continue
                if 'REPLACE_WITH_REAL_KEY' in fp or fp.startswith('XX:'):
                    message = ("Placeholder SHA-256 fingerprint found. Replace it with the production "
                               "Play app-signing certificate fingerprint.")
                    if allow_placeholder_fingerprint:
                        log_warning(".well-known/assetlinks.json", 1, message)
                    else:
                        log_error(".well-known/assetlinks.json", 1, message)
                    continue
                if not FINGERPRINT_PATTERN.fullmatch(fp):
                    log_error(".well-known/assetlinks.json", 1,
                              f"Statement {index} contains a malformed SHA-256 certificate fingerprint")

        if not expected_statement_found:
            log_error(".well-known/assetlinks.json", 1,
                      f"No statement found for expected package '{EXPECTED_PACKAGE_NAME}'")
    except (OSError, json.JSONDecodeError) as e:
        log_error(".well-known/assetlinks.json", 1, f"Invalid assetlinks.json format: {e}")

def validate_github_pages_config(root_dir):
    if not (root_dir / '.nojekyll').exists():
        log_error('.nojekyll', 1,
                  "Missing .nojekyll file; GitHub Pages will exclude the .well-known directory")

def validate_robots_and_sitemap(root_dir):
    robots_path = root_dir / 'robots.txt'
    if not robots_path.exists():
        log_error("robots.txt", 1, "Missing robots.txt file")
    else:
        robots_text = robots_path.read_text(encoding='utf-8')
        if 'Disallow: /use-case-template.html' not in robots_text:
            log_error("robots.txt", 1, "Missing 'Disallow: /use-case-template.html' rule")
        expected_sitemap_line = f"Sitemap: {EXPECTED_SITE_ORIGIN}/sitemap.xml"
        if expected_sitemap_line not in robots_text:
            log_error("robots.txt", 1, f"Missing canonical sitemap declaration '{expected_sitemap_line}'")

    sitemap_path = root_dir / 'sitemap.xml'
    if not sitemap_path.exists():
        log_error("sitemap.xml", 1, "Missing sitemap.xml file")
        return

    try:
        sitemap_root = ET.parse(sitemap_path).getroot()
    except (OSError, ET.ParseError) as e:
        log_error("sitemap.xml", 1, f"Invalid sitemap XML: {e}")
        return

    if sitemap_root.tag.split('}')[-1] != 'urlset':
        log_error("sitemap.xml", 1, "Root element must be <urlset>")
        return

    locations = []
    for url_elem in sitemap_root:
        if url_elem.tag.split('}')[-1] != 'url':
            continue
        loc_text = None
        lastmod_text = None
        for child in url_elem:
            tag_name = child.tag.split('}')[-1]
            if tag_name == 'loc' and child.text:
                loc_text = child.text.strip()
                locations.append(loc_text)
            elif tag_name == 'lastmod' and child.text:
                lastmod_text = child.text.strip()
        if loc_text and not lastmod_text:
            log_error("sitemap.xml", 1, f"Missing <lastmod> for sitemap URL: '{loc_text}'")

    duplicate_locations = [url for url, count in Counter(locations).items() if count > 1]
    for url in duplicate_locations:
        log_error("sitemap.xml", 1, f"Duplicate sitemap URL: '{url}'")

    html_files = [path for path in root_dir.glob('*.html')
                  if not path.name.startswith('google') and path.name not in NON_INDEXED_PAGES]
    expected_locations = {
        f"{EXPECTED_SITE_ORIGIN}/" if path.name == 'index.html'
        else f"{EXPECTED_SITE_ORIGIN}/{path.name}"
        for path in html_files
    }
    actual_locations = set(locations)

    for url in sorted(expected_locations - actual_locations):
        log_error("sitemap.xml", 1, f"Missing public page from sitemap: '{url}'")
    for url in sorted(actual_locations - expected_locations):
        log_error("sitemap.xml", 1, f"Unexpected sitemap URL: '{url}'")

    if f"{EXPECTED_SITE_ORIGIN}/index.html" in actual_locations:
        log_error("sitemap.xml", 1, "Use the canonical site root '/' instead of '/index.html'")
    for page_name in NON_INDEXED_PAGES:
        if f"{EXPECTED_SITE_ORIGIN}/{page_name}" in actual_locations:
            log_error("sitemap.xml", 1, f"Non-indexed page '{page_name}' must not appear in sitemap.xml")

def validate_page_reachability(root_dir):
    public_pages = {
        path.name for path in root_dir.glob('*.html')
        if not path.name.startswith('google') and path.name not in NON_INDEXED_PAGES
    }
    linked_targets = set()
    for page_name in public_pages:
        page_path = root_dir / page_name
        try:
            content = page_path.read_text(encoding='utf-8')
            parser = SiteHTMLParser(page_name)
            parser.feed(content)
            for href, _ in parser.links_to_check:
                clean_href = href.split('?')[0].split('#')[0].strip().lstrip('/')
                if clean_href in public_pages:
                    linked_targets.add(clean_href)
        except OSError as e:
            log_error(page_name, 1, f"Failed to read page for reachability check: {e}")

    orphaned = public_pages - linked_targets - {'index.html'}
    for orphan in sorted(orphaned):
        log_error(orphan, 1, f"Orphaned public page detected: '{orphan}' is not linked from any public page")

def main():
    parser = argparse.ArgumentParser(description="Site integrity, security, and CSP auditor.")
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent,
                        help="Root directory of the static site")
    parser.add_argument('--allow-placeholder-fingerprint', action='store_true',
                        help="Temporarily downgrade the known signing fingerprint placeholder to a warning")
    args = parser.parse_args()

    root_dir = args.root.resolve()
    errors.clear()
    warnings.clear()
    log_info(f"Starting site validation in root directory: {root_dir}")

    html_files = [f for f in sorted(list(root_dir.glob('*.html'))) if not f.name.startswith('google')]
    log_info(f"Found {len(html_files)} HTML pages to validate.")

    for html_file in html_files:
        validate_html_file(html_file, root_dir)

    validate_github_pages_config(root_dir)
    validate_assetlinks(root_dir, allow_placeholder_fingerprint=args.allow_placeholder_fingerprint)
    validate_robots_and_sitemap(root_dir)
    validate_page_reachability(root_dir)

    print("\n--- Audit Summary ---")
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for warn in warnings:
            print(f"  - {warn}")

    if errors:
        print(f"\nFAILED: Found {len(errors)} error(s) during validation:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    elif warnings:
        print(f"\nSUCCESS WITH WARNINGS: Validation passed across {len(html_files)} pages with {len(warnings)} warning(s).")
        sys.exit(0)
    else:
        print(f"\nSUCCESS: All validation and security checks passed cleanly across {len(html_files)} pages!")
        sys.exit(0)

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

# Global error / warning collectors
errors = []
warnings = []

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

        # Check inline event handlers (e.g., onclick, onload)
        for attr_name, attr_val in attrs:
            if attr_name.lower().startswith('on'):
                log_error(self.file_path, line_num, f"Forbidden inline event handler found: '{attr_name}=\"{attr_val}\"'")

        # Check javascript: URIs
        for attr_name, attr_val in attrs:
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
        if self.in_script:
            self.script_content += data

    def handle_endtag(self, tag):
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
        csp = parser.csp_content
        if "'unsafe-inline'" in (csp.split('script-src')[1].split(';')[0] if 'script-src' in csp else ""):
            log_error(rel_path, 1, "CSP 'script-src' contains unsafe-inline")
        if "fonts.googleapis.com" in csp or "fonts.gstatic.com" in csp:
            log_error(rel_path, 1, "CSP contains legacy Google Fonts domain rules")

    # 2. Insecure http:// Protocol Audit (ignoring standard XML schemas)
    http_matches = re.findall(r'http://(?!www\.w3\.org|schema\.org)[^\s"\'<>]+', content)
    if http_matches:
        for match in set(http_matches):
            log_error(rel_path, 1, f"Insecure 'http://' URL found: {match}")

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

    # 4. Local Link Existence Check
    for href, line_num in parser.links_to_check:
        if href.startswith('http://') or href.startswith('https://') or href.startswith('mailto:') or href.startswith('tel:') or href.startswith('#'):
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

    # 5. Template file indexing audit
    if file_path.name == 'use-case-template.html':
        if not parser.has_noindex:
            log_error(rel_path, 1, "Template 'use-case-template.html' is missing '<meta name=\"robots\" content=\"noindex\">'")

def validate_assetlinks(root_dir):
    assetlinks_path = root_dir / '.well-known' / 'assetlinks.json'
    if not assetlinks_path.exists():
        log_error(".well-known/assetlinks.json", 1, "Missing .well-known/assetlinks.json file")
        return

    try:
        data = json.loads(assetlinks_path.read_text(encoding='utf-8'))
        for entry in data:
            target = entry.get('target', {})
            fingerprints = target.get('sha256_cert_fingerprints', [])
            for fp in fingerprints:
                if 'REPLACE_WITH_REAL_KEY' in fp or fp.startswith('XX:'):
                    log_warning(".well-known/assetlinks.json", 1, f"Placeholder SHA-256 fingerprint found: '{fp}'. Update with production key from Play Console.")
    except Exception as e:
        log_error(".well-known/assetlinks.json", 1, f"Invalid assetlinks.json format: {e}")

def validate_robots_and_sitemap(root_dir):
    robots_path = root_dir / 'robots.txt'
    if robots_path.exists():
        robots_text = robots_path.read_text(encoding='utf-8')
        if 'Disallow: /use-case-template.html' not in robots_text:
            log_error("robots.txt", 1, "Missing 'Disallow: /use-case-template.html' rule")

    sitemap_path = root_dir / 'sitemap.xml'
    if sitemap_path.exists():
        sitemap_text = sitemap_path.read_text(encoding='utf-8')
        if 'https://dds-solutions.github.io/index.html' in sitemap_text:
            log_error("sitemap.xml", 1, "Duplicate entry 'https://dds-solutions.github.io/index.html' in sitemap.xml. Use canonical root '/' only.")

def main():
    parser = argparse.ArgumentParser(description="Site integrity, security, and CSP auditor.")
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent,
                        help="Root directory of the static site")
    args = parser.parse_args()

    root_dir = args.root.resolve()
    log_info(f"Starting site validation in root directory: {root_dir}")

    html_files = [f for f in sorted(list(root_dir.glob('*.html'))) if not f.name.startswith('google')]
    log_info(f"Found {len(html_files)} HTML pages to validate.")

    for html_file in html_files:
        validate_html_file(html_file, root_dir)

    validate_assetlinks(root_dir)
    validate_robots_and_sitemap(root_dir)

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
    else:
        print(f"\nSUCCESS: 100% of validation and security checks passed cleanly across {len(html_files)} pages!")
        sys.exit(0)

if __name__ == '__main__':
    main()

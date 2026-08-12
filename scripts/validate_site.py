#!/usr/bin/env python3
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

# Global error counter
errors = []

def log_error(file_path, line_num, message):
    error_str = f"[FAIL] {file_path}:{line_num} - {message}"
    errors.append(error_str)
    print(error_str)

def log_info(message):
    print(f"[INFO] {message}")

class SiteHTMLParser(HTMLParser):
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
        self.has_csp = False
        self.csp_content = ""
        self.current_tag = None
        self.current_attrs = {}
        self.in_script = False
        self.script_type = None
        self.script_content = ""
        self.script_line = 0

        self.assets_to_check = []  # List of (attr, path, line)
        self.links_to_check = []   # List of (href, line)

    def handle_starttag(self, tag, attrs):
        attr_dict = {k.lower(): v for k, v in attrs}
        line_num = self.getpos()[0]

        # Check CSP meta tag
        if tag.lower() == 'meta':
            if attr_dict.get('http-equiv', '').lower() == 'content-security-policy':
                self.has_csp = True
                self.csp_content = attr_dict.get('content', '')

        # Check inline event handlers (e.g., onclick, onload)
        for attr_name, attr_val in attrs:
            if attr_name.lower().startswith('on'):
                log_error(self.file_path, line_num, f"Forbidden inline event handler found: '{attr_name}=\"{attr_val}\"'")

        # Check javascript: URIs
        for attr_name, attr_val in attrs:
            if attr_val and attr_val.strip().lower().startswith('javascript:'):
                log_error(self.file_path, line_num, f"Forbidden 'javascript:' URI found in attribute '{attr_name}'")

        # Collect local assets (<img src>, <script src>, <link href>)
        if tag.lower() == 'img' and 'src' in attr_dict:
            self.assets_to_check.append(('src', attr_dict['src'], line_num))
        elif tag.lower() == 'script' and 'src' in attr_dict:
            self.assets_to_check.append(('src', attr_dict['src'], line_num))
            # SRI check for external scripts
            src_val = attr_dict['src']
            if src_val.startswith('http://') or src_val.startswith('https://'):
                if 'integrity' not in attr_dict or 'crossorigin' not in attr_dict:
                    log_error(self.file_path, line_num, f"External script '{src_val}' missing 'integrity' or 'crossorigin' attribute")
        elif tag.lower() == 'link' and 'href' in attr_dict:
            rel_val = attr_dict.get('rel', '').lower()
            if rel_val in ['stylesheet', 'icon', 'shortcut icon', 'apple-touch-icon']:
                self.assets_to_check.append(('href', attr_dict['href'], line_num))

        # Collect internal links (<a href>)
        if tag.lower() == 'a' and 'href' in attr_dict:
            self.links_to_check.append((attr_dict['href'], line_num))

        # Check for inline script blocks
        if tag.lower() == 'script':
            self.in_script = True
            self.script_type = attr_dict.get('type', '').lower()
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
                    log_error(self.file_path, self.script_line, f"Forbidden executable inline <script> block found")

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
        # Clean query string or anchor
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

def main():
    root_dir = Path(__file__).resolve().parent.parent
    log_info(f"Starting site validation in root directory: {root_dir}")

    html_files = [f for f in sorted(list(root_dir.glob('*.html'))) if not f.name.startswith('google')]
    log_info(f"Found {len(html_files)} HTML pages to validate.")

    for html_file in html_files:
        validate_html_file(html_file, root_dir)

    print("\n--- Audit Summary ---")
    if errors:
        print(f"FAILED: Found {len(errors)} error(s) during validation:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("SUCCESS: 100% of validation and security checks passed cleanly!")
        sys.exit(0)

if __name__ == '__main__':
    main()

# DDS-Solutions.github.io

Official website, privacy policy, terms of service, and Android Digital Asset Links verification for **Pro Wifi Camera Remote**.

## 🌐 Overview

**Pro Wifi Camera Remote** transforms Android devices into a private, local Wi-Fi camera and monitor system without requiring cloud subscriptions or external internet access.

This repository hosts the static site deployed to GitHub Pages at [https://dds-solutions.github.io/](https://dds-solutions.github.io/).

---

## 📁 Repository Structure

```
├── .github/
│   └── workflows/
│       └── ci.yml               # Automated CI auditor & integrity tests
├── .well-known/
│   └── assetlinks.json          # Android App Links domain verification
├── css/
│   └── style.css                # Site-wide responsive stylesheet
├── fonts/                       # Self-hosted subsetted Inter font files (.woff2)
├── images/
│   └── screenshots/             # App preview captures and feature diagrams
├── js/
│   └── app.js                   # Accessible modals, carousel & scroll animations
├── scripts/
│   └── validate_site.py         # Custom site integrity, CSP & link validator
├── sitemap.xml                  # Search engine sitemap
├── robots.txt                   # Crawler directives
├── index.html                   # Homepage & app landing page
├── whats-new.html               # Version changelog & feature highlights
├── accessories.html             # Curated hardware & mounting recommendations
├── privacy.html                 # Privacy policy
├── terms.html                   # Terms of service
└── [use-case].html              # Targeted use-case landing pages (Baby, Pet, 3D Printer, etc.)
```

---

## 🛡️ Security & Architecture Standards

1. **Strict Content Security Policy (CSP)**:
   - Zero inline JavaScript execution.
   - All CDN dependencies strictly pinned with Subresource Integrity (SRI) hashes.
   - Self-hosted fonts and assets.
2. **Accessible Modals & Navigation**:
   - WAI-ARIA dialog attributes (`role="dialog"`, `aria-modal="true"`, `aria-labelledby`).
   - Focus trapping, Escape key listener, and focus restoration to trigger buttons.
   - Scoped keyboard arrow controls for the screenshot carousel.
3. **SEO & Performance Optimization**:
   - Schema.org `SoftwareApplication` JSON-LD structured data.
   - Font preloads for fast First Contentful Paint (FCP) and Largest Contentful Paint (LCP).
   - Lazy loading on below-the-fold images (`loading="lazy"`).
   - Progressive enhancement fallback for users with JavaScript disabled.

---

## 🔍 Local Validation

To run the site auditor and integrity check locally:

```bash
python scripts/validate_site.py
```

The validator checks:
- Content Security Policy (CSP) tag presence and policy validity.
- Subresource Integrity (SRI) for external scripts and stylesheets.
- Existence of all local asset paths (`<img>`, `<script>`, `<link>`) and internal links (`<a>`).
- JSON-LD syntax validation in `<script type="application/ld+json">`.
- Digital Asset Links (`.well-known/assetlinks.json`) format.
- Disallow / noindex rules for draft or template pages.

---

## 📱 Android App Links Configuration

Android App Links allow URLs under `https://dds-solutions.github.io/` to open directly in the Pro Wifi Camera Remote app.

To update the verification fingerprint:
1. Obtain your SHA-256 App Signing Certificate Fingerprint from the **Google Play Console** (`Release > Setup > App Integrity > App Signing`).
2. Update `.well-known/assetlinks.json` with the SHA-256 fingerprint array.
3. Commit and push to `main`.

---

## 📄 License

Copyright &copy; 2026 DDS Solutions. All rights reserved. See [LICENSE](LICENSE) for details.
#!/usr/bin/env python3
"""
Render etl-id-cards.html into the printable artefacts in this repo:

    id-cards/<slug>.png              one high-res PNG per staff card (3x)
    preview/etl-id-cards-preview.png all five cards on one sheet
    ETL-Staff-ID-Cards.pdf           print-ready PDF

Run this whenever the card design, the staff details or the photos change:

    pip install playwright && playwright install chromium
    python3 tools/render_cards.py

It verifies that every card actually picked up a photo before writing anything,
so a broken image path fails the run instead of silently shipping cards with
empty "PHOTO" placeholders.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
PAGE = REPO / "etl-id-cards.html"
CARD_DIR = REPO / "id-cards"
PREVIEW = REPO / "preview" / "etl-id-cards-preview.png"
PDF = REPO / "ETL-Staff-ID-Cards.pdf"

SCALE = 3          # 340px card -> 1020px PNG, same as the previous renders
EXPECTED_CARDS = 5


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1400},
                                device_scale_factor=SCALE)
        page.goto(PAGE.as_uri(), wait_until="load")

        # cards are built by script, so wait for them
        page.wait_for_selector(".card", state="attached")
        page.wait_for_function(
            f"document.querySelectorAll('.card').length === {EXPECTED_CARDS}")

        # every photo and the logo must be decoded before we screenshot
        page.wait_for_function("""() => {
            const imgs = [...document.querySelectorAll('img')];
            return imgs.length > 0 && imgs.every(i => i.complete);
        }""", timeout=30000)
        page.wait_for_timeout(400)

        loaded = page.eval_on_selector_all(
            ".pimg", "els => els.map(e => [e.dataset.slug, e.dataset.loaded || null])")

        missing = [slug for slug, srcpath in loaded if not srcpath]
        if missing:
            print(f"ERROR: no photo loaded for {', '.join(missing)}", file=sys.stderr)
            browser.close()
            return 1

        print(f"{len(loaded)} cards, photos resolved to:")
        for slug, srcpath in loaded:
            print(f"  {slug:8s} {srcpath}")

        # ---- per-card PNGs ------------------------------------------------
        CARD_DIR.mkdir(parents=True, exist_ok=True)
        cards = page.query_selector_all(".card")
        for card in cards:
            slug = card.get_attribute("data-slug")
            dst = CARD_DIR / f"{slug}.png"
            card.screenshot(path=str(dst))
            print(f"  wrote {dst.relative_to(REPO)}")

        # ---- preview sheet ------------------------------------------------
        PREVIEW.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(PREVIEW), full_page=True)
        print(f"  wrote {PREVIEW.relative_to(REPO)}")

        # ---- print-ready PDF ---------------------------------------------
        page.emulate_media(media="print")
        page.pdf(path=str(PDF), format="A4", print_background=True,
                 margin={"top": "8mm", "bottom": "8mm", "left": "8mm", "right": "8mm"})
        print(f"  wrote {PDF.relative_to(REPO)}")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

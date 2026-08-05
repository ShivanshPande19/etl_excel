#!/usr/bin/env python3
"""
Build a professional Offer Letter for Shivansh Pande, overlaid onto the
Crownest Hospitality LLP letterhead PDF (exact original design preserved).

Approach:
  1. Flow the letter text with ReportLab Platypus into a frame that sits in the
     safe white area of the letterhead (below the header, above the footer).
  2. Merge the generated text page on top of a copy of the letterhead page
     using pypdf, so the header / footer / watermark stay pixel-perfect.

Run:  python3 build_offer_letter.py
Out:  Offer_Letter_Shivansh_Pande.pdf
"""

import io
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer,
    ListFlowable, ListItem,
)
from pypdf import PdfReader, PdfWriter

# ---------------------------------------------------------------------------
# Paths & page geometry
# ---------------------------------------------------------------------------
LETTERHEAD = "_assets/Crownest_Letterhead_A4.pdf"
OUTPUT = "Offer_Letter_Shivansh_Pande.pdf"

# Page size taken from the actual letterhead media box (A4-ish)
PAGE_W, PAGE_H = 595.44, 841.68

# Safe content frame (points). Header ends ~155pt from the top; the footer art
# starts ~150pt from the bottom. Left/right margins give a clean text column.
FRAME_X = 64
FRAME_W = PAGE_W - 2 * FRAME_X            # ~467
FRAME_TOP = PAGE_H - 162                  # start below the gold header rule
FRAME_BOTTOM = 150                        # stay above footer decorations
FRAME_H = FRAME_TOP - FRAME_BOTTOM

# Brand colours (sampled from the logo)
GOLD = HexColor(0xB0894F)
CHARCOAL = HexColor(0x2B2B2B)

# ---------------------------------------------------------------------------
# Paragraph styles
# ---------------------------------------------------------------------------
BODY = ParagraphStyle(
    "body", fontName="Helvetica", fontSize=10, leading=13.5,
    textColor=CHARCOAL, alignment=TA_JUSTIFY, spaceAfter=5,
)
META = ParagraphStyle(
    "meta", parent=BODY, alignment=TA_LEFT, spaceAfter=2, leading=13.5,
)
SUBJECT = ParagraphStyle(
    "subject", fontName="Helvetica-Bold", fontSize=11.5, leading=15,
    textColor=GOLD, spaceBefore=4, spaceAfter=8, alignment=TA_LEFT,
)
BOLD_LINE = ParagraphStyle(
    "boldline", parent=BODY, fontName="Helvetica-Bold", alignment=TA_LEFT,
    spaceAfter=3,
)
BULLET = ParagraphStyle(
    "bullet", parent=BODY, alignment=TA_LEFT, spaceAfter=3, leading=14,
)
SIGN = ParagraphStyle(
    "sign", parent=BODY, alignment=TA_LEFT, spaceAfter=1, leading=14,
)

BLANK = '<font color="#888888">______________________</font>'
SHORTBLANK = '<font color="#888888">________________</font>'


# ---------------------------------------------------------------------------
# Story (letter content). Blanks are fillable placeholders.
# ---------------------------------------------------------------------------
def build_story():
    s = []
    s.append(Paragraph(f"<b>Date:</b> {SHORTBLANK}", META))
    s.append(Paragraph(f"<b>Ref. No.:</b> {SHORTBLANK}", META))
    s.append(Spacer(1, 8))

    s.append(Paragraph("<b>To,</b>", META))
    s.append(Paragraph("<b>Shivansh Pande</b>", META))
    s.append(Paragraph(BLANK, META))
    s.append(Paragraph(f"{BLANK} <font color='#888888'>(Address / City)</font>", META))
    s.append(Spacer(1, 8))

    s.append(Paragraph("Subject: Offer of Employment", SUBJECT))

    s.append(Paragraph("Dear Shivansh,", BODY))
    s.append(Paragraph(
        "We are pleased to offer you the position of "
        f"<b>{SHORTBLANK} (Designation)</b> at <b>Crownest Hospitality LLP</b> "
        "(a subsidiary of Azimuth Business on Wheels Private Limited).", BODY))

    s.append(Paragraph("Please find the initial terms of your offer below:", BODY))

    s.append(ListFlowable(
        [
            ListItem(Paragraph(f"<b>Designation:</b> {SHORTBLANK}", BULLET), leftIndent=6),
            ListItem(Paragraph(f"<b>Duration:</b> {SHORTBLANK}", BULLET), leftIndent=6),
            ListItem(Paragraph(
                f"<b>Compensation:</b> Your salary will be {SHORTBLANK}, "
                "subject to standard statutory deductions.", BULLET), leftIndent=6),
        ],
        bulletType="bullet", bulletColor=GOLD, bulletFontSize=8,
        leftIndent=14, spaceBefore=2, spaceAfter=6,
    ))

    s.append(Paragraph("<b>Key Terms:</b>", BOLD_LINE))
    s.append(ListFlowable(
        [
            ListItem(Paragraph(
                "You will be expected to carry out your duties diligently, "
                'maintaining our commitment to "Hospitality with Integrity".',
                BULLET), leftIndent=6),
            ListItem(Paragraph(
                "During your tenure, you will be bound by the standard rules, "
                "regulations, and confidentiality policies of Crownest "
                "Hospitality LLP and its parent company.", BULLET), leftIndent=6),
        ],
        bulletType="1", bulletColor=GOLD, leftIndent=16,
        spaceBefore=2, spaceAfter=8,
    ))

    s.append(Paragraph(
        "Please review this offer letter. If you accept the terms, kindly sign "
        f"below and return a copy to us by {SHORTBLANK} (date).", BODY))
    s.append(Paragraph("We look forward to welcoming you to our team.", BODY))

    s.append(Spacer(1, 8))
    s.append(Paragraph("Sincerely,", SIGN))
    s.append(Spacer(1, 16))
    s.append(Paragraph(f"<b>{SHORTBLANK}</b>", SIGN))
    s.append(Paragraph("<font color='#888888'>(Authorized Signatory Name)</font>", SIGN))
    s.append(Paragraph("<font color='#888888'>(Signatory Designation)</font>", SIGN))
    s.append(Paragraph("<b>Crownest Hospitality LLP</b>", SIGN))

    s.append(Spacer(1, 10))
    # Compact acceptance line (keeps the whole letter on a single page)
    s.append(Paragraph(
        "<b>Accepted &amp; agreed</b> (Shivansh Pande) &nbsp;&mdash;&nbsp; "
        f"Signature: {SHORTBLANK} &nbsp;&nbsp; Date: {SHORTBLANK}", SIGN))
    return s


# ---------------------------------------------------------------------------
# Generate the text-only overlay, then merge onto the letterhead
# ---------------------------------------------------------------------------
def build_overlay():
    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=(PAGE_W, PAGE_H),
        leftMargin=FRAME_X, rightMargin=FRAME_X,
        topMargin=PAGE_H - FRAME_TOP, bottomMargin=FRAME_BOTTOM,
    )
    frame = Frame(FRAME_X, FRAME_BOTTOM, FRAME_W, FRAME_H,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="lh", frames=[frame])])
    doc.build(build_story())
    buf.seek(0)
    return buf


def merge():
    overlay_reader = PdfReader(build_overlay())
    writer = PdfWriter()
    for i in range(len(overlay_reader.pages)):
        lh_page = PdfReader(LETTERHEAD).pages[0]   # fresh letterhead per page
        lh_page.merge_page(overlay_reader.pages[i])
        writer.add_page(lh_page)
    with open(OUTPUT, "wb") as f:
        writer.write(f)
    print(f"Wrote {OUTPUT} with {len(overlay_reader.pages)} page(s).")


if __name__ == "__main__":
    merge()

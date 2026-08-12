"""Generate the Vansh Singh Fartyal offer letter on the Crownest letterhead,
matching the short single-page example format."""
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    ListFlowable, ListItem
)
from reportlab.lib.colors import HexColor
from pypdf import PdfReader, PdfWriter

LETTERHEAD = "Crownest_Letterhead_A4.pdf"
OUTPUT = "Offer_Letter_Vansh_Singh_Fartyal.pdf"

PAGE_W, PAGE_H = A4  # 595 x 842 pt

LEFT = 70
RIGHT = 70
TOP = 170       # sit below the letterhead header (gold line ~152pt from top)
BOTTOM = 96     # stay above the footer band

styles = getSampleStyleSheet()
dark = HexColor("#2b2b2b")
gold = HexColor("#B08D3F")

body = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica",
                      fontSize=10.5, leading=15, alignment=TA_JUSTIFY, textColor=dark,
                      spaceAfter=8)
plain = ParagraphStyle("plain", parent=body, alignment=0, spaceAfter=2)
subj = ParagraphStyle("subj", parent=styles["Normal"], fontName="Helvetica-Bold",
                      fontSize=13, leading=16, textColor=gold, spaceBefore=6, spaceAfter=10)
hang = ParagraphStyle("hang", parent=body, alignment=0, spaceAfter=5,
                      leftIndent=18, firstLineIndent=-18)
keyhead = ParagraphStyle("keyhead", parent=styles["Normal"], fontName="Helvetica-Bold",
                         fontSize=10.5, leading=15, textColor=dark, spaceBefore=2, spaceAfter=5)

GOLD = "#B08D3F"

story = []
story.append(Paragraph("<b>Date:</b> _______________", plain))
story.append(Spacer(1, 10))
story.append(Paragraph("<b>To,</b>", plain))
story.append(Paragraph("<b>Vansh Singh Fartyal</b>", plain))
story.append(Paragraph("Vill - Noida, Morna, Sector 32, Gautam Buddh Nagar, Uttar Pradesh, India - 201301", plain))
story.append(Spacer(1, 12))
story.append(Paragraph("Subject: Offer of Employment", subj))
story.append(Paragraph("Dear Vansh,", body))
story.append(Paragraph(
    "We are pleased to offer you the position of <b>Floor Manager</b> at "
    "<b>Crownest Hospitality LLP</b> (a subsidiary of Azimuth Business on Wheels Private "
    "Limited).", body))
story.append(Paragraph("Please find the initial terms of your offer below:", body))

# Bulleted terms with gold bullets
story.append(Paragraph(
    f'<font color="{GOLD}">&bull;</font>&nbsp;&nbsp;<b>Designation:</b> Floor Manager', hang))
story.append(Paragraph(
    f'<font color="{GOLD}">&bull;</font>&nbsp;&nbsp;<b>Compensation:</b> Your salary will be '
    'Rs. 20,000 subject to standard statutory deductions.', hang))

story.append(Paragraph("Key Terms:", keyhead))
story.append(Paragraph(
    f'<font color="{GOLD}">1</font>&nbsp;&nbsp;You will be expected to carry out your duties '
    'diligently, maintaining our commitment to "Hospitality with Integrity".', hang))
story.append(Paragraph(
    f'<font color="{GOLD}">2</font>&nbsp;&nbsp;During your tenure, you will be bound by the '
    'standard rules, regulations, and confidentiality policies of Crownest Hospitality LLP '
    'and its parent company.', hang))
story.append(Spacer(1, 4))

story.append(Paragraph(
    "Please review this offer letter. If you accept the terms, kindly sign below and return a "
    "copy to us by _______________ (date).", body))
story.append(Paragraph("We look forward to welcoming you to our team.", body))
story.append(Spacer(1, 10))
story.append(Paragraph("Sincerely,", plain))
story.append(Spacer(1, 20))
story.append(Paragraph("________________", plain))
story.append(Paragraph("(Authorized Signatory Name)", plain))
story.append(Paragraph("(Signatory Designation)", plain))
story.append(Paragraph("<b>Crownest Hospitality LLP</b>", plain))
story.append(Spacer(1, 14))
story.append(Paragraph(
    "<b>Accepted &amp; agreed</b> (Vansh Singh Fartyal) &nbsp;—&nbsp; "
    "Signature: ________________ &nbsp;&nbsp; Date: ________________", plain))

# --- Build content PDF in memory ---
buf = io.BytesIO()
doc = BaseDocTemplate(buf, pagesize=A4,
                      leftMargin=LEFT, rightMargin=RIGHT,
                      topMargin=TOP, bottomMargin=BOTTOM)
frame = Frame(LEFT, BOTTOM, PAGE_W - LEFT - RIGHT, PAGE_H - TOP - BOTTOM, id="body")
doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])
doc.build(story)
buf.seek(0)

# --- Overlay content onto the letterhead background (per page) ---
content = PdfReader(buf)
writer = PdfWriter()
for page in content.pages:
    bg = PdfReader(LETTERHEAD).pages[0]
    base = writer.add_blank_page(width=float(bg.mediabox.width),
                                 height=float(bg.mediabox.height))
    base.merge_page(bg)
    base.merge_page(page)

with open(OUTPUT, "wb") as f:
    writer.write(f)

print(f"Wrote {OUTPUT} with {len(content.pages)} page(s)")

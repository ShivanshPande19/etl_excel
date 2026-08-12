"""Generate the Vansh Singh Fartyal offer letter rendered on the Crownest letterhead."""
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer
)
from reportlab.lib.colors import HexColor
from pypdf import PdfReader, PdfWriter

LETTERHEAD = "Crownest_Letterhead_A4.pdf"
OUTPUT = "Offer_Letter_Vansh_Singh_Fartyal.pdf"

PAGE_W, PAGE_H = A4  # 595 x 842 pt

# Margins tuned to sit inside the letterhead's header (gold line ~152pt from top)
# and above the footer band ("TRUSTED | RELIABLE | COMMITTED").
LEFT = 68
RIGHT = 68
TOP = 172      # distance from top of page
BOTTOM = 100   # distance from bottom of page

styles = getSampleStyleSheet()
dark = HexColor("#1a1a1a")

body = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica",
                      fontSize=10.5, leading=15, alignment=TA_JUSTIFY, textColor=dark,
                      spaceAfter=6)
plain = ParagraphStyle("plain", parent=body, alignment=0)
head = ParagraphStyle("head", parent=styles["Normal"], fontName="Helvetica-Bold",
                      fontSize=11, leading=15, textColor=dark, spaceBefore=4, spaceAfter=2)
subj = ParagraphStyle("subj", parent=styles["Normal"], fontName="Helvetica-Bold",
                      fontSize=12, leading=16, textColor=dark, spaceBefore=6, spaceAfter=8,
                      alignment=1)

story = []
story.append(Paragraph("<b>Date:</b> _______________", plain))
story.append(Spacer(1, 10))
story.append(Paragraph("<b>To,</b>", plain))
story.append(Paragraph("<b>Mr. Vansh Singh Fartyal</b>", plain))
story.append(Paragraph("Vill - Noida, Morna, Sector 32", plain))
story.append(Paragraph("Post - Gautam Buddh Nagar", plain))
story.append(Paragraph("Distt. - Gautam Buddh Nagar", plain))
story.append(Paragraph("Uttar Pradesh - 201301", plain))
story.append(Spacer(1, 10))
story.append(Paragraph("Subject: Letter of Offer / Appointment", subj))
story.append(Paragraph("Dear Mr. Vansh Singh Fartyal,", plain))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "We are pleased to offer you the position of <b>Floor Manager</b> at "
    "<b>Crownest Hospitality LLP</b>. We are confident that your skills and experience "
    "will be a valuable addition to our organization.", body))
story.append(Paragraph("The key terms and conditions of your offer are as follows:", body))

sections = [
    ("1. Designation",
     "You will be employed in the capacity of <b>Floor Manager</b>."),
    ("2. Compensation",
     "Your compensation will be <b>Rs. 20,000/- (Rupees Twenty Thousand only) per month</b>, "
     "payable in accordance with the Company's payroll policy and subject to applicable "
     "statutory deductions."),
    ("3. Place of Work",
     "Your primary place of work will be at the Company's office. However, you may be required "
     "to work at or be transferred to any other location as per business requirements."),
    ("4. Working Hours",
     "You will observe the working hours, days, and shift schedules as applicable to your role "
     "and as communicated by the Company from time to time."),
    ("5. Duties and Responsibilities",
     "You will perform the duties assigned to you diligently and to the best of your ability. "
     "The Company reserves the right to modify your role, responsibilities, and reporting "
     "structure as per organizational needs."),
    ("6. Confidentiality",
     "During and after your employment, you shall maintain strict confidentiality regarding all "
     "proprietary, business, and client-related information of the Company."),
    ("7. Governing Terms",
     "Your employment will be governed by the rules, regulations, and policies of the Company, "
     "as amended from time to time."),
]
for title, text in sections:
    story.append(Paragraph(title, head))
    story.append(Paragraph(text, body))

story.append(Spacer(1, 8))
story.append(Paragraph(
    "We look forward to a long and mutually rewarding association. Kindly sign and return the "
    "duplicate copy of this letter as a token of your acceptance of the above terms and "
    "conditions.", body))
story.append(Paragraph(
    "We welcome you to the <b>Crownest Hospitality LLP</b> family and wish you a successful "
    "career with us.", body))
story.append(Spacer(1, 16))
story.append(Paragraph("<b>For Crownest Hospitality LLP</b>", plain))
story.append(Spacer(1, 26))
story.append(Paragraph("_______________________________", plain))
story.append(Paragraph("<b>Authorized Signatory</b>", plain))
story.append(Spacer(1, 16))
story.append(Paragraph("<b>Acceptance</b>", head))
story.append(Paragraph(
    "I, <b>Mr. Vansh Singh Fartyal</b>, have read and understood the terms and conditions "
    "mentioned above and hereby accept this offer.", body))
story.append(Spacer(1, 14))
story.append(Paragraph(
    "Signature: _______________________     Date: _______________________", plain))

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

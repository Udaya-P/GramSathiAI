"""Render verified minutes with embedded Unicode fonts and transcript evidence."""
from pathlib import Path

from fastapi import HTTPException
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from sqlalchemy import select

from app import models, schemas
from app.services import integrity, meeting_service

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"
FONTS = ("NotoSans", "NotoSansDevanagari", "NotoSansKannada", "NotoSansTelugu")
LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "kn": "Kannada", "te": "Telugu"}
DISCLAIMER = "Prototype-generated meeting record. This report is not an official government certificate."


class MinutesPDF(FPDF):
    def line_of_text(self, text: str, *, size=10, color=(32, 49, 43)):
        self.set_font("NotoSans", size=size)
        self.set_text_color(*color)
        self.multi_cell(w=0, h=size * 0.48, text=text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def section(self, title: str):
        if self.will_page_break(24):
            self.add_page()
        self.ln(3)
        self.line_of_text(title, size=13, color=(31, 93, 58))
        self.ln(1)

    def header(self):
        self.line_of_text("GRAMSATHI AI  /  GRAM SABHA", size=9, color=(31, 93, 58))

    def footer(self):
        self.set_y(-15)
        self.line_of_text(f"GramSathi AI  |  Prototype meeting record  |  Page {self.page_no()}",
                          size=8, color=(75, 94, 86))


def _evidence(pdf, ids, quotes, segments):
    if not ids:
        return
    pdf.line_of_text("Evidence: " + ", ".join(f"#{segment_id}" for segment_id in ids), size=9)
    for segment_id in dict.fromkeys(ids):
        text = segments.get(segment_id)
        if not text:
            pdf.line_of_text(f"#{segment_id}  Transcript text unavailable", size=9)
            continue
        excerpts = [q.quote for q in quotes if q.segment_id == segment_id and q.quote in text]
        if not excerpts:
            excerpt = text[:420].rstrip()
            suffix = " [excerpt]" if len(text) > 420 else ""
            pdf.line_of_text(f'#{segment_id}  "{excerpt}"{suffix}', size=9)
        for quote in excerpts:
            pdf.line_of_text(f'#{segment_id}  "{quote}"', size=9)


def render_minutes_pdf(meeting: schemas.MeetingOut, minutes: schemas.MinutesOut, segments: dict[int, str]) -> bytes:
    pdf = MinutesPDF(format="A4")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(auto=True, margin=21)
    for family in FONTS:
        pdf.add_font(family, fname=FONT_DIR / f"{family}-Regular.ttf")
    pdf.set_fallback_fonts(FONTS[1:])
    pdf.set_text_shaping(True)
    pdf.set_title("Verified Gram Sabha meeting minutes")
    pdf.set_creator("GramSathi AI")
    pdf.add_page()

    pdf.line_of_text("Verified meeting minutes", size=22)
    pdf.line_of_text(DISCLAIMER, size=9, color=(75, 94, 86))

    pdf.section("Meeting details")
    pdf.line_of_text(meeting.title, size=14)
    pdf.line_of_text(f"Meeting date: {meeting.meeting_date.isoformat()}")
    pdf.line_of_text(f"Location: {meeting.village_name}, {meeting.district}, {meeting.state}")
    primary = LANGUAGE_NAMES.get(meeting.primary_language, meeting.primary_language)
    languages = ", ".join(LANGUAGE_NAMES.get(code, code) for code in meeting.supported_languages)
    pdf.line_of_text(f"Primary language: {primary}  |  Languages: {languages}")
    pdf.line_of_text(f"Meeting ID: {meeting.id}  |  Revision: {minutes.revision}", size=9)
    if meeting.description:
        pdf.line_of_text(meeting.description)

    pdf.section("Draft origin and human verification")
    source = {"groq": "AI-generated draft (Groq)", "evon": "AI-generated draft (Evon)",
              "mock_fixture": "Development fixture draft", "manual": "Manually authored draft"}
    origin = source.get(minutes.generation_source, f"Draft source: {minutes.generation_source}")
    model = f"  |  Model: {minutes.generation_model}" if minutes.generation_model else ""
    pdf.line_of_text(f"{origin}{model}")
    verified_at = minutes.verified_at.isoformat(timespec="seconds") if minutes.verified_at else "Unavailable"
    pdf.line_of_text(f"Human verifier: {minutes.verifier_name or 'Unavailable'}")
    pdf.line_of_text(f"Verified at: {verified_at}")

    pdf.section("Meeting summary")
    pdf.line_of_text(minutes.summary)
    claim_ids = {i for claim in minutes.summary_claims for i in claim.evidence_segment_ids}
    _evidence(pdf, [i for i in minutes.summary_evidence_segment_ids if i not in claim_ids], (), segments)
    for claim in minutes.summary_claims:
        pdf.ln(1)
        pdf.line_of_text(claim.text)
        _evidence(pdf, claim.evidence_segment_ids, claim.evidence_quotes, segments)

    approved = [d for d in minutes.decisions if d.classification == "approved"]
    other = [d for d in minutes.decisions if d.classification != "approved"]
    for title, decisions in (("Approved decisions", approved), ("Other decisions and proposals", other)):
        pdf.section(title)
        if not decisions:
            pdf.line_of_text("None recorded.")
        for decision in decisions:
            pdf.line_of_text(f"{(decision.classification or decision.status).title()}: {decision.description}")
            for label, amount in (("Estimated cost", decision.estimated_amount),
                                  ("Proposed budget", decision.proposed_amount),
                                  ("Approved budget", decision.approved_amount)):
                if amount is not None:
                    currency = decision.currency or "Currency unspecified"
                    pdf.line_of_text(f"{label}: {currency} {amount:,.2f}")
            _evidence(pdf, decision.evidence_segment_ids, decision.evidence_quotes, segments)
            pdf.ln(2)

    pdf.section("Action items")
    if not minutes.action_items:
        pdf.line_of_text("None recorded.")
    for item in minutes.action_items:
        pdf.line_of_text(item.task)
        pdf.line_of_text(f"Assigned responsibility: {item.assigned_to or 'Unassigned'}")
        deadlines = [value for value in (item.deadline.isoformat() if item.deadline else None, item.deadline_text) if value]
        pdf.line_of_text("Deadline: " + (" / ".join(deadlines) or "Unspecified"))
        _evidence(pdf, item.evidence_segment_ids, item.evidence_quotes, segments)
        pdf.ln(2)

    pdf.section("Unresolved issues")
    if not minutes.unresolved_issues:
        pdf.line_of_text("None recorded.")
    for issue in minutes.unresolved_issues:
        pdf.line_of_text(issue.description)
        _evidence(pdf, issue.evidence_segment_ids, issue.evidence_quotes, segments)
        pdf.ln(2)
    return bytes(pdf.output())


def export_verified_minutes(db, meeting_id, owner_id):
    meeting = meeting_service.owned_meeting(db, meeting_id, owner_id)
    minutes = meeting_service.current_minutes(db, meeting_id)
    if minutes.status != "verified":
        raise HTTPException(409, "Verify the minutes before exporting a PDF.")
    document = schemas.MinutesOut.model_validate(minutes)
    refs = integrity.evidence_ids(document)
    segments = {}
    if refs:
        segments = dict(db.execute(select(models.TranscriptSegment.id, models.TranscriptSegment.text).where(
            models.TranscriptSegment.meeting_id == meeting_id, models.TranscriptSegment.id.in_(refs)
        )).tuples().all())
    return render_minutes_pdf(schemas.MeetingOut.model_validate(meeting), document, segments)

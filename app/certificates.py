import os
from pathlib import Path

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


def generate_certificate(name: str, event_name: str, issued_on: str, destination: str) -> str:
    """Render one certificate PDF and return its path."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    page = landscape(letter)
    pdf = canvas.Canvas(str(path), pagesize=page)
    width, height = page
    pdf.setTitle(f"Certificate - {name}")
    pdf.setStrokeColorRGB(0.72, 0.56, 0.24)
    pdf.setLineWidth(4)
    pdf.rect(0.45 * inch, 0.45 * inch, width - 0.9 * inch, height - 0.9 * inch)
    pdf.setFillColorRGB(0.12, 0.19, 0.29)
    pdf.setFont("Helvetica-Bold", 30)
    pdf.drawCentredString(width / 2, height - 1.65 * inch, "CERTIFICATE OF ACHIEVEMENT")
    pdf.setFillColorRGB(0.25, 0.29, 0.34)
    pdf.setFont("Helvetica", 16)
    pdf.drawCentredString(width / 2, height - 2.35 * inch, "This certificate is proudly presented to")
    pdf.setFillColorRGB(0.12, 0.19, 0.29)
    pdf.setFont("Helvetica-Bold", 27)
    pdf.drawCentredString(width / 2, height - 3.15 * inch, name[:100])
    pdf.setFillColorRGB(0.25, 0.29, 0.34)
    pdf.setFont("Helvetica", 16)
    pdf.drawCentredString(width / 2, height - 3.8 * inch, f"for successful completion of {event_name[:120]}")
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(width / 2, 1.25 * inch, f"Issued on {issued_on}")
    pdf.save()
    return os.fspath(path)

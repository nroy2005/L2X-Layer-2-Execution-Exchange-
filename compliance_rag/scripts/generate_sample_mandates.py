"""One-off helper to create sample mandates.pdf (requires fpdf2)."""

from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "mandates.pdf"

LINES = [
    "Trade Surveillance Mandates (Sample)",
    "",
    "1. Wash Trading: Same beneficial owner on both sides without legitimate risk change is prohibited.",
    "2. Spoofing: Orders intended to cancel before fill to manipulate price are prohibited.",
    "3. Large Notional: Single trade notional over USD 500000 must be flagged within 24 hours.",
    "4. Volatility: During volatile modes review trades within 15 minutes.",
    "5. Size Anomalies: Size over 10x baseline hourly average requires alert.",
    "6. Side Imbalance: Over 80 percent one-sided flow for 5 minutes triggers review.",
    "7. Record Retention: Retain ingested trade prints for seven years.",
]


def main() -> None:
    pdf = FPDF()
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    width = pdf.epw
    for line in LINES:
        if not line.strip():
            pdf.ln(4)
            continue
        pdf.multi_cell(width, 6, line)
    pdf.output(str(OUT))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()

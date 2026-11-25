#!/usr/bin/env python3
"""
Generate minimal, self-contained fixtures for Veridocs testing and evaluation.
Includes clean digital PDFs, scanned documents with OCR preprocessing,
plain-text contracts, and multi-format structured tables.
"""

from pathlib import Path
from PIL import Image, ImageDraw

fixtures_dir = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
fixtures_dir.mkdir(parents=True, exist_ok=True)


def create_digital_pdf(path: Path):
    """Create a digital PDF with extractable text layer."""
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length 135 >> stream\n"
        b"BT\n"
        b"/F1 14 Tf\n"
        b"50 720 Td\n"
        b"(ACME Cloud Services Agreement) Tj\n"
        b"0 -30 Td\n"
        b"(Section 1. Payment Terms: Invoices are payable net 30 days.) Tj\n"
        b"0 -25 Td\n"
        b"(Section 2. Service Level: Monthly uptime SLA is 99.95 percent.) Tj\n"
        b"ET\n"
        b"endstream\n"
        b"endobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000244 00000 n \n"
        b"0000000431 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"startxref\n"
        b"508\n"
        b"%%EOF\n"
    )
    path.write_bytes(pdf_content)
    print(f"Created {path}")


def create_scanned_pdf(path: Path):
    """Create a high-resolution 300 DPI scanned PDF fixture."""
    # 300 DPI canvas
    img = Image.new("RGB", (1800, 900), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((80, 100), "CONFIDENTIAL DISCLOSURE NOTICE", fill=(0, 0, 0))
    draw.text((80, 220), "Authorized personnel only. Data retention: 7 years.", fill=(0, 0, 0))
    draw.text((80, 340), "Penalty for unauthorized disclosure: $100,000 fine.", fill=(0, 0, 0))
    img.save(path, "PDF", resolution=300.0)
    print(f"Created {path}")


def create_scanned_receipt(path: Path):
    """Create a scanned receipt fixture with line items and totals."""
    img = Image.new("RGB", (1200, 1600), color=(250, 250, 250))
    draw = ImageDraw.Draw(img)
    draw.text((100, 100), "GROCERY DEPOT", fill=(10, 10, 10))
    draw.text((100, 180), "Receipt #8821 Date: 2026-11-20", fill=(10, 10, 10))
    draw.text((100, 260), "Organic Milk $4.50", fill=(10, 10, 10))
    draw.text((100, 340), "Whole Wheat Bread $3.25", fill=(10, 10, 10))
    draw.text((100, 420), "Subtotal: $7.75", fill=(10, 10, 10))
    draw.text((100, 500), "Tax: $0.62", fill=(10, 10, 10))
    draw.text((100, 580), "Total: $8.37", fill=(10, 10, 10))
    draw.text((100, 660), "Thank you for shopping with us!", fill=(10, 10, 10))
    img.save(path, "PDF", resolution=300.0)
    print(f"Created {path}")


def create_noisy_form(path: Path):
    """Create a slightly noisy scanned registration form fixture."""
    img = Image.new("RGB", (1500, 1200), color=(248, 248, 246))
    draw = ImageDraw.Draw(img)
    draw.text((80, 80), "EMPLOYEE ENROLLMENT FORM", fill=(20, 20, 20))
    draw.text((80, 180), "Name: Jane Doe", fill=(20, 20, 20))
    draw.text((80, 280), "Department: Engineering", fill=(20, 20, 20))
    draw.text((80, 380), "Start Date: 2026-12-01", fill=(20, 20, 20))
    draw.text((80, 480), "Status: Full-Time", fill=(20, 20, 20))
    draw.text((80, 580), "Approved by HR Operations.", fill=(20, 20, 20))

    # Add subtle scan artifact lines
    draw.line([(50, 700), (1400, 700)], fill=(220, 220, 220), width=2)
    img.save(path, "PDF", resolution=300.0)
    print(f"Created {path}")


def create_scanned_letter(path: Path):
    """Create a scanned corporate board resolution letterhead PNG."""
    img = Image.new("RGB", (1400, 1000), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((80, 80), "GLOBAL LOGISTICS PARTNERS", fill=(0, 0, 0))
    draw.text((80, 180), "Board of Directors Resolution", fill=(0, 0, 0))
    draw.text(
        (80, 280),
        "The board has unanimously resolved to approve the international fulfillment expansion plan effective Q1 2027.",
        fill=(0, 0, 0),
    )
    img.save(path, "PNG")
    print(f"Created {path}")


def create_png_invoice(path: Path):
    """Create a sample scanned PNG invoice."""
    img = Image.new("RGB", (1400, 800), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((80, 60), "INVOICE #INV-2026-904", fill=(0, 0, 0))
    draw.text((80, 140), "Customer: Globex Corporation", fill=(0, 0, 0))
    draw.text((80, 220), "Service: Enterprise Cloud License", fill=(0, 0, 0))
    draw.text((80, 300), "Amount Due: $14,500.00", fill=(0, 0, 0))
    draw.text((80, 380), "Due Date: 2026-12-15", fill=(0, 0, 0))
    img.save(path, "PNG")
    print(f"Created {path}")


def create_table_pdf(path: Path):
    """Create a digital PDF with a pricing tier schedule table."""
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length 260 >> stream\n"
        b"BT\n"
        b"/F1 12 Tf\n"
        b"40 720 Td\n"
        b"(Pricing Tier Schedule) Tj\n"
        b"0 -30 Td\n"
        b"(| Tier | Storage | Monthly Cost |) Tj\n"
        b"0 -18 Td\n"
        b"(| Basic | 100 GB | $50 |) Tj\n"
        b"0 -18 Td\n"
        b"(| Pro | 1 TB | $250 |) Tj\n"
        b"0 -18 Td\n"
        b"(| Enterprise | Unlimited | $1200 |) Tj\n"
        b"ET\n"
        b"endstream\n"
        b"endobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Courier >> endobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000244 00000 n \n"
        b"0000000556 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"startxref\n"
        b"631\n"
        b"%%EOF\n"
    )
    path.write_bytes(pdf_content)
    print(f"Created {path}")


def create_financial_report_pdf(path: Path):
    """Create a digital PDF with a quarterly financial statement table."""
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length 280 >> stream\n"
        b"BT\n"
        b"/F1 12 Tf\n"
        b"40 720 Td\n"
        b"(Quarterly Financial Statement) Tj\n"
        b"0 -30 Td\n"
        b"(| Metric | Q1 2026 | Q2 2026 | Q3 2026 |) Tj\n"
        b"0 -18 Td\n"
        b"(| Revenue | $12.4M | $14.1M | $15.8M |) Tj\n"
        b"0 -18 Td\n"
        b"(| Operating Expenses | $7.2M | $7.8M | $8.1M |) Tj\n"
        b"0 -18 Td\n"
        b"(| Net Income | $5.2M | $6.3M | $7.7M |) Tj\n"
        b"ET\n"
        b"endstream\n"
        b"endobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Courier >> endobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000244 00000 n \n"
        b"0000000576 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"startxref\n"
        b"651\n"
        b"%%EOF\n"
    )
    path.write_bytes(pdf_content)
    print(f"Created {path}")


def create_balance_sheet_pdf(path: Path):
    """Create a digital PDF with a balance sheet assets/liabilities table."""
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length 280 >> stream\n"
        b"BT\n"
        b"/F1 12 Tf\n"
        b"40 720 Td\n"
        b"(Consolidated Balance Sheet) Tj\n"
        b"0 -30 Td\n"
        b"(| Category | 2025 | 2026 |) Tj\n"
        b"0 -18 Td\n"
        b"(| Current Assets | $4,500,000 | $5,800,000 |) Tj\n"
        b"0 -18 Td\n"
        b"(| Total Liabilities | $1,800,000 | $2,100,000 |) Tj\n"
        b"0 -18 Td\n"
        b"(| Shareholder Equity | $2,700,000 | $3,700,000 |) Tj\n"
        b"ET\n"
        b"endstream\n"
        b"endobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Courier >> endobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000244 00000 n \n"
        b"0000000576 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"startxref\n"
        b"651\n"
        b"%%EOF\n"
    )
    path.write_bytes(pdf_content)
    print(f"Created {path}")


def create_service_tiers_pdf(path: Path):
    """Create a digital PDF with a multi-column infrastructure service tier matrix."""
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length 320 >> stream\n"
        b"BT\n"
        b"/F1 12 Tf\n"
        b"40 720 Td\n"
        b"(Cloud Compute and Infrastructure Tiers) Tj\n"
        b"0 -30 Td\n"
        b"(| Plan | vCPU | RAM | Bandwidth | Price |) Tj\n"
        b"0 -18 Td\n"
        b"(| Starter | 2 | 4 GB | 1 TB | $20 |) Tj\n"
        b"0 -18 Td\n"
        b"(| Professional | 4 | 16 GB | 5 TB | $80 |) Tj\n"
        b"0 -18 Td\n"
        b"(| Dedicated | 16 | 64 GB | Unlimited | $350 |) Tj\n"
        b"ET\n"
        b"endstream\n"
        b"endobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Courier >> endobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000244 00000 n \n"
        b"0000000616 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"startxref\n"
        b"691\n"
        b"%%EOF\n"
    )
    path.write_bytes(pdf_content)
    print(f"Created {path}")


def create_txt_contract(path: Path):
    """
    Create an authentic plain-text contract without markdown pipe table formatting.
    Avoids synthetic pipe characters so plain text contracts do not falsely trigger table extraction.
    """
    content = (
        "MASTER SERVICES AGREEMENT\n\n"
        "SECTION 1. SCOPE OF SERVICES\n"
        "Provider agrees to deliver managed document AI processing and validation.\n\n"
        "SECTION 2. PRICING AND PAYMENTS\n"
        "Ingestion rate is $0.05 per document OCR. Storage rate is $0.20 monthly per GB.\n"
        "Invoices shall be payable within thirty (30) days of the date of invoice.\n\n"
        "SECTION 3. CONFIDENTIALITY\n"
        "Each party agrees to hold all confidential information in strict confidence.\n"
    )
    path.write_text(content, encoding="utf-8")
    print(f"Created {path}")


def main():
    create_digital_pdf(fixtures_dir / "digital_doc.pdf")
    create_scanned_pdf(fixtures_dir / "scanned_doc.pdf")
    create_scanned_receipt(fixtures_dir / "scanned_receipt.pdf")
    create_noisy_form(fixtures_dir / "noisy_form.pdf")
    create_scanned_letter(fixtures_dir / "scanned_letter.png")
    create_png_invoice(fixtures_dir / "scanned_invoice.png")
    create_table_pdf(fixtures_dir / "table_doc.pdf")
    create_financial_report_pdf(fixtures_dir / "financial_report.pdf")
    create_balance_sheet_pdf(fixtures_dir / "balance_sheet.pdf")
    create_service_tiers_pdf(fixtures_dir / "service_tiers.pdf")
    create_txt_contract(fixtures_dir / "contract.txt")
    print(f"All 11 test fixtures generated successfully in {fixtures_dir}")


if __name__ == "__main__":
    main()

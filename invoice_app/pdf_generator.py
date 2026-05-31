
"""
PDF invoice generator (layout updates):
- Header: Tax Invoice & logo centered inside their cells
- Meta: UDYAM moved to right column below Email; then Challan No/Date row
- Spacers before blocks to match visual rhythm
- Two-column blocks: 'Invoice To' (left) and 'Ship To' (right) with Name, Address, GSTIN
- Items header: white background, blue captions; numeric columns right
- Totals computed at invoice level; Amount in words uses rounded total
- Bank Details: line-by-line (Account number, Branch Name, IFSC, Branch Address) + Authorised Signatory on right
- Rupee (₹) rendered reliably via Unicode TTF registration
"""
import sys
from pathlib import Path
from typing import Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image, Spacer
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .models import Invoice, ConfigManager

# Determine output directory based on whether running as exe or from source
if hasattr(sys, '_MEIPASS'):
    # Running as PyInstaller exe - use exe directory
    exe_dir = Path(sys.executable).parent
    OUTPUT_DIR = exe_dir / "data" / "invoices"
else:
    # Running from source - use project data folder
    OUTPUT_DIR = Path(__file__).parent.parent / "data" / "invoices"

# ---- Widths / colors --------------------------------------------------------
LEFT_MARGIN_PT  = 8 * mm
RIGHT_MARGIN_PT = 8 * mm
PAGE_WIDTH_PT   = A4[0]
CONTENT_WIDTH   = PAGE_WIDTH_PT - (LEFT_MARGIN_PT + RIGHT_MARGIN_PT)  # ~6.5 inch with 8mm margins

BLUE  = colors.HexColor('#0047AB')
WHITE = colors.white

def base_table_style(line_width=1, padding=4) -> TableStyle:
    """BOX + INNERGRID for cleaner borders without double-thick edges."""
    return TableStyle([
        ('BOX',           (0, 0), (-1, -1), line_width, colors.black),
        ('INNERGRID',     (0, 0), (-1, -1), line_width, colors.black),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING',   (0, 0), (-1, -1), padding),
        ('RIGHTPADDING',  (0, 0), (-1, -1), padding),
        ('TOPPADDING',    (0, 0), (-1, -1), padding),
        ('BOTTOMPADDING', (0, 0), (-1, -1), padding),
    ])

def _register_app_font() -> str:
    """
    Register a Unicode TTF that includes U+20B9 (₹).
    Reads 'font_path' from config.json; if missing/invalid, tries common system fonts.
    """
    cfg = ConfigManager()
    candidates = []
    fp = cfg.get('font_path', '')
    if fp:
        candidates.append(fp)
    candidates += [
        r"C:\Windows\Fonts\DejaVuSans.ttf",
        r"C:\Windows\Fonts\NotoSans-Regular.ttf",
        r"C:\Windows\Fonts\ArialUni.ttf",
        r"C:\Windows\Fonts\Arial.ttf",
        r"C:/Windows/Fonts/DejaVuSans.ttf",
        r"C:/Windows/Fonts/NotoSans-Regular.ttf",
        r"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        r"/Library/Fonts/Arial Unicode.ttf",
    ]
    for p in candidates:
        if p and Path(p).exists():
            try:
                pdfmetrics.registerFont(TTFont("AppFont", p))
                return "AppFont"
            except Exception:
                continue
    # Fallback: try Helvetica with rupee substitution
    return "Helvetica"

def amount_in_words_inr(amount: float) -> str:
    NUM_WORDS_1_TO_19 = [
        "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
        "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen",
        "Eighteen", "Nineteen"
    ]
    TENS_WORDS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def _two_digit_words(n: int) -> str:
        if n < 20: return NUM_WORDS_1_TO_19[n]
        t, u = divmod(n, 10)
        return TENS_WORDS[t] + (" " + NUM_WORDS_1_TO_19[u] if u else "")

    rupees = int(round(amount))
    paise = int(round((amount - int(amount)) * 100))
    parts = []
    crore, rupees = divmod(rupees, 10_000_000)
    lakh, rupees = divmod(rupees, 100_000)
    thousand, rupees = divmod(rupees, 1000)
    hundred, rupees = divmod(rupees, 100)
    if crore:   parts.append(_two_digit_words(crore)   + " Crore")
    if lakh:    parts.append(_two_digit_words(lakh)    + " Lakh")
    if thousand:parts.append(_two_digit_words(thousand)+ " Thousand")
    if hundred: parts.append(NUM_WORDS_1_TO_19[hundred]+ " Hundred")
    if rupees:  parts.append(_two_digit_words(rupees))
    words = " ".join(parts) if parts else "Zero"
    return f"Rupees {words} Only" if not paise else f"Rupees {words} and {paise} Paise Only"

def generate_pdf(invoice: Invoice, logo_path: Optional[str] = None) -> str:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    app_font = _register_app_font()

    safe_invoice_number = (
        invoice.invoice_number.replace('/', '-').replace('\\', '-').replace(':', '-')
    )
    pdf_filename = f"{safe_invoice_number}.pdf"
    pdf_path = OUTPUT_DIR / pdf_filename

    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=A4,
        topMargin=8*mm, bottomMargin=8*mm,
        leftMargin=LEFT_MARGIN_PT, rightMargin=RIGHT_MARGIN_PT
    )
    story = []
    styles = getSampleStyleSheet()

    # Styles (explicit font names; never None)
    title_style = ParagraphStyle('Title', parent=styles['Normal'],
                                 fontSize=12, leading=14,
                                 fontName=app_font, textColor=colors.black,
                                 alignment=TA_CENTER)
    label_style = ParagraphStyle('Label', parent=styles['Normal'],
                                 fontSize=8, leading=10,
                                 fontName=app_font, textColor=colors.black)
    value_style = ParagraphStyle('Value', parent=styles['Normal'],
                                 fontSize=8, leading=10,
                                 fontName=app_font, textColor=colors.black)
    small_center = ParagraphStyle('SmallCenter', parent=styles['Normal'],
                                  fontSize=8, leading=10,
                                  fontName=app_font, textColor=colors.black,
                                  alignment=TA_CENTER)

    # ===== Calculate totals (for all items, for summary display)
    subtotal    = sum(it.total_price for it in invoice.line_items)
    sgst        = sum(it.sgst_amount for it in invoice.line_items)
    cgst        = sum(it.cgst_amount for it in invoice.line_items)
    sgst_eff    = (sgst / subtotal * 100.0) if subtotal else 0.0
    cgst_eff    = (cgst / subtotal * 100.0) if subtotal else 0.0
    total       = subtotal + sgst + cgst
    import decimal
    round_total = float(decimal.Decimal(str(total)).quantize(decimal.Decimal('1'), rounding=decimal.ROUND_HALF_UP))

    # ===== Pagination: split items into pages (max 5 per page)
    items_per_page = 5
    item_pages = []
    for i in range(0, len(invoice.line_items), items_per_page):
        item_pages.append(invoice.line_items[i:i+items_per_page])
    
    if not item_pages:
        item_pages = [[]]  # At least one page, even if empty

    # ===== Helper function to build header section
    def build_header():
        header_row = [Paragraph("<b>Tax Invoice</b>", title_style)]

        if not logo_path:
            default_logo = Path(__file__).parent / "logo.png"
            if default_logo.exists():
                logo_path_use = str(default_logo)
            else:
                logo_path_use = None
        else:
            logo_path_use = logo_path

        if logo_path_use and Path(logo_path_use).exists():
            try:
                ir = ImageReader(logo_path_use)
                iw, ih = ir.getSize()
                target_w_pt = 1.5 * 72
                scale = target_w_pt / float(iw)
                logo = Image(logo_path_use, width=target_w_pt, height=ih * scale)
                header_row.append(logo)
            except Exception:
                header_row.append("")
        else:
            header_row.append("")

        header_table = Table(
            [header_row],
            colWidths=[CONTENT_WIDTH * (5.0/6.5), CONTENT_WIDTH * (1.5/6.5)],
            hAlign='LEFT'
        )
        header_table.setStyle(TableStyle(base_table_style().getCommands() + [
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ]))
        return header_table

    # ===== Helper function to build meta section
    def build_meta():
        def L(label, value):
            return Paragraph(f"<b>{label}</b> {value}", value_style)

        meta_rows = [
            [L('Company Name:', invoice.company_name), L('Invoice No:', invoice.invoice_number)],
            [L('ADDRESS:', invoice.company_address), L('Invoice Date:', invoice.invoice_date)],
        ]
        
        # Build right-side optional fields list (only those with values)
        optional_right_fields = []
        if invoice.po_number and invoice.po_number.strip():
            optional_right_fields.append(L('Po No:', invoice.po_number))
        if invoice.po_date and invoice.po_date.strip():
            optional_right_fields.append(L('Po Date:', invoice.po_date))
        if invoice.challan_number and invoice.challan_number.strip():
            optional_right_fields.append(L('Challan No:', invoice.challan_number))
        if invoice.challan_date and invoice.challan_date.strip():
            optional_right_fields.append(L('Challan Date:', invoice.challan_date))
        
        # Left-side labels for optional fields section
        left_labels = ['GSTIN:', 'Phone:', 'Email:', 'UDYAM REGISTRATION NUMBER:']
        left_values = [invoice.company_gstin, invoice.company_phone, invoice.company_email, invoice.udyam_registration]
        
        # Add rows with left labels and dynamic right-side optional fields
        for i in range(len(left_labels)):
            right_content = optional_right_fields[i] if i < len(optional_right_fields) else Paragraph("", value_style)
            meta_rows.append([L(left_labels[i], left_values[i]), right_content])
        
        meta_table = Table(meta_rows, colWidths=[CONTENT_WIDTH/2, CONTENT_WIDTH/2], hAlign='LEFT')
        meta_table.setStyle(base_table_style())
        meta_table.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'LEFT')]))
        return meta_table

    # ===== Helper function to build additional info section
    def build_additional_info():
        line1 = getattr(invoice, 'additional_info_line1', '').strip()
        line2 = getattr(invoice, 'additional_info_line2', '').strip()
        if not (line1 or line2):
            return None
        
        additional_rows = [
            [Paragraph('<b>Additional Information</b>', label_style)],
        ]
        if line1:
            additional_rows.append([Paragraph(line1, value_style)])
        if line2:
            additional_rows.append([Paragraph(line2, value_style)])
        additional_table = Table(additional_rows, colWidths=[CONTENT_WIDTH], hAlign='LEFT')
        additional_table.setStyle(base_table_style())
        return additional_table

    # ===== Helper function to build two-column section (Invoice To / Ship To)
    def build_customer_section():
        inv_to_name  = Paragraph(invoice.customer_name or "", value_style)
        inv_to_addr  = Paragraph(invoice.customer_address or "", value_style)
        inv_to_gstin = Paragraph(f"GSTIN: {invoice.customer_gstin or ''}", value_style)

        ship_to_name  = Paragraph(getattr(invoice, 'ship_to_name', '') or "", value_style)
        ship_to_addr  = Paragraph(getattr(invoice, 'ship_to_address', '') or "", value_style)
        ship_to_gstin = Paragraph(f"GSTIN: {getattr(invoice, 'ship_to_gstin', '') or ''}", value_style)

        two_col_rows = [
            [Paragraph('<b>Invoice To</b>', label_style), Paragraph('<b>Ship To</b>', label_style)],
            [inv_to_name,  ship_to_name],
            [inv_to_addr,  ship_to_addr],
            [inv_to_gstin, ship_to_gstin],
        ]
        two_col_table = Table(two_col_rows, colWidths=[CONTENT_WIDTH/2, CONTENT_WIDTH/2], hAlign='LEFT')
        two_col_table.setStyle(base_table_style())
        two_col_table.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'LEFT')]))
        return two_col_table

    # ===== Helper function to build items table for a specific page
    def build_items_table(page_items):
        items_header = ['Description', 'HSN', 'Qty', 'UOM', 'Unit price', 'Total price']
        items_data = [items_header]
        for it in page_items:
            items_data.append([
                Paragraph(it.description, value_style),
                Paragraph(it.hsn, value_style),
                Paragraph(f"{it.qty:.2f}", value_style),
                Paragraph(it.uom, value_style),
                Paragraph(f"₹{it.unit_price:.2f}", value_style),
                Paragraph(f"₹{it.total_price:.2f}", value_style),
            ])

        items_table = Table(
            items_data,
            colWidths=[
                CONTENT_WIDTH * (2.30/6.5),
                CONTENT_WIDTH * (0.90/6.5),
                CONTENT_WIDTH * (0.70/6.5),
                CONTENT_WIDTH * (0.70/6.5),
                CONTENT_WIDTH * (0.95/6.5),
                CONTENT_WIDTH * (0.95/6.5),
            ],
            rowHeights=[None] + [18] * len(page_items),  # Header auto, data rows 18pt
            hAlign='LEFT'
        )
        items_table.setStyle(TableStyle(base_table_style().getCommands() + [
            ('BACKGROUND', (0, 0), (-1, 0), WHITE),
            ('TEXTCOLOR',  (0, 0), (-1, 0), BLUE),
            ('FONTNAME',   (0, 0), (-1, 0), app_font),
            ('FONTSIZE',   (0, 0), (-1, 0), 9),
            ('ALIGN',      (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN',      (0, 1), (0, -1), 'LEFT'),
            ('ALIGN',      (1, 1), (-1, -1), 'RIGHT'),
            ('TOPPADDING',    (0, 0), (-1, 0), 6),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('TOPPADDING',    (0, 1), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 2),
            ('VALIGN',       (0, 1), (-1, -1), 'MIDDLE'),
        ]))
        return items_table

    # ===== Helper function to build totals section (only on last page)
    def build_totals_section():
        totals_rows = [
            [Paragraph('<b>Subtotal</b>', label_style),                       Paragraph(f"₹{subtotal:.2f}", value_style)],
            [Paragraph(f'<b>SGST ({sgst_eff:.2f}%)</b>', label_style), Paragraph(f"₹{sgst:.2f}", value_style)],
            [Paragraph(f'<b>CGST ({cgst_eff:.2f}%)</b>', label_style), Paragraph(f"₹{cgst:.2f}", value_style)],
            [Paragraph('<b>Total Amount in INR</b>', label_style),            Paragraph(f"₹{total:.2f}", value_style)],
            [Paragraph('<b>Total Amount in INR (Round off)</b>', label_style),Paragraph(f"₹{round_total:.2f}", value_style)],
        ]
        totals_table = Table(
            totals_rows,
            colWidths=[CONTENT_WIDTH * (4.5/6.5), CONTENT_WIDTH * (2.0/6.5)],
            hAlign='LEFT'
        )
        totals_table.setStyle(base_table_style())
        totals_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ]))
        return totals_table

    # ===== Helper function to build amount in words
    def build_amount_in_words():
        words_text = amount_in_words_inr(round_total)
        words_row = Table(
            [[Paragraph(f'<b>Total Amount In Words :</b> {words_text}', value_style)]],
            colWidths=[CONTENT_WIDTH],
            hAlign='LEFT'
        )
        words_row.setStyle(base_table_style())
        return words_row

    # ===== Helper function to build bank details
    def build_bank_details():
        bank_left_rows = [
            [Paragraph('<b>Bank Details</b>', label_style)],
            [Paragraph(f"Account Holder Name: {getattr(invoice, 'bank_account_holder_name', '')}", value_style)],
            [Paragraph(f"Account number: {invoice.bank_account_number}", value_style)],
            [Paragraph(f"Branch Name: {invoice.bank_branch_name}", value_style)],
            [Paragraph(f"Branch IFSC: {invoice.bank_branch_ifsc}", value_style)],
            [Paragraph(f"Branch Address: {invoice.bank_branch_address}", value_style)],
            [Paragraph(f"<b>PAN No:</b> {invoice.pan_number}", value_style)],
        ]
        bank_left_table = Table(
            bank_left_rows,
            colWidths=[CONTENT_WIDTH * (4.3/6.5)],
            hAlign='LEFT'
        )
        bank_left_table.setStyle(base_table_style())

        sign_rows = [
            [Paragraph('<b>For NITRA ENTERPRISES</b>', label_style)],
            [Spacer(1, 28)],
            [Spacer(1, 28)],
            [Paragraph('Authorised Signatory', value_style)],
        ]
        sign_table = Table(
            sign_rows,
            colWidths=[CONTENT_WIDTH * (2.2/6.5)],
            hAlign='CENTER'
        )
        sign_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0, colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (0, -1), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, -1), (-1, -1), 8),
        ]))

        bank_combo = Table(
            [[bank_left_table, sign_table]],
            colWidths=[CONTENT_WIDTH * (4.3/6.5), CONTENT_WIDTH * (2.2/6.5)],
            hAlign='LEFT'
        )
        bank_combo.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        return bank_combo

    # ===== Helper function to build declaration and jurisdiction
    def build_footer():
        dec_header = Table([[Paragraph('<b>Declaration</b>', label_style)]],
                           colWidths=[CONTENT_WIDTH], hAlign='LEFT')
        dec_header.setStyle(base_table_style())
        
        dec_table  = Table([[Paragraph(
            'We Declare that this invoice shows the actual price of the goods described and that all the particulars are the true and correct.',
            value_style)]], colWidths=[CONTENT_WIDTH], hAlign='LEFT')
        dec_table.setStyle(base_table_style())
        
        jur_table = Table([[Paragraph(f"<i>{invoice.jurisdiction_note}</i>", small_center)]],
                          colWidths=[CONTENT_WIDTH], hAlign='LEFT')
        jur_table.setStyle(base_table_style())
        
        return [dec_header, dec_table, jur_table]

    # ===== Build pages
    for page_num, page_items in enumerate(item_pages):
        is_first_page = (page_num == 0)
        is_last_page = (page_num == len(item_pages) - 1)

        # Page header
        story.append(build_header())
        
        # Page meta
        story.append(build_meta())
        story.append(Spacer(0, 4))

        # Additional info (only on first page)
        if is_first_page:
            additional = build_additional_info()
            if additional:
                story.append(additional)
                story.append(Spacer(0, 4))

            # Customer section (only on first page)
            story.append(build_customer_section())
            story.append(Spacer(0, 4))

        # Items for this page
        story.append(build_items_table(page_items))

        # Totals (only on last page)
        if is_last_page:
            story.append(build_totals_section())
            story.append(build_amount_in_words())
            story.append(Table([[Paragraph("", value_style)]], colWidths=[CONTENT_WIDTH], hAlign='LEFT').setStyle(base_table_style()))
            story.append(build_bank_details())
            
            # Footer (only on last page)
            for footer_item in build_footer():
                story.append(footer_item)
        else:
            # If not last page, add page break
            from reportlab.platypus import PageBreak
            story.append(PageBreak())

    doc.build(story)
    return str(pdf_path)

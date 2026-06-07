import sys
import os
from pathlib import Path
from typing import Optional, List
from fpdf import FPDF
import decimal

from .models import Invoice, ConfigManager


def _is_writable_dir(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        test_file = p / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        return True
    except (PermissionError, OSError):
        return False


def get_output_dir(custom_dir: str = "") -> Path:
    if custom_dir:
        p = Path(custom_dir)
        if _is_writable_dir(p):
            return p

    is_android = os.path.exists('/system/bin/am') or 'ANDROID_ROOT' in os.environ
    if is_android:
        for base in ['/storage/emulated/0', os.environ.get('EXTERNAL_STORAGE', ''), '/sdcard', '/storage/self/primary']:
            if not base:
                continue
            for sub in ['Download/Invoices', 'Invoices', 'Download']:
                p = Path(base) / sub
                if _is_writable_dir(p):
                    return p
        for env_var in ['FLET_APP_STORAGE_DATA', 'ANDROID_APP_DATA', 'XDG_DATA_HOME']:
            app_dir = os.environ.get(env_var, '')
            if app_dir:
                p = Path(app_dir) / 'Invoices'
                if _is_writable_dir(p):
                    return p
    else:
        home_dir = os.environ.get("HOME") or os.path.expanduser("~")
        if home_dir and home_dir != "~":
            p = Path(home_dir) / 'Invoices'
            if _is_writable_dir(p):
                return p

    import tempfile
    p = Path(tempfile.gettempdir()) / "Invoices"
    p.mkdir(parents=True, exist_ok=True)
    return p


def amount_in_words_inr(amount: float) -> str:
    ones = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    def two(n: int) -> str:
        if n < 20:
            return ones[n]
        t, u = divmod(n, 10)
        return tens[t] + ((" " + ones[u]) if u else "")
    rupees = int(round(amount))
    paise = int(round((amount - int(amount)) * 100))
    parts = []
    crore, rupees = divmod(rupees, 10000000)
    lakh, rupees = divmod(rupees, 100000)
    thousand, rupees = divmod(rupees, 1000)
    hundred, rupees = divmod(rupees, 100)
    if crore: parts.append(two(crore) + " Crore")
    if lakh: parts.append(two(lakh) + " Lakh")
    if thousand: parts.append(two(thousand) + " Thousand")
    if hundred: parts.append(ones[hundred] + " Hundred")
    if rupees: parts.append(two(rupees))
    words = " ".join(parts) if parts else "Zero"
    return f"Rupees {words} Only" if not paise else f"Rupees {words} and {paise} Paise Only"


class InvoicePDF(FPDF):
    def footer(self):
        pass


def generate_pdf(invoice: Invoice, logo_path: Optional[str] = None, output_dir: str = "") -> str:
    out = get_output_dir(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_invoice_number = invoice.invoice_number.replace('/', '-').replace('\\', '-').replace(':', '-').strip()
    pdf_filename = f"{safe_invoice_number}.pdf"
    pdf_path = out / pdf_filename

    subtotal = sum(it.total_price for it in invoice.line_items)
    sgst = sum(it.sgst_amount for it in invoice.line_items)
    cgst = sum(it.cgst_amount for it in invoice.line_items)
    sgst_eff = (sgst / subtotal * 100.0) if subtotal else 0.0
    cgst_eff = (cgst / subtotal * 100.0) if subtotal else 0.0
    total = subtotal + sgst + cgst
    round_total = float(decimal.Decimal(str(total)).quantize(decimal.Decimal('1'), rounding=decimal.ROUND_HALF_UP))

    pdf = InvoicePDF('P', 'mm', 'A4')
    pdf.set_margins(8, 8, 8)
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()
    page_w = pdf.w - 16
    rs = "₹ "

    font_family = "Arial"
    unicode_ok = False
    try:
        cfg_font = ConfigManager().get('font_path', '')
    except Exception:
        cfg_font = ''
    regular = Path(cfg_font) if cfg_font else Path(__file__).parent / "fonts" / "DejaVuSans.ttf"
    bold = Path(__file__).parent / "fonts" / "DejaVuSans-Bold.ttf"
    try:
        if regular.exists():
            pdf.add_font('DejaVu', '', str(regular), uni=True)
            if bold.exists():
                pdf.add_font('DejaVu', 'B', str(bold), uni=True)
            font_family = 'DejaVu'
            unicode_ok = True
    except Exception:
        font_family = "Arial"
        unicode_ok = False
        rs = "Rs. "

    def clean(t):
        s = "" if t is None else str(t)
        if unicode_ok:
            return s
        return s.encode('iso-8859-1', 'ignore').decode('iso-8859-1')
    def set_font(style='', size=9):
        try:
            pdf.set_font(font_family, style, size)
        except Exception:
            pdf.set_font('Arial', style, size)
    def fit_text(t: str, w: float, style='', size=8, min_size=6) -> str:
        t = clean(t)
        fs = size
        set_font(style, fs)
        while fs > min_size and pdf.get_string_width(t) > max(w - 1, 1):
            fs -= 0.5
            set_font(style, fs)
        return t
    def split_text(t: str, w: float, style='', size=8, max_lines=2) -> List[str]:
        t = clean(t).replace('\r', ' ').replace('\n', ' ')
        set_font(style, size)
        words = t.split()
        lines, cur = [], ""
        for word in words:
            test = word if not cur else cur + " " + word
            if pdf.get_string_width(test) <= w - 2:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = word
                if len(lines) >= max_lines:
                    break
        if cur and len(lines) < max_lines:
            lines.append(cur)
        return lines or [""]
    def label_value(x, y, label, value, label_w, value_w, size=8):
        pdf.set_xy(x, y)
        set_font('B', size)
        pdf.cell(label_w, 4, clean(label), align='L')
        set_font('', size)
        pdf.cell(value_w, 4, fit_text(value, value_w, '', size), align='L')

    x0 = 8
    y = 8

    # Header
    header_h = 22
    title_w = page_w * 0.76
    logo_w = page_w - title_w
    pdf.rect(x0, y, title_w, header_h)
    pdf.rect(x0 + title_w, y, logo_w, header_h)
    set_font('B', 14)
    pdf.set_xy(x0, y + 7)
    pdf.cell(title_w, 8, 'Tax Invoice', align='C')
    if logo_path and os.path.exists(logo_path):
        try:
            pdf.image(logo_path, x=x0 + title_w + 4, y=y + 3, w=logo_w - 8, h=16)
        except Exception:
            pass
    y += header_h

    # Company/meta section
    left_w = page_w / 2
    right_w = page_w / 2
    row_h = 5.7
    rows = [
        ('Company Name:', invoice.company_name, 'Invoice No:', invoice.invoice_number),
        ('ADDRESS:', invoice.company_address, 'Invoice Date:', invoice.invoice_date),
        ('GSTIN:', invoice.company_gstin, 'Po No:', invoice.po_number),
        ('Phone:', invoice.company_phone, 'Po Date:', invoice.po_date),
        ('Email:', invoice.company_email, 'Challan No:', invoice.challan_number),
        ('UDYAM REG NO:', invoice.udyam_registration, 'Challan Date:', invoice.challan_date),
    ]
    meta_h = row_h * len(rows)
    pdf.rect(x0, y, left_w, meta_h)
    pdf.rect(x0 + left_w, y, right_w, meta_h)
    for i, r in enumerate(rows):
        yy = y + i * row_h + 0.9
        label_value(x0 + 1, yy, r[0], r[1], 33, left_w - 36, 8)
        label_value(x0 + left_w + 1, yy, r[2], r[3], 31, right_w - 34, 8)
    y += meta_h + 2

    # Additional Info - full retained section
    line1 = getattr(invoice, 'additional_info_line1', '').strip()
    line2 = getattr(invoice, 'additional_info_line2', '').strip()
    if line1 or line2:
        add_h = 6 + (5 if line1 else 0) + (5 if line2 else 0)
        pdf.rect(x0, y, page_w, add_h)
        set_font('B', 8)
        pdf.set_xy(x0 + 1, y + 1)
        pdf.cell(page_w - 2, 4, 'Additional Information')
        set_font('', 8)
        yy = y + 6
        if line1:
            pdf.set_xy(x0 + 1, yy)
            pdf.cell(page_w - 2, 4, fit_text(line1, page_w - 2, '', 8))
            yy += 5
        if line2:
            pdf.set_xy(x0 + 1, yy)
            pdf.cell(page_w - 2, 4, fit_text(line2, page_w - 2, '', 8))
        y += add_h + 2

    # Invoice To / Ship To - aligned fixed label column
    cust_h = 30
    pdf.rect(x0, y, left_w, cust_h)
    pdf.rect(x0 + left_w, y, right_w, cust_h)
    set_font('B', 8)
    pdf.set_xy(x0 + 1, y + 1)
    pdf.cell(left_w - 2, 4, 'Invoice To')
    pdf.set_xy(x0 + left_w + 1, y + 1)
    pdf.cell(right_w - 2, 4, 'Ship To')
    cust_label_w = 28
    cust_value_w = left_w - cust_label_w - 3
    ship_value_w = right_w - cust_label_w - 3
    label_value(x0 + 1, y + 6, 'Name:', invoice.customer_name, cust_label_w, cust_value_w, 8)
    label_value(x0 + left_w + 1, y + 6, 'Name:', getattr(invoice, 'ship_to_name', ''), cust_label_w, ship_value_w, 8)
    label_value(x0 + 1, y + 11, 'Address:', '', cust_label_w, cust_value_w, 8)
    set_font('', 8)
    addr_lines = split_text(invoice.customer_address, cust_value_w, '', 8, 2)
    for i, line in enumerate(addr_lines[:2]):
        pdf.set_xy(x0 + 1 + cust_label_w, y + 11 + i * 4.5)
        pdf.cell(cust_value_w, 4, fit_text(line, cust_value_w, '', 8))
    label_value(x0 + left_w + 1, y + 11, 'Address:', '', cust_label_w, ship_value_w, 8)
    set_font('', 8)
    ship_lines = split_text(getattr(invoice, 'ship_to_address', ''), ship_value_w, '', 8, 2)
    for i, line in enumerate(ship_lines[:2]):
        pdf.set_xy(x0 + left_w + 1 + cust_label_w, y + 11 + i * 4.5)
        pdf.cell(ship_value_w, 4, fit_text(line, ship_value_w, '', 8))
    label_value(x0 + 1, y + 24, 'GSTIN:', invoice.customer_gstin, cust_label_w, cust_value_w, 8)
    label_value(x0 + left_w + 1, y + 24, 'GSTIN:', getattr(invoice, 'ship_to_gstin', ''), cust_label_w, ship_value_w, 8)
    y += cust_h + 2

    # Items table
    widths = [68, 27, 20, 20, 28, 31]
    headers = ['Description', 'HSN', 'Qty', 'UOM', 'Unit price', 'Total price']
    set_font('B', 8)
    pdf.set_text_color(0, 71, 171)
    pdf.set_xy(x0, y)
    for w, hdr in zip(widths, headers):
        pdf.cell(w, 7, hdr, border=1, align='C')
    pdf.ln()
    pdf.set_text_color(0, 0, 0)
    set_font('', 8)
    y = pdf.get_y()
    for it in invoice.line_items:
        pdf.set_xy(x0, y)
        vals = [it.description, it.hsn, f"{it.qty:.2f}", it.uom, f"{rs}{it.unit_price:.2f}", f"{rs}{it.total_price:.2f}"]
        aligns = ['L', 'R', 'R', 'R', 'R', 'R']
        for w, val, al in zip(widths, vals, aligns):
            pdf.cell(w, 6, fit_text(val, w, '', 8), border=1, align=al)
        y += 6
    pdf.set_y(y)

    # Totals
    label_w = sum(widths[:-1])
    val_w = widths[-1]
    totals = [
        ('Subtotal', subtotal),
        (f'SGST ({sgst_eff:.2f}%)', sgst),
        (f'CGST ({cgst_eff:.2f}%)', cgst),
        ('Total Amount in INR', total),
        ('Total Amount in INR (Round off)', round_total),
    ]
    set_font('B', 8)
    for lab, val in totals:
        pdf.set_x(x0)
        pdf.cell(label_w, 6, lab, border=1, align='L')
        pdf.cell(val_w, 6, f"{rs}{val:.2f}", border=1, align='R', ln=1)

    # Amount in words
    words_label_w = 50
    set_font('B', 8)
    pdf.set_x(x0)
    pdf.cell(words_label_w, 8, 'Total Amount In Words :', border=1, align='L')
    set_font('', 8)
    pdf.cell(page_w - words_label_w, 8, ' ' + clean(amount_in_words_inr(round_total)), border=1, align='L', ln=1)
    pdf.set_x(x0)
    pdf.cell(page_w, 6, '', border=1, ln=1)

    # Bank details + signatory - full retained section
    y = pdf.get_y()
    bank_w = page_w * 0.66
    sig_w = page_w - bank_w
    bank_h = 40
    pdf.rect(x0, y, bank_w, bank_h)
    pdf.rect(x0 + bank_w, y, sig_w, bank_h)
    set_font('B', 8)
    pdf.set_xy(x0 + 1, y + 1)
    pdf.cell(bank_w - 2, 4, 'Bank Details')
    bank_fields = [
        ('Account Holder Name:', getattr(invoice, 'bank_account_holder_name', '')),
        ('Account number:', invoice.bank_account_number),
        ('Branch Name:', invoice.bank_branch_name),
        ('Branch IFSC:', invoice.bank_branch_ifsc),
        ('Branch Address:', invoice.bank_branch_address),
        ('PAN No:', invoice.pan_number),
    ]
    labelw = 35
    yy = y + 7
    for lab, val in bank_fields:
        label_value(x0 + 1, yy, lab, val, labelw, bank_w - labelw - 3, 8)
        yy += 5
    set_font('B', 8)
    pdf.set_xy(x0 + bank_w, y + 1)
    pdf.cell(sig_w, 5, fit_text(f"For {invoice.company_name or 'Company'}", sig_w, 'B', 8), align='C')
    set_font('', 8)
    pdf.set_xy(x0 + bank_w, y + bank_h - 8)
    pdf.cell(sig_w, 5, 'Authorised Signatory', align='C')
    y += bank_h

    # Declaration - full retained section, one row + wraps if needed
    dec_h = 14
    pdf.rect(x0, y, page_w, dec_h)
    set_font('B', 8)
    pdf.set_xy(x0 + 1, y + 2)
    pdf.cell(23, 4, 'Declaration:')
    set_font('', 8)
    declaration = 'We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct.'
    lines = split_text(declaration, page_w - 27, '', 8, 2)
    for i, line in enumerate(lines):
        pdf.set_xy(x0 + 25, y + 2 + i * 5)
        pdf.cell(page_w - 27, 4, fit_text(line, page_w - 27, '', 8))
    y += dec_h

    # Jurisdiction footer
    set_font('I', 7)
    pdf.set_xy(x0, y)
    pdf.cell(page_w, 6, clean(invoice.jurisdiction_note), border=1, align='C')

    try:
        pdf.output(str(pdf_path))
    except (PermissionError, OSError):
        import tempfile
        fallback_dir = Path(tempfile.gettempdir()) / 'Invoices'
        fallback_dir.mkdir(parents=True, exist_ok=True)
        fallback_path = fallback_dir / pdf_filename
        pdf.output(str(fallback_path))
        pdf_path = fallback_path
    return str(pdf_path)

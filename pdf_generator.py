import sys
import os
from pathlib import Path
from typing import Optional, List, Tuple
from fpdf import FPDF
import decimal
import math

from .models import Invoice, ConfigManager


# -----------------------------
# Output directory helpers
# -----------------------------
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


# Backward compatibility for old PySide UI import.
OUTPUT_DIR = get_output_dir()


# -----------------------------
# Text and money helpers
# -----------------------------
def amount_in_words_inr(amount: float) -> str:
    ones = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def below_hundred(n: int) -> str:
        if n < 20:
            return ones[n]
        t, u = divmod(n, 10)
        return tens[t] + ((" " + ones[u]) if u else "")

    rupees = int(decimal.Decimal(str(amount)).quantize(decimal.Decimal('1'), rounding=decimal.ROUND_HALF_UP))
    paise = int(round((amount - int(amount)) * 100))
    parts = []
    crore, rupees = divmod(rupees, 10000000)
    lakh, rupees = divmod(rupees, 100000)
    thousand, rupees = divmod(rupees, 1000)
    hundred, rupees = divmod(rupees, 100)
    if crore:
        parts.append(below_hundred(crore) + " Crore")
    if lakh:
        parts.append(below_hundred(lakh) + " Lakh")
    if thousand:
        parts.append(below_hundred(thousand) + " Thousand")
    if hundred:
        parts.append(ones[hundred] + " Hundred")
    if rupees:
        parts.append(below_hundred(rupees))
    words = " ".join(parts) if parts else "Zero"
    return f"Rupees {words} Only" if not paise else f"Rupees {words} and {paise} Paise Only"


class InvoicePDF(FPDF):
    def footer(self):
        pass


def generate_pdf(invoice: Invoice, logo_path: Optional[str] = None, output_dir: str = "") -> str:
    """Generate invoice PDF with proper wrapping and dynamic row heights.

    Main fixes:
    - No fixed-height rows for long text.
    - Address, item description, bank address and declaration wrap correctly.
    - Page break before content would overflow.
    - Item table header repeats after page break.
    """
    out = get_output_dir(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe_invoice_number = (invoice.invoice_number or "invoice").replace('/', '-').replace('\\', '-').replace(':', '-').strip()
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
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()

    page_w = pdf.w - 16
    x0 = 8
    bottom_margin = 10
    usable_bottom = pdf.h - bottom_margin

    font_family = "Arial"
    unicode_ok = False
    rs = "Rs. "
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
            rs = "₹ "
    except Exception:
        font_family = "Arial"
        unicode_ok = False
        rs = "Rs. "

    def clean(t):
        s = "" if t is None else str(t)
        s = s.replace('\r\n', '\n').replace('\r', '\n').strip()
        if unicode_ok:
            return s
        return s.replace('₹', 'Rs.').encode('iso-8859-1', 'ignore').decode('iso-8859-1')

    def set_font(style='', size=9):
        try:
            pdf.set_font(font_family, style, size)
        except Exception:
            pdf.set_font('Arial', style, size)

    def money(v: float) -> str:
        return f"{rs}{v:.2f}"

    def ensure_space(height: float):
        if pdf.get_y() + height > usable_bottom:
            pdf.add_page()
            pdf.set_y(8)

    def wrap_lines(text: str, width: float, style='', size=8) -> List[str]:
        text = clean(text)
        set_font(style, size)
        lines = []
        for raw in (text.split('\n') or ['']):
            raw = raw.strip()
            if not raw:
                lines.append('')
                continue
            words = raw.split()
            cur = ''
            for word in words:
                test = word if not cur else cur + ' ' + word
                if pdf.get_string_width(test) <= max(width - 2, 1):
                    cur = test
                else:
                    if cur:
                        lines.append(cur)
                    # Hard-break extremely long words/SKU codes.
                    if pdf.get_string_width(word) > max(width - 2, 1):
                        chunk = ''
                        for ch in word:
                            test2 = chunk + ch
                            if pdf.get_string_width(test2) <= max(width - 2, 1):
                                chunk = test2
                            else:
                                if chunk:
                                    lines.append(chunk)
                                chunk = ch
                        cur = chunk
                    else:
                        cur = word
            if cur:
                lines.append(cur)
        return lines or ['']

    def cell_text(x, y, w, h, text, style='', size=8, align='L', valign='M', line_h=4.2):
        lines = wrap_lines(text, w, style, size)
        total_h = len(lines) * line_h
        if valign == 'M':
            yy = y + max((h - total_h) / 2, 1)
        else:
            yy = y + 1.5
        set_font(style, size)
        for line in lines:
            pdf.set_xy(x + 1.2, yy)
            pdf.cell(w - 2.4, line_h, line, align=align)
            yy += line_h

    def row_height(items: List[Tuple[str, float, str, int]], min_h=6.0, line_h=4.2, pad=3.2) -> float:
        mx = min_h
        for text, width, style, size in items:
            lines = wrap_lines(text, width, style, size)
            mx = max(mx, len(lines) * line_h + pad)
        return mx

    def draw_row(x, y, widths, values, aligns=None, styles=None, sizes=None, h=None, fill=False):
        aligns = aligns or ['L'] * len(values)
        styles = styles or [''] * len(values)
        sizes = sizes or [8] * len(values)
        if h is None:
            h = row_height([(v, w, st, sz) for v, w, st, sz in zip(values, widths, styles, sizes)])
        if fill:
            pdf.set_fill_color(238, 243, 248)
            pdf.rect(x, y, sum(widths), h, 'F')
        xx = x
        pdf.set_draw_color(90, 90, 90)
        for w, v, al, st, sz in zip(widths, values, aligns, styles, sizes):
            pdf.rect(xx, y, w, h)
            cell_text(xx, y, w, h, v, st, sz, al)
            xx += w
        return h

    def draw_label_value_rows(x, y, w, rows: List[Tuple[str, str]], title: str = '') -> float:
        label_w = min(34, w * 0.36)
        value_w = w - label_w
        cur_y = y
        if title:
            h = 6
            pdf.rect(x, cur_y, w, h)
            cell_text(x, cur_y, w, h, title, 'B', 8, 'L')
            cur_y += h
        for lab, val in rows:
            h = row_height([(lab, label_w, 'B', 8), (val, value_w, '', 8)], min_h=6, line_h=4.2, pad=3.4)
            pdf.rect(x, cur_y, label_w, h)
            pdf.rect(x + label_w, cur_y, value_w, h)
            cell_text(x, cur_y, label_w, h, lab, 'B', 8)
            cell_text(x + label_w, cur_y, value_w, h, val, '', 8)
            cur_y += h
        return cur_y - y

    def draw_two_blocks(left_title, left_rows, right_title, right_rows):
        left_w = page_w / 2
        right_w = page_w / 2
        # Calculate heights without drawing by using row_height.
        def calc_block_h(rows):
            label_w = min(34, left_w * 0.36)
            value_w = left_w - label_w
            total_hh = 6
            for lab, val in rows:
                total_hh += row_height([(lab, label_w, 'B', 8), (val, value_w, '', 8)], min_h=6, line_h=4.2, pad=3.4)
            return total_hh
        h = max(calc_block_h(left_rows), calc_block_h(right_rows))
        ensure_space(h)
        y = pdf.get_y()
        pdf.rect(x0, y, left_w, h)
        pdf.rect(x0 + left_w, y, right_w, h)
        lh = draw_label_value_rows(x0, y, left_w, left_rows, left_title)
        rh = draw_label_value_rows(x0 + left_w, y, right_w, right_rows, right_title)
        pdf.set_y(y + h)

    def draw_items_header():
        widths = [68, 27, 20, 20, 28, 31]
        headers = ['Description', 'HSN', 'Qty', 'UOM', 'Unit price', 'Total price']
        ensure_space(7)
        y = pdf.get_y()
        draw_row(x0, y, widths, headers, aligns=['C']*6, styles=['B']*6, sizes=[8]*6, h=7, fill=True)
        pdf.set_y(y + 7)
        return widths

    # Header
    pdf.set_y(8)
    header_h = 22
    title_w = page_w * 0.76
    logo_w = page_w - title_w
    ensure_space(header_h)
    y = pdf.get_y()
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
    pdf.set_y(y + header_h)

    # Company/meta section - now dynamic height and wrapped.
    left_rows = [
        ('Company Name:', invoice.company_name),
        ('ADDRESS:', invoice.company_address),
        ('GSTIN:', invoice.company_gstin),
        ('Phone:', invoice.company_phone),
        ('Email:', invoice.company_email),
        ('UDYAM REG NO:', invoice.udyam_registration),
    ]
    right_rows = [
        ('Invoice No:', invoice.invoice_number),
        ('Invoice Date:', invoice.invoice_date),
        ('Po No:', invoice.po_number),
        ('Po Date:', invoice.po_date),
        ('Challan No:', invoice.challan_number),
        ('Challan Date:', invoice.challan_date),
    ]
    draw_two_blocks('', left_rows, '', right_rows)
    pdf.ln(2)

    # Additional info.
    line1 = getattr(invoice, 'additional_info_line1', '').strip()
    line2 = getattr(invoice, 'additional_info_line2', '').strip()
    if line1 or line2:
        rows = [('Additional Information:', '\n'.join([x for x in [line1, line2] if x]))]
        h = draw_label_value_rows(x0, pdf.get_y(), page_w, rows, '')
        pdf.set_y(pdf.get_y() + h + 2)

    # Invoice To / Ship To - dynamically wrapped.
    bill_rows = [
        ('Name:', invoice.customer_name),
        ('Address:', invoice.customer_address),
        ('GSTIN:', invoice.customer_gstin),
    ]
    ship_rows = [
        ('Name:', getattr(invoice, 'ship_to_name', '')),
        ('Address:', getattr(invoice, 'ship_to_address', '')),
        ('GSTIN:', getattr(invoice, 'ship_to_gstin', '')),
    ]
    draw_two_blocks('Invoice To', bill_rows, 'Ship To', ship_rows)
    pdf.ln(2)

    # Items table - row height expands for description.
    widths = draw_items_header()
    for it in invoice.line_items:
        vals = [
            it.description,
            it.hsn,
            f"{it.qty:.2f}",
            it.uom,
            money(it.unit_price),
            money(it.total_price),
        ]
        aligns = ['L', 'R', 'R', 'R', 'R', 'R']
        h = row_height([(vals[i], widths[i], '', 8) for i in range(len(vals))], min_h=7, line_h=4.2, pad=3.6)
        if pdf.get_y() + h > usable_bottom:
            pdf.add_page()
            pdf.set_y(8)
            widths = draw_items_header()
        y = pdf.get_y()
        draw_row(x0, y, widths, vals, aligns=aligns, sizes=[8]*6, h=h)
        pdf.set_y(y + h)

    # Totals.
    label_w = sum(widths[:-1])
    val_w = widths[-1]
    totals = [
        ('Subtotal', subtotal),
        (f'SGST ({sgst_eff:.2f}%)', sgst),
        (f'CGST ({cgst_eff:.2f}%)', cgst),
        ('Total Amount in INR', total),
        ('Total Amount in INR (Round off)', round_total),
    ]
    for lab, val in totals:
        ensure_space(6)
        y = pdf.get_y()
        draw_row(x0, y, [label_w, val_w], [lab, money(val)], aligns=['L', 'R'], styles=['B', 'B'], sizes=[8, 8], h=6)
        pdf.set_y(y + 6)

    # Amount in words.
    words = amount_in_words_inr(round_total)
    words_label_w = 50
    h = row_height([('Total Amount In Words :', words_label_w, 'B', 8), (words, page_w - words_label_w, '', 8)], min_h=8, line_h=4.2, pad=3.6)
    ensure_space(h)
    y = pdf.get_y()
    draw_row(x0, y, [words_label_w, page_w - words_label_w], ['Total Amount In Words :', words], styles=['B', ''], sizes=[8, 8], h=h)
    pdf.set_y(y + h + 2)

    # Bank and sign section.
    bank_w = page_w * 0.66
    sig_w = page_w - bank_w
    bank_rows = [
        ('Account Holder Name:', getattr(invoice, 'bank_account_holder_name', '')),
        ('Account number:', invoice.bank_account_number),
        ('Branch Name:', invoice.bank_branch_name),
        ('Branch IFSC:', invoice.bank_branch_ifsc),
        ('Branch Address:', invoice.bank_branch_address),
        ('PAN No:', invoice.pan_number),
    ]
    # Calculate bank block height using the same sizing as draw_label_value_rows.
    label_w = min(34, bank_w * 0.36)
    value_w = bank_w - label_w
    bank_h = 6 + sum(
        row_height([(lab, label_w, 'B', 8), (val, value_w, '', 8)], min_h=6, line_h=4.2, pad=3.4)
        for lab, val in bank_rows
    )
    bank_h = max(bank_h, 38)
    ensure_space(bank_h)
    y = pdf.get_y()
    pdf.rect(x0, y, bank_w, bank_h)
    pdf.rect(x0 + bank_w, y, sig_w, bank_h)
    draw_label_value_rows(x0, y, bank_w, bank_rows, 'Bank Details')
    cell_text(x0 + bank_w, y, sig_w, 8, f"For {invoice.company_name or 'Company'}", 'B', 8, 'C')
    cell_text(x0 + bank_w, y + bank_h - 10, sig_w, 8, 'Authorised Signatory', '', 8, 'C')
    pdf.set_y(y + bank_h)

    # Declaration.
    declaration = 'We declare that this invoice shows the actual price of the goods described and that all particulars are true and correct.'
    dec_label_w = 26
    h = row_height([('Declaration:', dec_label_w, 'B', 8), (declaration, page_w - dec_label_w, '', 8)], min_h=12, line_h=4.0, pad=3.5)
    ensure_space(h + 6)
    y = pdf.get_y()
    draw_row(x0, y, [dec_label_w, page_w - dec_label_w], ['Declaration:', declaration], styles=['B', ''], sizes=[8, 8], h=h)
    pdf.set_y(y + h)

    # Jurisdiction footer.
    ensure_space(6)
    y = pdf.get_y()
    draw_row(x0, y, [page_w], [clean(invoice.jurisdiction_note)], aligns=['C'], styles=['I'], sizes=[7], h=6)

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

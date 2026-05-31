import sys
import os
from pathlib import Path
from typing import Optional
from fpdf import FPDF
import decimal

from .models import Invoice, ConfigManager

def get_output_dir():
    if hasattr(sys, '_MEIPASS'):
        return Path(sys.executable).parent / "data" / "invoices"
    
    local_dir = Path(__file__).parent.parent / "data" / "invoices"
    try:
        local_dir.mkdir(parents=True, exist_ok=True)
        return local_dir
    except (PermissionError, OSError):
        pass
        
    home_dir = os.environ.get("HOME")
    if home_dir:
        try:
            android_dir = Path(home_dir) / "invoices"
            android_dir.mkdir(parents=True, exist_ok=True)
            return android_dir
        except (PermissionError, OSError):
            pass
            
    import tempfile
    return Path(tempfile.gettempdir()) / "invoices"

OUTPUT_DIR = get_output_dir()

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

class InvoicePDF(FPDF):
    def footer(self):
        # We handle footers explicitly in the generation loop, so pass
        pass

def generate_pdf(invoice: Invoice, logo_path: Optional[str] = None) -> str:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    safe_invoice_number = (
        invoice.invoice_number.replace('/', '-').replace('\\', '-').replace(':', '-')
    )
    pdf_filename = f"{safe_invoice_number}.pdf"
    pdf_path = OUTPUT_DIR / pdf_filename

    # Replace ₹ with Rs. since fpdf core fonts are iso-8859-1
    rs = "Rs."

    # Subtotals
    subtotal    = sum(it.total_price for it in invoice.line_items)
    sgst        = sum(it.sgst_amount for it in invoice.line_items)
    cgst        = sum(it.cgst_amount for it in invoice.line_items)
    sgst_eff    = (sgst / subtotal * 100.0) if subtotal else 0.0
    cgst_eff    = (cgst / subtotal * 100.0) if subtotal else 0.0
    total       = subtotal + sgst + cgst
    round_total = float(decimal.Decimal(str(total)).quantize(decimal.Decimal('1'), rounding=decimal.ROUND_HALF_UP))

    pdf = InvoicePDF('P', 'mm', 'A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(8, 8, 8)
    
    page_w = pdf.w - 16  # total page width minus 8mm left and right margins

    def txt(t):
        if not t: return ""
        # Filter unprintable characters if any
        return str(t).encode('iso-8859-1', 'ignore').decode('iso-8859-1')

    # Draw header
    pdf.set_font('Arial', 'B', 14)
    # Tax Invoice text
    pdf.cell(page_w * 0.75, 10, 'Tax Invoice', border=1, align='C')
    # Logo Box
    x_logo_box = pdf.get_x()
    y_logo_box = pdf.get_y()
    pdf.cell(page_w * 0.25, 10, '', border=1, ln=1, align='C')
    
    if logo_path and os.path.exists(logo_path):
        try:
            # fpdf handles jpg, png natively
            pdf.image(logo_path, x=x_logo_box + 2, y=y_logo_box + 1, w=page_w * 0.25 - 4, h=8)
        except Exception:
            pass

    # Meta
    # Two columns:
    col1_w = page_w / 2
    col2_w = page_w / 2
    
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(28, 6, "Company Name:", border="L")
    pdf.set_font('Arial', '', 9)
    pdf.cell(col1_w - 28, 6, txt(invoice.company_name))
    
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(28, 6, "Invoice No:", border="L")
    pdf.set_font('Arial', '', 9)
    pdf.cell(col2_w - 28, 6, txt(invoice.invoice_number), border="R", ln=1)
    
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(28, 6, "ADDRESS:", border="L")
    pdf.set_font('Arial', '', 9)
    pdf.cell(col1_w - 28, 6, txt(invoice.company_address))
    
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(28, 6, "Invoice Date:", border="L")
    pdf.set_font('Arial', '', 9)
    pdf.cell(col2_w - 28, 6, txt(invoice.invoice_date), border="R", ln=1)

    left_labels = ['GSTIN:', 'Phone:', 'Email:', 'UDYAM REG NO:']
    left_values = [invoice.company_gstin, invoice.company_phone, invoice.company_email, invoice.udyam_registration]
    
    right_fields = []
    if invoice.po_number: right_fields.append(('Po No:', invoice.po_number))
    if invoice.po_date: right_fields.append(('Po Date:', invoice.po_date))
    if invoice.challan_number: right_fields.append(('Challan No:', invoice.challan_number))
    if invoice.challan_date: right_fields.append(('Challan Date:', invoice.challan_date))

    for i in range(len(left_labels)):
        pdf.set_font('Arial', 'B', 9)
        # We give a fixed width to label, then rest to value
        pdf.cell(30, 6, left_labels[i], border="L")
        pdf.set_font('Arial', '', 9)
        pdf.cell(col1_w - 30, 6, txt(left_values[i]))
        
        pdf.set_font('Arial', 'B', 9)
        if i < len(right_fields):
            pdf.cell(30, 6, right_fields[i][0], border="L")
            pdf.set_font('Arial', '', 9)
            pdf.cell(col2_w - 30, 6, txt(right_fields[i][1]), border="R", ln=1)
        else:
            pdf.cell(30, 6, "", border="L")
            pdf.cell(col2_w - 30, 6, "", border="R", ln=1)
    
    # Close border of meta box
    pdf.cell(page_w, 0, "", border="T", ln=1)
    
    # Space
    pdf.ln(2)
    
    # Additional Info
    line1 = getattr(invoice, 'additional_info_line1', '').strip()
    line2 = getattr(invoice, 'additional_info_line2', '').strip()
    if line1 or line2:
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(page_w, 6, "Additional Information", border="LRT", ln=1)
        pdf.set_font('Arial', '', 9)
        if line1:
            pdf.cell(page_w, 6, txt(line1), border="LR", ln=1)
        if line2:
            pdf.cell(page_w, 6, txt(line2), border="LR", ln=1)
        pdf.cell(page_w, 0, "", border="T", ln=1)
        pdf.ln(2)

    # Customer Section
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(col1_w, 6, "Invoice To", border="LRT")
    pdf.cell(col2_w, 6, "Ship To", border="LRT", ln=1)
    
    pdf.set_font('Arial', '', 9)
    inv_name = txt(invoice.customer_name)
    ship_name = txt(getattr(invoice, 'ship_to_name', ''))
    pdf.cell(col1_w, 6, inv_name, border="LR")
    pdf.cell(col2_w, 6, ship_name, border="LR", ln=1)
    
    inv_addr = txt(invoice.customer_address)
    ship_addr = txt(getattr(invoice, 'ship_to_address', ''))
    pdf.cell(col1_w, 6, inv_addr, border="LR")
    pdf.cell(col2_w, 6, ship_addr, border="LR", ln=1)

    inv_gstin = txt(f"GSTIN: {invoice.customer_gstin or ''}")
    ship_gstin = txt(f"GSTIN: {getattr(invoice, 'ship_to_gstin', '') or ''}")
    pdf.cell(col1_w, 6, inv_gstin, border="LRB")
    pdf.cell(col2_w, 6, ship_gstin, border="LRB", ln=1)
    pdf.ln(2)

    # Items table header
    pdf.set_fill_color(255, 255, 255)
    pdf.set_text_color(0, 71, 171) # BLUE
    pdf.set_font('Arial', 'B', 9)
    
    w_desc = page_w * (2.30/6.5)
    w_hsn = page_w * (0.90/6.5)
    w_qty = page_w * (0.70/6.5)
    w_uom = page_w * (0.70/6.5)
    w_unit = page_w * (0.95/6.5)
    w_tot = page_w * (0.95/6.5)

    pdf.cell(w_desc, 8, "Description", border=1, align='C', fill=True)
    pdf.cell(w_hsn, 8, "HSN", border=1, align='C', fill=True)
    pdf.cell(w_qty, 8, "Qty", border=1, align='C', fill=True)
    pdf.cell(w_uom, 8, "UOM", border=1, align='C', fill=True)
    pdf.cell(w_unit, 8, "Unit price", border=1, align='C', fill=True)
    pdf.cell(w_tot, 8, "Total price", border=1, align='C', fill=True, ln=1)

    # Items
    pdf.set_text_color(0, 0, 0)
    pdf.set_font('Arial', '', 9)
    for it in invoice.line_items:
        pdf.cell(w_desc, 6, txt(it.description), border="LR")
        pdf.cell(w_hsn, 6, txt(it.hsn), border="LR", align="R")
        pdf.cell(w_qty, 6, f"{it.qty:.2f}", border="LR", align="R")
        pdf.cell(w_uom, 6, txt(it.uom), border="LR", align="R")
        pdf.cell(w_unit, 6, f"{rs}{it.unit_price:.2f}", border="LR", align="R")
        pdf.cell(w_tot, 6, f"{rs}{it.total_price:.2f}", border="LR", align="R", ln=1)
    
    # Close items table bottom border
    pdf.cell(page_w, 0, "", border="T", ln=1)
    
    # Totals
    w_tot_label = page_w * (4.5/6.5)
    w_tot_val = page_w * (2.0/6.5)

    pdf.set_font('Arial', 'B', 9)
    pdf.cell(w_tot_label, 6, "Subtotal", border="LRT")
    pdf.cell(w_tot_val, 6, f"{rs}{subtotal:.2f}", border="LRT", align="R", ln=1)
    
    pdf.cell(w_tot_label, 6, f"SGST ({sgst_eff:.2f}%)", border="LR")
    pdf.cell(w_tot_val, 6, f"{rs}{sgst:.2f}", border="LR", align="R", ln=1)
    
    pdf.cell(w_tot_label, 6, f"CGST ({cgst_eff:.2f}%)", border="LR")
    pdf.cell(w_tot_val, 6, f"{rs}{cgst:.2f}", border="LR", align="R", ln=1)
    
    pdf.cell(w_tot_label, 6, "Total Amount in INR", border="LR")
    pdf.cell(w_tot_val, 6, f"{rs}{total:.2f}", border="LR", align="R", ln=1)
    
    pdf.cell(w_tot_label, 6, "Total Amount in INR (Round off)", border="LRB")
    pdf.cell(w_tot_val, 6, f"{rs}{round_total:.2f}", border="LRB", align="R", ln=1)

    # Amount in words
    words_text = txt(amount_in_words_inr(round_total))
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(40, 8, "Total Amount In Words :", border="LBT")
    pdf.set_font('Arial', '', 9)
    pdf.cell(page_w - 40, 8, words_text, border="RBT", ln=1)
    pdf.cell(page_w, 6, "", border="LRBT", ln=1)
    
    # Bank Details + Signatory
    b_left_w = page_w * 4.3/6.5
    b_right_w = page_w * 2.2/6.5

    x_start = pdf.get_x()
    y_start = pdf.get_y()

    # Draw bank details text
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(b_left_w, 6, "Bank Details", border="LRT", ln=2)
    pdf.set_font('Arial', '', 9)
    pdf.cell(b_left_w, 6, txt(f"Account Holder Name: {getattr(invoice, 'bank_account_holder_name', '')}"), border="LR", ln=2)
    pdf.cell(b_left_w, 6, txt(f"Account number: {invoice.bank_account_number}"), border="LR", ln=2)
    pdf.cell(b_left_w, 6, txt(f"Branch Name: {invoice.bank_branch_name}"), border="LR", ln=2)
    pdf.cell(b_left_w, 6, txt(f"Branch IFSC: {invoice.bank_branch_ifsc}"), border="LR", ln=2)
    pdf.cell(b_left_w, 6, txt(f"Branch Address: {invoice.bank_branch_address}"), border="LR", ln=2)
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(b_left_w, 6, txt(f"PAN No: {invoice.pan_number}"), border="LRB")
    
    # Move to right col for signatory
    y_end = pdf.get_y()
    pdf.set_xy(x_start + b_left_w, y_start)
    
    # Draw right column (signatory) bounding box
    pdf.cell(b_right_w, 6, "For NITRA ENTERPRISES", border="LRT", align="C", ln=2)
    # The height left is (y_end - y_start) - 6 + 6
    h_left = (y_end - y_start) - 12
    if h_left < 0: h_left = 12
    pdf.cell(b_right_w, h_left, "", border="LR", ln=2)
    pdf.set_font('Arial', '', 9)
    pdf.cell(b_right_w, 6, "Authorised Signatory", border="LRB", align="C")

    # Reset position
    pdf.set_xy(x_start, y_end + 6)
    
    # Footer
    pdf.set_font('Arial', 'B', 9)
    pdf.cell(page_w, 6, "Declaration", border="LRT", ln=1)
    pdf.set_font('Arial', '', 9)
    pdf.cell(page_w, 6, "We Declare that this invoice shows the actual price of the goods described", border="LR", ln=1)
    pdf.cell(page_w, 6, "and that all the particulars are the true and correct.", border="LRB", ln=1)
    
    pdf.set_font('Arial', 'I', 8)
    pdf.cell(page_w, 6, txt(invoice.jurisdiction_note), border=1, align="C", ln=1)

    pdf.output(str(pdf_path))
    return str(pdf_path)

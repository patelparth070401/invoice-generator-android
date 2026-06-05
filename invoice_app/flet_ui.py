import flet as ft
from invoice_app.models import Invoice, LineItem, InvoiceDB, ConfigManager
from invoice_app.pdf_generator import generate_pdf
import os
import subprocess
import traceback
import datetime
import urllib.parse


def _is_android() -> bool:
    """Check if running on Android."""
    return os.path.exists('/system/bin/am') or 'ANDROID_ROOT' in os.environ


def _am_start(args: list) -> bool:
    """Run 'am start' on Android. Returns True on success."""
    try:
        am = '/system/bin/am' if os.path.exists('/system/bin/am') else 'am'
        subprocess.Popen([am, 'start'] + args,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def _is_writable_dir(d: str) -> bool:
    """Check if a directory is actually writable by creating a temporary file."""
    try:
        os.makedirs(d, exist_ok=True)
        test_file = os.path.join(d, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.unlink(test_file)
        return True
    except (PermissionError, OSError):
        return False


def _default_pdf_dir() -> str:
    """Return a sensible default PDF directory."""
    for base in [
        os.environ.get('EXTERNAL_STORAGE', ''),
        '/storage/emulated/0',
        '/sdcard',
    ]:
        if base and os.path.isdir(base):
            d = os.path.join(base, 'Invoices')
            if _is_writable_dir(d):
                return d
    # App-private storage on Android (accessible without special permissions)
    for env_var in ['FLET_APP_STORAGE_DATA', 'ANDROID_APP_DATA', 'XDG_DATA_HOME']:
        app_dir = os.environ.get(env_var, '')
        if app_dir:
            d = os.path.join(app_dir, 'Invoices')
            if _is_writable_dir(d):
                return d
    home = os.environ.get("HOME") or os.path.expanduser("~")
    if home and home != "~":
        d = os.path.join(home, "Invoices")
        if _is_writable_dir(d):
            return d
    import tempfile
    d = os.path.join(tempfile.gettempdir(), "Invoices")
    os.makedirs(d, exist_ok=True)
    return d

def main(page: ft.Page):
    try:
        page.title = "Invoice Generator"
        page.theme_mode = ft.ThemeMode.LIGHT
        page.padding = 10

        db = InvoiceDB()
        config = ConfigManager()
        
        # Try to load logo
        logo_path = config.get('logo_path', '')
        if not logo_path or not os.path.exists(logo_path):
            bundled_logo = os.path.join(os.path.dirname(__file__), 'logo.png')
            if os.path.exists(bundled_logo):
                logo_path = bundled_logo
    except Exception as e:
        page.add(ft.SafeArea(ft.Text(f"ERROR INIT: {e}\n{traceback.format_exc()}", color="red", selectable=True)))
        return
        
    try:
        # ---------------------------------------------------------
        # SETTINGS TAB FIELDS
        # ---------------------------------------------------------
        company_name = ft.TextField(label="Company Name", value=config.get('company_name', ''))
        company_address = ft.TextField(label="Address", value=config.get('company_address', ''), multiline=True)
        company_gstin = ft.TextField(label="GSTIN", value=config.get('company_gstin', ''))
        company_phone = ft.TextField(label="Phone", value=config.get('company_phone', ''))
        company_email = ft.TextField(label="Email", value=config.get('company_email', ''))
        pan_number = ft.TextField(label="PAN No", value=config.get('pan_number', ''))
        
        bank_acc_name = ft.TextField(label="Account Holder Name", value=config.get('bank_account_holder_name', ''))
        bank_acc_no = ft.TextField(label="Account No", value=config.get('bank_account_number', ''))
        bank_branch = ft.TextField(label="Branch Name", value=config.get('bank_branch_name', ''))
        bank_ifsc = ft.TextField(label="Branch IFSC", value=config.get('bank_branch_ifsc', ''))
        invoice_start_number = ft.TextField(
            label="Invoice Start Number",
            value=str(config.get('invoice_start_number', 32)),
            keyboard_type=ft.KeyboardType.NUMBER
        )
        pdf_dir_field = ft.TextField(
            label="PDF Save Folder",
            value=config.get('pdf_output_dir', ''),
            hint_text="Leave blank to use /sdcard/Invoices (default)",
            expand=True,
            read_only=False,
        )

        # FilePicker for choosing PDF save directory
        def on_dir_result(e: ft.FilePickerResultEvent):
            if e.path:
                pdf_dir_field.value = e.path
                pdf_dir_field.update()

        dir_picker = ft.FilePicker(on_result=on_dir_result)
        page.overlay.append(dir_picker)

        def save_settings(e):
            config.set('company_name', company_name.value)
            config.set('company_address', company_address.value)
            config.set('company_gstin', company_gstin.value)
            config.set('company_phone', company_phone.value)
            config.set('company_email', company_email.value)
            config.set('pan_number', pan_number.value)
            config.set('bank_account_holder_name', bank_acc_name.value)
            config.set('bank_account_number', bank_acc_no.value)
            config.set('bank_branch_name', bank_branch.value)
            config.set('bank_branch_ifsc', bank_ifsc.value)
            config.set('pdf_output_dir', pdf_dir_field.value)
            try:
                config.set('invoice_start_number', int(invoice_start_number.value))
            except ValueError:
                pass
            try:
                config.save()
                page.snack_bar = ft.SnackBar(ft.Text("Settings saved successfully!"))
            except Exception as ex:
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"Error saving settings: {ex}", color=ft.colors.WHITE),
                    bgcolor=ft.colors.RED
                )
            page.snack_bar.open = True
            page.update()

        settings_tab = ft.Tab(
            text="Settings",
            icon=ft.icons.SETTINGS,
            content=ft.ListView(
                expand=True,
                spacing=10,
                padding=10,
                controls=[
                    ft.Text("Company Details", size=18, weight=ft.FontWeight.BOLD),
                    company_name, company_address, company_gstin, pan_number, company_phone, company_email,
                    ft.Divider(),
                    ft.Text("Bank Details", size=18, weight=ft.FontWeight.BOLD),
                    bank_acc_name, bank_acc_no, bank_branch, bank_ifsc,
                    ft.Divider(),
                    ft.Text("Invoice Series", size=18, weight=ft.FontWeight.BOLD),
                    invoice_start_number,
                    ft.Divider(),
                    ft.Text("PDF Save Folder", size=18, weight=ft.FontWeight.BOLD),
                    ft.Row([
                        pdf_dir_field,
                        ft.ElevatedButton(
                            "Browse",
                            icon=ft.icons.FOLDER_OPEN,
                            on_click=lambda e: dir_picker.get_directory_path(dialog_title="Choose PDF Save Folder"),
                        )
                    ]),
                    ft.Divider(),
                    ft.ElevatedButton("Save Settings", on_click=save_settings, color=ft.colors.WHITE, bgcolor=ft.colors.GREEN)
                ]
            )
        )

        # ---------------------------------------------------------
        # CREATE INVOICE TAB FIELDS
        # ---------------------------------------------------------
        invoice_number = ft.TextField(label="Invoice Number")
        invoice_date = ft.TextField(label="Invoice Date (dd-mm-yyyy)")
        po_number = ft.TextField(label="PO Number")
        po_date = ft.TextField(label="PO Date (dd-mm-yyyy)")
        challan_number = ft.TextField(label="Challan Number")
        challan_date = ft.TextField(label="Challan Date (dd-mm-yyyy)")

        # Date pickers
        def _make_date_picker(target_field):
            dp = ft.DatePicker(
                first_date=datetime.datetime(2020, 1, 1),
                last_date=datetime.datetime(2030, 12, 31),
            )
            def on_change(e, tf=target_field, picker=dp):
                if picker.value:
                    tf.value = picker.value.strftime("%d-%m-%Y")
                    tf.update()
            dp.on_change = on_change
            page.overlay.append(dp)
            return dp

        dp_invoice_date = _make_date_picker(invoice_date)
        dp_po_date = _make_date_picker(po_date)
        dp_challan_date = _make_date_picker(challan_date)

        def _date_row(label_field, dp):
            def open_picker(e, picker=dp):
                picker.open = True
                page.update()
            return ft.Row([
                ft.Container(content=label_field, expand=True),
                ft.IconButton(icon=ft.icons.CALENDAR_TODAY, tooltip="Pick date", on_click=open_picker)
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
        
        # Customer Suggestions Dropdown
        customer_dropdown = ft.Dropdown(label="Select Existing Customer...", options=[])
        
        customer_name = ft.TextField(label="Invoice To Name")
        customer_address = ft.TextField(label="Invoice To Address", multiline=True)
        customer_gstin = ft.TextField(label="Invoice To GSTIN")
        
        ship_to_name = ft.TextField(label="Ship To Name")
        ship_to_address = ft.TextField(label="Ship To Address", multiline=True)
        ship_to_gstin = ft.TextField(label="Ship To GSTIN")
        
        def populate_customer_dropdown():
            customers = db.get_unique_customers()
            options = [ft.dropdown.Option(name) for name in sorted(customers.keys())]
            customer_dropdown.options = options
            
        def on_customer_select(e):
            if not customer_dropdown.value: return
            customers = db.get_unique_customers()
            data = customers.get(customer_dropdown.value, {})
            customer_name.value = customer_dropdown.value
            customer_address.value = data.get('address', '')
            customer_gstin.value = data.get('gstin', '')
            ship_to_name.value = data.get('ship_to_name', '')
            ship_to_address.value = data.get('ship_to_address', '')
            ship_to_gstin.value = data.get('ship_to_gstin', '')
            page.update()
            
        customer_dropdown.on_change = on_customer_select

        line_items = []
        
        lbl_subtotal = ft.Text("Subtotal: Rs. 0.00", weight=ft.FontWeight.BOLD)
        lbl_tax = ft.Text("Tax (SGST+CGST): Rs. 0.00", weight=ft.FontWeight.BOLD)
        lbl_total = ft.Text("Total: Rs. 0.00", weight=ft.FontWeight.BOLD, size=20, color=ft.colors.BLUE)

        def update_totals():
            subtotal = sum(i.total_price for i in line_items)
            sgst = sum(i.sgst_amount for i in line_items)
            cgst = sum(i.cgst_amount for i in line_items)
            total = subtotal + sgst + cgst
            lbl_subtotal.value = f"Subtotal: Rs. {subtotal:.2f}"
            lbl_tax.value = f"Tax (SGST+CGST): Rs. {sgst+cgst:.2f}"
            lbl_total.value = f"Total: Rs. {total:.2f}"
            page.update()

        def remove_item(idx):
            if 0 <= idx < len(line_items):
                line_items.pop(idx)
                refresh_items_list()

        items_column = ft.Column(spacing=5)

        def refresh_items_list():
            items_column.controls.clear()
            for i, item in enumerate(line_items):
                items_column.controls.append(
                    ft.Card(
                        content=ft.Container(
                            padding=10,
                            content=ft.Row([
                                ft.Column([
                                    ft.Text(item.description, weight=ft.FontWeight.BOLD),
                                    ft.Text(f"Qty: {item.qty} | Price: Rs. {item.unit_price} | Total: Rs. {item.total_price}")
                                ], expand=True),
                                ft.IconButton(icon=ft.icons.DELETE, icon_color="red", on_click=lambda e, idx=i: remove_item(idx))
                            ])
                        )
                    )
                )
            if not line_items:
                items_column.controls.append(ft.Text("No items added.", italic=True, color="grey"))
            
            update_totals()
            page.update()

        add_desc = ft.TextField(label="Description")
        add_hsn = ft.TextField(label="HSN")
        add_qty = ft.TextField(label="Qty", value="1")
        add_price = ft.TextField(label="Unit Price", value="0.0")
        add_sgst = ft.TextField(label="SGST %", value="9")
        add_cgst = ft.TextField(label="CGST %", value="9")

        def dlg_add_item_click(e):
            try:
                item = LineItem(
                    description=add_desc.value,
                    hsn=add_hsn.value,
                    qty=float(add_qty.value),
                    uom="NOS",
                    unit_price=float(add_price.value),
                    sgst_rate=float(add_sgst.value),
                    cgst_rate=float(add_cgst.value)
                )
                line_items.append(item)
                refresh_items_list()
                add_item_dialog.open = False
                page.update()
            except ValueError:
                pass 

        add_item_dialog = ft.AlertDialog(
            title=ft.Text("Add Line Item"),
            content=ft.Column([
                add_desc, add_hsn, add_qty, add_price, add_sgst, add_cgst
            ], scroll=ft.ScrollMode.AUTO, height=400),
            actions=[
                ft.TextButton("Add", on_click=dlg_add_item_click),
                ft.TextButton("Cancel", on_click=lambda e: setattr(add_item_dialog, 'open', False) or page.update())
            ],
        )

        def open_add_dialog(e):
            page.dialog = add_item_dialog
            add_item_dialog.open = True
            page.update()

        def generate_pdf_action(e):
            try:
                inv = Invoice(
                    invoice_number=invoice_number.value,
                    invoice_date=invoice_date.value,
                    po_number=po_number.value,
                    po_date=po_date.value,
                    challan_number=challan_number.value,
                    challan_date=challan_date.value,
                    company_name=company_name.value,
                    company_address=company_address.value,
                    company_gstin=company_gstin.value,
                    company_phone=company_phone.value,
                    company_email=company_email.value,
                    pan_number=pan_number.value,
                    customer_name=customer_name.value,
                    customer_address=customer_address.value,
                    customer_gstin=customer_gstin.value,
                    ship_to_name=ship_to_name.value,
                    ship_to_address=ship_to_address.value,
                    ship_to_gstin=ship_to_gstin.value,
                    bank_account_holder_name=bank_acc_name.value,
                    bank_account_number=bank_acc_no.value,
                    bank_branch_name=bank_branch.value,
                    bank_branch_ifsc=bank_ifsc.value,
                )
                for i in line_items:
                    inv.add_item(i)
                
                # Generate PDF using user-configured output directory
                pdf_out_dir = config.get('pdf_output_dir', '')
                if not pdf_out_dir:
                    pdf_out_dir = _default_pdf_dir()
                pdf_path = generate_pdf(inv, logo_path, output_dir=pdf_out_dir)
                
                # Save invoice to DB including pdf path
                db.save_invoice(inv, pdf_path=pdf_path)
                
                page.snack_bar = ft.SnackBar(ft.Text(f"Invoice saved to {pdf_path}"))
                page.snack_bar.open = True
                
                # Auto-increment invoice number
                start = config.get('invoice_start_number', 32)
                invoice_number.value = db.get_next_invoice_number(start_number=start)
                
                # Refresh history tab
                refresh_history()
                
                page.update()
            except Exception as ex:
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"Error: {ex}", color=ft.colors.WHITE),
                    bgcolor=ft.colors.RED
                )
                page.snack_bar.open = True
                page.update()

        # Initialize defaults
        start = config.get('invoice_start_number', 32)
        invoice_number.value = db.get_next_invoice_number(start_number=start)
        invoice_date.value = datetime.datetime.now().strftime("%d-%m-%Y")
        refresh_items_list()
        populate_customer_dropdown()

        create_tab = ft.Tab(
            text="Create",
            icon=ft.icons.ADD,
            content=ft.ListView(
                expand=True,
                spacing=10,
                padding=10,
                controls=[
                    ft.Text("Invoice Info", size=18, weight=ft.FontWeight.BOLD),
                    invoice_number,
                    _date_row(invoice_date, dp_invoice_date),
                    po_number,
                    _date_row(po_date, dp_po_date),
                    challan_number,
                    _date_row(challan_date, dp_challan_date),
                    ft.Divider(),
                    ft.Text("Customer Info", size=18, weight=ft.FontWeight.BOLD),
                    customer_dropdown,
                    customer_name, customer_address, customer_gstin,
                    ft.Divider(),
                    ft.Text("Ship To", size=18, weight=ft.FontWeight.BOLD),
                    ship_to_name, ship_to_address, ship_to_gstin,
                    ft.Divider(),
                    ft.Text("Line Items", size=18, weight=ft.FontWeight.BOLD),
                    items_column,
                    ft.ElevatedButton("Add Item", icon=ft.icons.ADD, on_click=open_add_dialog),
                    ft.Divider(),
                    lbl_subtotal, lbl_tax, lbl_total,
                    ft.Divider(),
                    ft.ElevatedButton("Generate PDF", icon=ft.icons.PICTURE_AS_PDF, on_click=generate_pdf_action, color=ft.colors.WHITE, bgcolor=ft.colors.BLUE)
                ]
            )
        )

        # ---------------------------------------------------------
        # VIEW INVOICES TAB
        # ---------------------------------------------------------
        history_list = ft.ListView(expand=True, spacing=10)

        def _open_pdf(pdf_path: str):
            """Open the PDF with an external viewer."""
            if not pdf_path or not os.path.exists(pdf_path):
                page.snack_bar = ft.SnackBar(ft.Text("PDF file not found."))
                page.snack_bar.open = True
                page.update()
                return

            opened = False

            # Primary: Android 'am start' command (most reliable on Android)
            if _is_android():
                opened = _am_start([
                    '-a', 'android.intent.action.VIEW',
                    '-d', f'file://{pdf_path}',
                    '-t', 'application/pdf',
                    '--grant-read-uri-permission',
                ])

            # Fallback 1: intent:// URL via Flet's launch_url
            if not opened:
                try:
                    encoded_path = urllib.parse.quote(pdf_path, safe='/')
                    intent_url = (
                        f"intent://{encoded_path}#Intent;"
                        "scheme=file;"
                        "action=android.intent.action.VIEW;"
                        "type=application/pdf;"
                        "launchFlags=0x10000001;"
                        "end"
                    )
                    page.launch_url(intent_url)
                    opened = True
                except Exception:
                    pass

            # Fallback 2: file:// URL
            if not opened:
                try:
                    page.launch_url(f"file://{pdf_path}")
                    opened = True
                except Exception:
                    pass

            # Always show a confirmation snackbar with the path
            page.snack_bar = ft.SnackBar(
                ft.Text(f"PDF: {pdf_path}", selectable=True),
                duration=4000,
            )
            page.snack_bar.open = True
            page.update()

        def _share_whatsapp(inv_num: str, pdf_path: str):
            """Share invoice via WhatsApp with PDF attached and a short thank-you message."""
            msg = "Thank you"

            # Primary: Android 'am start' with file attachment
            if pdf_path and os.path.exists(pdf_path) and _is_android():
                sent = _am_start([
                    '-a', 'android.intent.action.SEND',
                    '-t', 'application/pdf',
                    '-p', 'com.whatsapp',
                    '--es', 'android.intent.extra.TEXT', msg,
                    '--eu', 'android.intent.extra.STREAM', f'file://{pdf_path}',
                    '--grant-read-uri-permission',
                ])
                if sent:
                    return

            # Fallback 1: intent:// URL
            if pdf_path and os.path.exists(pdf_path):
                stream = urllib.parse.quote(f"file://{pdf_path}", safe='')
                encoded_msg = urllib.parse.quote(msg)
                intent_url = (
                    "intent://send#Intent;"
                    "action=android.intent.action.SEND;"
                    "type=application/pdf;"
                    "package=com.whatsapp;"
                    f"S.android.intent.extra.TEXT={encoded_msg};"
                    f"S.android.intent.extra.STREAM={stream};"
                    "launchFlags=0x10000001;"
                    "end"
                )
                try:
                    page.launch_url(intent_url)
                    return
                except Exception:
                    pass

            # Fallback 2: WhatsApp web API (text only, tell user where PDF is)
            text_with_path = msg
            if pdf_path:
                text_with_path = f"{msg}\n\nInvoice PDF saved at: {pdf_path}"
            encoded = urllib.parse.quote(text_with_path)
            try:
                page.launch_url(f"https://api.whatsapp.com/send?text={encoded}")
            except Exception:
                page.launch_url(f"https://wa.me/?text={encoded}")

        def _share_gmail(inv_num: str, customer: str, pdf_path: str):
            """Share invoice via Gmail with PDF attached and a professional message."""
            subject = f"Invoice {inv_num}"
            body_text = (
                f"Dear {customer},\n\n"
                f"Please find invoice {inv_num}.\n\n"
                "Regards,\n"
                "Nitra Enterprises"
            )

            # Primary: Android 'am start' with file attachment
            if pdf_path and os.path.exists(pdf_path) and _is_android():
                sent = _am_start([
                    '-a', 'android.intent.action.SEND',
                    '-t', 'application/pdf',
                    '-p', 'com.google.android.gm',
                    '--es', 'android.intent.extra.SUBJECT', subject,
                    '--es', 'android.intent.extra.TEXT', body_text,
                    '--eu', 'android.intent.extra.STREAM', f'file://{pdf_path}',
                    '--grant-read-uri-permission',
                ])
                if sent:
                    return

            # Fallback 1: intent:// URL
            if pdf_path and os.path.exists(pdf_path):
                enc_subject = urllib.parse.quote(subject)
                enc_body = urllib.parse.quote(body_text)
                stream = urllib.parse.quote(f"file://{pdf_path}", safe='')
                intent_url = (
                    "intent://send#Intent;"
                    "action=android.intent.action.SEND;"
                    "type=application/pdf;"
                    "package=com.google.android.gm;"
                    f"S.android.intent.extra.SUBJECT={enc_subject};"
                    f"S.android.intent.extra.TEXT={enc_body};"
                    f"S.android.intent.extra.STREAM={stream};"
                    "launchFlags=0x10000001;"
                    "end"
                )
                try:
                    page.launch_url(intent_url)
                    return
                except Exception:
                    pass

            # Fallback 2: mailto (no attachment)
            enc_subject = urllib.parse.quote(subject)
            enc_body = urllib.parse.quote(body_text)
            page.launch_url(f"mailto:?subject={enc_subject}&body={enc_body}")

        def open_history_pdf(inv_num: str):
            """Regenerate PDF (in case file was deleted) and open it."""
            pdf_path = db.get_invoice_pdf_path(inv_num)
            if pdf_path and os.path.exists(pdf_path):
                _open_pdf(pdf_path)
                return
            # Regenerate if missing
            inv = db.get_invoice(inv_num)
            if inv:
                pdf_out_dir = config.get('pdf_output_dir', '')
                if not pdf_out_dir:
                    pdf_out_dir = _default_pdf_dir()
                try:
                    pdf_path = generate_pdf(inv, logo_path, output_dir=pdf_out_dir)
                    db.save_invoice(inv, pdf_path=pdf_path)
                    _open_pdf(pdf_path)
                except Exception as ex:
                    page.snack_bar = ft.SnackBar(
                        ft.Text(f"Error: {ex}", color=ft.colors.WHITE),
                        bgcolor=ft.colors.RED,
                    )
                    page.snack_bar.open = True
                    page.update()
            else:
                page.snack_bar = ft.SnackBar(ft.Text("Invoice not found in database."))
                page.snack_bar.open = True
                page.update()

        def refresh_history():
            history_list.controls.clear()
            invoices = db.get_all_invoices_with_paths()
            if not invoices:
                history_list.controls.append(ft.Text("No generated invoices found."))
            for inv, pdf_path in invoices:
                history_list.controls.append(
                    ft.Card(
                        content=ft.Container(
                            padding=10,
                            content=ft.Column([
                                ft.Row([
                                    ft.Column([
                                        ft.Text(f"{inv.invoice_number}", weight=ft.FontWeight.BOLD),
                                        ft.Text(f"{inv.customer_name} | Date: {inv.invoice_date}")
                                    ], expand=True),
                                    ft.IconButton(
                                        icon=ft.icons.OPEN_IN_NEW,
                                        tooltip="Open PDF",
                                        on_click=lambda e, n=inv.invoice_number: open_history_pdf(n)
                                    )
                                ]),
                                ft.Row([
                                    ft.OutlinedButton(
                                        text="WhatsApp",
                                        icon=ft.icons.SHARE,
                                        on_click=lambda e, n=inv.invoice_number, p=pdf_path: _share_whatsapp(n, p),
                                        style=ft.ButtonStyle(color=ft.colors.GREEN),
                                    ),
                                    ft.OutlinedButton(
                                        text="Gmail",
                                        icon=ft.icons.EMAIL,
                                        on_click=lambda e, n=inv.invoice_number, c=inv.customer_name, p=pdf_path: _share_gmail(n, c, p),
                                        style=ft.ButtonStyle(color=ft.colors.RED),
                                    ),
                                ], spacing=8)
                            ])
                        )
                    )
                )

        refresh_history()

        view_tab = ft.Tab(
            text="History",
            icon=ft.icons.HISTORY,
            content=ft.Container(
                padding=10,
                content=history_list,
                expand=True
            )
        )

        # ---------------------------------------------------------
        # FIRST-RUN: Ask user to choose PDF save directory (once)
        # ---------------------------------------------------------
        def _ensure_pdf_dir():
            """On first run, prompt user to pick a PDF save folder.
            Called after the full UI is built so dialogs can display."""
            saved_dir = config.get('pdf_output_dir', '')
            if saved_dir:
                # Already configured – nothing to do
                return

            # FilePicker for first-run directory selection
            def on_first_dir_result(e: ft.FilePickerResultEvent):
                if e.path:
                    chosen = e.path
                else:
                    # User cancelled → use a sensible default
                    chosen = _default_pdf_dir()
                config.set('pdf_output_dir', chosen)
                config.save()
                pdf_dir_field.value = chosen
                try:
                    os.makedirs(chosen, exist_ok=True)
                except OSError:
                    pass
                # Close the dialog
                if page.dialog:
                    page.dialog.open = False
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"PDFs will be saved to: {chosen}"),
                    duration=4000,
                )
                page.snack_bar.open = True
                page.update()

            first_picker = ft.FilePicker(on_result=on_first_dir_result)
            page.overlay.append(first_picker)

            def _pick_dir(e):
                first_picker.get_directory_path(dialog_title="Choose PDF Save Folder")

            def _use_default(e):
                chosen = _default_pdf_dir()
                config.set('pdf_output_dir', chosen)
                config.save()
                pdf_dir_field.value = chosen
                try:
                    os.makedirs(chosen, exist_ok=True)
                except OSError:
                    pass
                page.dialog.open = False
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"PDFs will be saved to: {chosen}"),
                    duration=4000,
                )
                page.snack_bar.open = True
                page.update()

            dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text("Choose PDF Save Location"),
                content=ft.Text(
                    "Please choose a folder where your invoice PDFs will be saved.\n\n"
                    "You can change this later in Settings."
                ),
                actions=[
                    ft.TextButton("Choose Folder", on_click=_pick_dir),
                    ft.TextButton("Use Default", on_click=_use_default),
                ],
            )
            page.dialog = dlg
            dlg.open = True
            page.update()

        # ---------------------------------------------------------
        # MAIN LAYOUT
        # ---------------------------------------------------------
        main_tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[create_tab, view_tab, settings_tab],
            expand=True
        )
            
        page.add(
            ft.SafeArea(
                ft.Container(
                    content=main_tabs,
                    expand=True
                ),
                expand=True
            )
        )

        # Trigger first-run directory selection after UI is rendered
        _ensure_pdf_dir()

    except Exception as e:
        page.add(ft.SafeArea(ft.ListView([ft.Text(f"ERROR LAYOUT: {e}\n{traceback.format_exc()}", color="red", selectable=True)], expand=True)))
        return

def start_flet():
    ft.app(target=main)

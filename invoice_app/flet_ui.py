import flet as ft
from invoice_app.models import Invoice, LineItem, InvoiceDB, ConfigManager
from invoice_app.pdf_generator import generate_pdf
import os
import re
import shutil
import subprocess
import traceback
import datetime
import urllib.parse


def _is_android() -> bool:
    """Check if running on Android."""
    return os.path.exists('/system/bin/am') or 'ANDROID_ROOT' in os.environ


def _am_start(args: list) -> bool:
    """Run 'am start' on Android. Returns True only if the command succeeds."""
    try:
        am = '/system/bin/am' if os.path.exists('/system/bin/am') else 'am'
        result = subprocess.run(
            [am, 'start'] + args,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10,
            text=True
        )
        # am start returns 0 on success; non-zero or 'Error' in output means failure
        if result.returncode == 0:
            stderr_text = result.stderr
            stdout_text = result.stdout
            # Check for error indicators
            if 'Error' not in stderr_text and 'Exception' not in stderr_text and 'Error' not in stdout_text:
                return True
        return False
    except subprocess.TimeoutExpired:
        return False
    except Exception as e:
        return False


def _get_content_uri(file_path: str) -> str:
    """Get a content:// URI for a file from Android's MediaStore.

    On Android 7+ (API 24+), file:// URIs are blocked for inter-app
    communication.  We query MediaStore for the file's _id and build a
    content://media/external/file/<id> URI that any app can open.
    """
    if not _is_android() or not file_path or not os.path.exists(file_path):
        return ""
    
    try:
        # Ensure MediaScanner has indexed the file first
        _media_scan(file_path)
        
        import time
        time.sleep(0.5)  # Give MediaScanner time to index

        # Query MediaStore for the file
        try:
            result = subprocess.run(
                ['content', 'query', '--uri', 'content://media/external/file',
                 '--projection', '_id',
                 '--where', f"_data='{file_path}'"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=10,
                text=True
            )
            output = result.stdout
            # Look for _id in the format: _id=12345
            match = re.search(r'_id=(\d+)', output)
            if match:
                media_id = match.group(1)
                uri = f"content://media/external/file/{media_id}"
                return uri
        except Exception as e:
            pass

        # Fallback: Use file URI provider path (for recent Android versions with file access)
        # Some devices may support content://media/external/file or content://com.android.externalstorage.documents/document/primary%3ADownload%2FInvoices%2Ffile.pdf
        try:
            # Try another MediaStore table
            result = subprocess.run(
                ['content', 'query', '--uri', 'content://media/external/downloads',
                 '--projection', '_id,_data',
                 '--where', f"_data='{file_path}'"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=10,
                text=True
            )
            output = result.stdout
            match = re.search(r'_id=(\d+)', output)
            if match:
                media_id = match.group(1)
                uri = f"content://media/external/downloads/{media_id}"
                return uri
        except Exception:
            pass

        # Last resort: try file:// if on shared storage (may work on some devices)
        if any(x in file_path for x in ['/Download/', '/Documents/', '/Pictures/', '/storage/emulated']):
            return f"file://{file_path}"
            
    except Exception as e:
        pass

    # If all else fails, return file:// URI
    return f"file://{file_path}"


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
    """Return a sensible default PDF directory.
    
    Prefers shared/public directories (Downloads, external storage) so PDFs
    are visible in file-manager apps and accessible to other apps for
    opening and sharing.
    """
    if _is_android():
        # On Android, try multiple common paths
        common_bases = [
            '/storage/emulated/0',      # Most common on modern Android
            os.environ.get('EXTERNAL_STORAGE', ''),  # EXTERNAL_STORAGE env var
            '/sdcard',                   # Legacy path
            '/storage/self/primary',     # Alias for /storage/emulated/0
        ]
        
        # Try Download/Invoices first (most visible)
        for base in common_bases:
            if not base or base == '':
                continue
            try:
                d = os.path.join(base, 'Download', 'Invoices')
                if _is_writable_dir(d):
                    return d
            except Exception:
                pass
        
        # Fallback to root-level Invoices folder
        for base in common_bases:
            if not base or base == '':
                continue
            try:
                d = os.path.join(base, 'Invoices')
                if _is_writable_dir(d):
                    return d
            except Exception:
                pass
    else:
        # Desktop: use home directory
        home = os.environ.get("HOME") or os.path.expanduser("~")
        if home and home != "~":
            d = os.path.join(home, 'Invoices')
            if _is_writable_dir(d):
                return d

    # App-private storage on Android (accessible without special permissions)
    for env_var in ['FLET_APP_STORAGE_DATA', 'ANDROID_APP_DATA', 'XDG_DATA_HOME']:
        app_dir = os.environ.get(env_var, '')
        if app_dir:
            try:
                d = os.path.join(app_dir, 'Invoices')
                if _is_writable_dir(d):
                    return d
            except Exception:
                pass
    
    # Home directory fallback
    home = os.environ.get("HOME") or os.path.expanduser("~")
    if home and home != "~":
        try:
            d = os.path.join(home, "Invoices")
            if _is_writable_dir(d):
                return d
        except Exception:
            pass
    
    # Temp directory as last resort
    import tempfile
    d = os.path.join(tempfile.gettempdir(), "Invoices")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def _copy_to_shared_storage(pdf_path: str) -> str:
    """Copy a PDF from app-private storage to a shared/public location.
    
    Returns the shared path on success, or the original path if copying fails.
    This ensures the PDF is visible in file-manager apps and accessible to
    other apps (WhatsApp, Gmail, PDF viewers) for opening and sharing.
    """
    if not pdf_path:
        return pdf_path
    
    # If file doesn't exist, return as-is
    if not os.path.exists(pdf_path):
        return pdf_path

    # If already in shared storage (contains common paths), no need to copy
    shared_markers = ['/Download/', '/Documents/', '/Pictures/', '/storage/emulated', '/sdcard', '/storage/self']
    is_shared = any(m in pdf_path for m in shared_markers)
    if is_shared:
        return pdf_path

    # Try to copy to Download/Invoices (most visible on Android)
    filename = os.path.basename(pdf_path)
    
    common_bases = [
        '/storage/emulated/0',
        os.environ.get('EXTERNAL_STORAGE', ''),
        '/sdcard',
        '/storage/self/primary',
    ]
    
    # Try Download/Invoices first
    for base in common_bases:
        if not base or base == '':
            continue
        for sub in ['Download/Invoices', 'Invoices', 'Download']:
            try:
                dest_dir = os.path.join(base, sub)
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(dest_dir, filename)
                
                # Copy with 644 permissions so other apps can read it
                shutil.copy2(pdf_path, dest_path)
                try:
                    os.chmod(dest_path, 0o644)
                except OSError:
                    pass
                
                # Notify MediaScanner
                _media_scan(dest_path)
                
                return dest_path
            except (PermissionError, OSError):
                continue

    return pdf_path


def _media_scan(file_path: str):
    """Ask Android's MediaScanner to index a file so it appears in file managers."""
    if not _is_android():
        return
    try:
        am = '/system/bin/am' if os.path.exists('/system/bin/am') else 'am'
        subprocess.run(
            [am, 'broadcast',
             '-a', 'android.intent.action.MEDIA_SCANNER_SCAN_FILE',
             '-d', f'file://{file_path}'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        pass

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
        bank_address = ft.TextField(label="Branch Address", value=config.get('bank_branch_address', ''), multiline=True)
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
                chosen_path = e.path
                # On Android, FilePicker may return SAF URIs — convert to
                # a usable filesystem path or fall back to defaults
                if chosen_path.startswith('content://'):
                    # SAF URIs can't be used as filesystem paths;
                    # extract a best-guess path or use default
                    if 'primary:' in chosen_path:
                        # content://...primary:Invoices → /storage/emulated/0/Invoices
                        suffix = chosen_path.split('primary:')[-1]
                        suffix = urllib.parse.unquote(suffix)
                        chosen_path = os.path.join('/storage/emulated/0', suffix)
                    else:
                        # Can't resolve — use default
                        chosen_path = _default_pdf_dir()
                # Validate the chosen path is writable
                if not _is_writable_dir(chosen_path):
                    chosen_path = _default_pdf_dir()
                    page.snack_bar = ft.SnackBar(
                        ft.Text(f"Selected folder not writable. Using default: {chosen_path}"),
                        duration=4000,
                    )
                    page.snack_bar.open = True
                pdf_dir_field.value = chosen_path
                pdf_dir_field.update()
                page.update()

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
            config.set('bank_branch_address', bank_address.value)
            # Validate and save PDF output directory
            pdf_dir = pdf_dir_field.value.strip() if pdf_dir_field.value else ''
            if pdf_dir:
                # Handle SAF URIs that might have been pasted
                if pdf_dir.startswith('content://'):
                    if 'primary:' in pdf_dir:
                        suffix = pdf_dir.split('primary:')[-1]
                        suffix = urllib.parse.unquote(suffix)
                        pdf_dir = os.path.join('/storage/emulated/0', suffix)
                    else:
                        pdf_dir = _default_pdf_dir()
                # Validate the directory
                if not _is_writable_dir(pdf_dir):
                    pdf_dir = _default_pdf_dir()
                    pdf_dir_field.value = pdf_dir
            config.set('pdf_output_dir', pdf_dir)
            try:
                config.set('invoice_start_number', int(invoice_start_number.value))
            except ValueError:
                pass
            try:
                config.save()
                page.snack_bar = ft.SnackBar(ft.Text(f"Settings saved! PDFs will save to: {pdf_dir or 'default location'}"))
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
                    bank_acc_name, bank_acc_no, bank_branch, bank_ifsc, bank_address,
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
                # Basic validations before generating invoice/PDF
                if not (invoice_number.value or '').strip():
                    raise ValueError('Invoice number required')
                if not (invoice_date.value or '').strip():
                    raise ValueError('Invoice date required')
                if not (customer_name.value or '').strip():
                    raise ValueError('Customer name required')
                if not line_items:
                    raise ValueError('Please add at least one line item')

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
                    bank_branch_address=bank_address.value,
                )
                for i in line_items:
                    inv.add_item(i)
                
                # Generate PDF using user-configured output directory
                pdf_out_dir = config.get('pdf_output_dir', '')
                if not pdf_out_dir:
                    pdf_out_dir = _default_pdf_dir()
                pdf_path = generate_pdf(inv, logo_path, output_dir=pdf_out_dir)
                
                # PDF is already saved to the appropriate location (Downloads/Invoices on Android)
                # No need to copy - save directly to database
                db.save_invoice(inv, pdf_path=pdf_path)
                
                # Notify user
                file_location = "Downloads/Invoices folder" if _is_android() else "storage"
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"Invoice {inv.invoice_number} saved successfully! Saved at: {pdf_path}"),
                    duration=5000
                )
                page.snack_bar.open = True
                
                # Auto-increment invoice number
                start = config.get('invoice_start_number', 32)
                invoice_number.value = db.get_next_invoice_number(start_number=start)
                
                # Refresh history tab
                refresh_history()
                
                page.update()
            except Exception as ex:
                error_msg = str(ex)
                # Simplify error message for users
                if "Permission denied" in error_msg or "PermissionError" in error_msg:
                    user_msg = "PDF saved to app storage (public storage access not available)"
                else:
                    user_msg = f"Error: {error_msg[:80]}"
                
                page.snack_bar = ft.SnackBar(
                    ft.Text(user_msg, color=ft.colors.WHITE),
                    bgcolor=ft.colors.RED,
                    duration=6000,
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
            if not pdf_path:
                page.snack_bar = ft.SnackBar(ft.Text("No PDF path provided."))
                page.snack_bar.open = True
                page.update()
                return
            
            if not os.path.exists(pdf_path):
                page.snack_bar = ft.SnackBar(ft.Text(f"PDF file not found: {pdf_path}"))
                page.snack_bar.open = True
                page.update()
                return

            # Copy to shared storage so external apps can access the file
            shared_path = _copy_to_shared_storage(pdf_path)
            opened = False

            if _is_android():
                # Ensure file is properly indexed and accessible
                _media_scan(shared_path)
                
                import time
                time.sleep(0.3)

                # Primary: use content:// URI from MediaStore (required on Android 7+)
                content_uri = _get_content_uri(shared_path)
                if content_uri:
                    opened = _am_start([
                        '-a', 'android.intent.action.VIEW',
                        '-d', content_uri,
                        '-t', 'application/pdf',
                        '--grant-read-uri-permission',
                    ])
                    if opened:
                        page.snack_bar = ft.SnackBar(
                            ft.Text(f"Opening PDF: {os.path.basename(shared_path)}"),
                            duration=2000,
                        )
                        page.snack_bar.open = True
                        page.update()
                        return

                # Fallback 1: try file:// with am start (works on older Android)
                if not opened:
                    opened = _am_start([
                        '-a', 'android.intent.action.VIEW',
                        '-d', f'file://{shared_path}',
                        '-t', 'application/pdf',
                    ])
                    if opened:
                        page.snack_bar = ft.SnackBar(
                            ft.Text(f"Opening PDF: {os.path.basename(shared_path)}"),
                            duration=2000,
                        )
                        page.snack_bar.open = True
                        page.update()
                        return

            # Fallback 2: Use Flet's launch_url with file:// (may work on some devices)
            if not opened:
                try:
                    page.launch_url(f"file://{shared_path}")
                    page.snack_bar = ft.SnackBar(
                        ft.Text(f"Opening PDF: {os.path.basename(shared_path)}"),
                        duration=2000,
                    )
                    page.snack_bar.open = True
                    page.update()
                    opened = True
                except Exception as e:
                    pass

            # If still not opened, show the path to the user
            if not opened:
                page.snack_bar = ft.SnackBar(
                    ft.Text(f"Could not open PDF. Saved at: {shared_path}", selectable=True),
                    duration=5000,
                )
                page.snack_bar.open = True
                page.update()

        def _share_whatsapp(inv_num: str, pdf_path: str):
            """Share invoice via WhatsApp with PDF attached."""
            msg = "Thank you"
            
            # Ensure we have a valid PDF
            if not pdf_path or not os.path.exists(pdf_path):
                page.snack_bar = ft.SnackBar(ft.Text("PDF file not found."))
                page.snack_bar.open = True
                page.update()
                return

            # Copy to shared storage if needed and use content:// URI on Android 7+
            shared_path = _copy_to_shared_storage(pdf_path)
            _media_scan(shared_path)
            
            import time
            time.sleep(0.5)
            
            sent = False

            if _is_android():
                share_uri = _get_content_uri(shared_path) or f'file://{shared_path}'
                sent = _am_start([
                    '-a', 'android.intent.action.SEND',
                    '-t', 'application/pdf',
                    '-p', 'com.whatsapp',
                    '--grant-read-uri-permission',
                    '--es', 'android.intent.extra.TEXT', msg,
                    '--eu', 'android.intent.extra.STREAM', share_uri,
                ])
                if sent:
                    page.snack_bar = ft.SnackBar(ft.Text("Opening WhatsApp with PDF..."))
                    page.snack_bar.open = True
                    page.update()
                    return

            # If failed
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Failed to open WhatsApp. PDF saved at: {shared_path}", color=ft.colors.WHITE),
                bgcolor=ft.colors.RED,
                duration=6000
            )
            page.snack_bar.open = True
            page.update()

        def _share_gmail(inv_num: str, customer: str, pdf_path: str):
            """Share invoice via Gmail with PDF attached."""
            subject = f"Invoice {inv_num}"
            sender_name = (company_name.value or config.get('company_name', '') or 'Company').strip()
            body_text = (
                f"Dear {customer},\n\n"
                f"Please find invoice {inv_num} attached.\n\n"
                "Regards,\n"
                f"{sender_name}"
            )

            # Ensure we have a valid PDF
            if not pdf_path or not os.path.exists(pdf_path):
                page.snack_bar = ft.SnackBar(ft.Text("PDF file not found."))
                page.snack_bar.open = True
                page.update()
                return

            # Copy to shared storage if needed and use content:// URI on Android 7+
            shared_path = _copy_to_shared_storage(pdf_path)
            _media_scan(shared_path)
            
            import time
            time.sleep(0.5)
            
            sent = False

            if _is_android():
                share_uri = _get_content_uri(shared_path) or f'file://{shared_path}'
                sent = _am_start([
                    '-a', 'android.intent.action.SEND',
                    '-t', 'application/pdf',
                    '-p', 'com.google.android.gm',
                    '--grant-read-uri-permission',
                    '--es', 'android.intent.extra.SUBJECT', subject,
                    '--es', 'android.intent.extra.TEXT', body_text,
                    '--eu', 'android.intent.extra.STREAM', share_uri,
                ])
                if sent:
                    page.snack_bar = ft.SnackBar(ft.Text("Opening Gmail with PDF..."))
                    page.snack_bar.open = True
                    page.update()
                    return

            # If failed
            page.snack_bar = ft.SnackBar(
                ft.Text(f"Failed to open Gmail. PDF saved at: {shared_path}", color=ft.colors.WHITE),
                bgcolor=ft.colors.RED,
                duration=6000
            )
            page.snack_bar.open = True
            page.update()

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
                    # PDF is already saved to the appropriate location
                    db.save_invoice(inv, pdf_path=pdf_path)
                    _open_pdf(pdf_path)
                except Exception as ex:
                    page.snack_bar = ft.SnackBar(
                        ft.Text(f"Error generating PDF: {ex}", color=ft.colors.WHITE),
                        bgcolor=ft.colors.RED,
                        duration=6000,
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
                    # Handle Android SAF URIs
                    if chosen.startswith('content://'):
                        if 'primary:' in chosen:
                            suffix = chosen.split('primary:')[-1]
                            suffix = urllib.parse.unquote(suffix)
                            chosen = os.path.join('/storage/emulated/0', suffix)
                        else:
                            chosen = _default_pdf_dir()
                    # Validate writability
                    if not _is_writable_dir(chosen):
                        chosen = _default_pdf_dir()
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

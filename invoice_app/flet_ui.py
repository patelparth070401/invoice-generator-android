import flet as ft
from invoice_app.models import Invoice, LineItem, InvoiceDB, ConfigManager
from invoice_app.pdf_generator import generate_pdf
import os
import datetime

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
        import traceback
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
            try:
                config.set('invoice_start_number', int(invoice_start_number.value))
            except ValueError:
                pass
            config.save()
            page.snack_bar = ft.SnackBar(ft.Text("Settings saved successfully!"))
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
                
                # Save invoice to DB
                db.save_invoice(inv)
                
                # Generate PDF
                pdf_path = generate_pdf(inv, logo_path)
                
                page.snack_bar = ft.SnackBar(ft.Text(f"PDF saved: {pdf_path}"))
                page.snack_bar.open = True
                
                # Auto-increment invoice number
                start = config.get('invoice_start_number', 32)
                invoice_number.value = db.get_next_invoice_number(start_number=start)
                
                # Refresh history tab
                refresh_history()
                
                try:
                    page.launch_url(f"file://{pdf_path}")
                except Exception:
                    pass
                
                page.update()
            except Exception as ex:
                import traceback
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

        def open_history_pdf(inv_num):
            inv = db.get_invoice(inv_num)
            if inv:
                pdf_path = generate_pdf(inv, logo_path)
                try:
                    page.launch_url(f"file://{pdf_path}")
                except Exception:
                    pass

        def refresh_history():
            history_list.controls.clear()
            invoices = db.get_all_invoices()
            if not invoices:
                history_list.controls.append(ft.Text("No generated invoices found."))
            for inv in invoices:
                history_list.controls.append(
                    ft.Card(
                        content=ft.Container(
                            padding=10,
                            content=ft.Row([
                                ft.Column([
                                    ft.Text(f"{inv.invoice_number}", weight=ft.FontWeight.BOLD),
                                    ft.Text(f"{inv.customer_name} | Date: {inv.invoice_date}")
                                ], expand=True),
                                ft.IconButton(icon=ft.icons.OPEN_IN_NEW, on_click=lambda e, n=inv.invoice_number: open_history_pdf(n))
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
    except Exception as e:
        import traceback
        page.add(ft.SafeArea(ft.ListView([ft.Text(f"ERROR LAYOUT: {e}\n{traceback.format_exc()}", color="red", selectable=True)], expand=True)))
        return

def start_flet():
    ft.app(target=main)

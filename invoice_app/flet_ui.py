import flet as ft
from invoice_app.models import Invoice, LineItem, InvoiceDB, ConfigManager
from invoice_app.pdf_generator import generate_pdf
import os

def main(page: ft.Page):
    page.title = "Invoice Generator"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.padding = 20
    page.scroll = ft.ScrollMode.AUTO

    db = InvoiceDB()
    config = ConfigManager()
    
    # Try to load logo
    logo_path = config.get('logo_path', '')
    if not logo_path or not os.path.exists(logo_path):
        bundled_logo = os.path.join(os.path.dirname(__file__), 'logo.png')
        if os.path.exists(bundled_logo):
            logo_path = bundled_logo

    # Company Details Fields
    company_name = ft.TextField(label="Company Name", value=config.get('company_name', ''))
    company_address = ft.TextField(label="Address", value=config.get('company_address', ''), multiline=True)
    company_gstin = ft.TextField(label="GSTIN", value=config.get('company_gstin', ''))
    company_phone = ft.TextField(label="Phone", value=config.get('company_phone', ''))
    company_email = ft.TextField(label="Email", value=config.get('company_email', ''))
    pan_number = ft.TextField(label="PAN No", value=config.get('pan_number', ''))
    udyam_reg = ft.TextField(label="UDYAM Registration", value=config.get('udyam_registration', ''))

    # Invoice Details Fields
    invoice_number = ft.TextField(label="Invoice Number")
    invoice_date = ft.TextField(label="Invoice Date (dd-mm-yyyy)")
    po_number = ft.TextField(label="PO Number")
    po_date = ft.TextField(label="PO Date (dd-mm-yyyy)")
    challan_number = ft.TextField(label="Challan Number")
    challan_date = ft.TextField(label="Challan Date (dd-mm-yyyy)")

    # Customer Fields
    customer_name = ft.TextField(label="Customer Name")
    customer_address = ft.TextField(label="Customer Address", multiline=True)
    customer_gstin = ft.TextField(label="Customer GSTIN")

    # Bank Fields
    bank_acc_name = ft.TextField(label="Account Holder Name", value=config.get('bank_account_holder_name', ''))
    bank_acc_no = ft.TextField(label="Account No", value=config.get('bank_account_number', ''))
    bank_branch = ft.TextField(label="Branch Name", value=config.get('bank_branch_name', ''))
    bank_ifsc = ft.TextField(label="Branch IFSC", value=config.get('bank_branch_ifsc', ''))

    # Line Items
    line_items = []

    def update_totals():
        subtotal = sum(i.total_price for i in line_items)
        sgst = sum(i.sgst_amount for i in line_items)
        cgst = sum(i.cgst_amount for i in line_items)
        total = subtotal + sgst + cgst
        
        lbl_subtotal.value = f"Subtotal: ₹{subtotal:.2f}"
        lbl_tax.value = f"Tax (SGST+CGST): ₹{sgst+cgst:.2f}"
        lbl_total.value = f"Total: ₹{total:.2f}"
        page.update()

    def build_items_table():
        rows = []
        for i, item in enumerate(line_items):
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(item.description)),
                        ft.DataCell(ft.Text(f"{item.qty}")),
                        ft.DataCell(ft.Text(f"₹{item.unit_price}")),
                        ft.DataCell(ft.Text(f"₹{item.total_price}")),
                        ft.DataCell(
                            ft.IconButton(
                                icon=ft.icons.DELETE,
                                icon_color="red",
                                on_click=lambda e, idx=i: remove_item(idx)
                            )
                        )
                    ]
                )
            )
        return ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Description")),
                ft.DataColumn(ft.Text("Qty")),
                ft.DataColumn(ft.Text("Price")),
                ft.DataColumn(ft.Text("Total")),
                ft.DataColumn(ft.Text("")),
            ],
            rows=rows,
        )

    items_table_container = ft.Column([build_items_table()])

    def remove_item(idx):
        if 0 <= idx < len(line_items):
            line_items.pop(idx)
            refresh_table()

    def refresh_table():
        items_table_container.controls = [build_items_table()]
        update_totals()
        page.update()

    # Add Item Dialog
    add_desc = ft.TextField(label="Description")
    add_hsn = ft.TextField(label="HSN")
    add_qty = ft.TextField(label="Qty", value="1")
    add_price = ft.TextField(label="Unit Price", value="0.0")
    add_sgst = ft.TextField(label="SGST %", value="9")
    add_cgst = ft.TextField(label="CGST %", value="9")

    def dlg_add_item_click(e):
        try:
            qty = float(add_qty.value)
            price = float(add_price.value)
            sgst = float(add_sgst.value)
            cgst = float(add_cgst.value)
            
            item = LineItem(
                description=add_desc.value,
                hsn=add_hsn.value,
                qty=qty,
                uom="NOS",
                unit_price=price,
                sgst_rate=sgst,
                cgst_rate=cgst
            )
            line_items.append(item)
            refresh_table()
            add_item_dialog.open = False
            page.update()
        except ValueError:
            pass # Show error in a real app

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

    # Totals labels
    lbl_subtotal = ft.Text("Subtotal: ₹0.00", weight=ft.FontWeight.BOLD)
    lbl_tax = ft.Text("Tax (SGST+CGST): ₹0.00", weight=ft.FontWeight.BOLD)
    lbl_total = ft.Text("Total: ₹0.00", weight=ft.FontWeight.BOLD, size=20, color=ft.colors.BLUE)

    def generate_pdf_action(e):
        inv = Invoice(
            invoice_number=invoice_number.value,
            invoice_date=invoice_date.value,
            po_number=po_number.value,
            po_date=po_date.value,
            company_name=company_name.value,
            company_address=company_address.value,
            company_gstin=company_gstin.value,
            company_phone=company_phone.value,
            company_email=company_email.value,
            pan_number=pan_number.value,
            customer_name=customer_name.value,
            customer_address=customer_address.value,
            customer_gstin=customer_gstin.value,
            bank_account_holder_name=bank_acc_name.value,
            bank_account_number=bank_acc_no.value,
            bank_branch_name=bank_branch.value,
            bank_branch_ifsc=bank_ifsc.value,
        )
        for i in line_items:
            inv.add_item(i)
        
        pdf_path = generate_pdf(inv, logo_path)
        
        snack = ft.SnackBar(ft.Text(f"PDF Generated at: {pdf_path}"))
        page.snack_bar = snack
        snack.open = True
        page.update()

    # Initialize auto invoice number
    prefix = config.get('invoice_prefix', 'INV')
    invoice_number.value = db.get_next_invoice_number(prefix=prefix, series_year=True, width=4)
    import datetime
    invoice_date.value = datetime.datetime.now().strftime("%d-%m-%Y")

    # Layout
    page.add(
        ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(
                    text="Create Invoice",
                    content=ft.Column([
                        ft.Text("Company Details", size=18, weight=ft.FontWeight.BOLD),
                        company_name, company_address, company_gstin, pan_number,
                        ft.Divider(),
                        ft.Text("Invoice Info", size=18, weight=ft.FontWeight.BOLD),
                        invoice_number, invoice_date, po_number,
                        ft.Divider(),
                        ft.Text("Customer Info", size=18, weight=ft.FontWeight.BOLD),
                        customer_name, customer_address, customer_gstin,
                        ft.Divider(),
                        ft.Text("Line Items", size=18, weight=ft.FontWeight.BOLD),
                        items_table_container,
                        ft.ElevatedButton("Add Item", on_click=open_add_dialog),
                        lbl_subtotal, lbl_tax, lbl_total,
                        ft.Divider(),
                        ft.ElevatedButton("Generate PDF", on_click=generate_pdf_action, color=ft.colors.WHITE, bgcolor=ft.colors.BLUE)
                    ], scroll=ft.ScrollMode.AUTO)
                ),
                ft.Tab(
                    text="Bank Details",
                    content=ft.Column([
                        bank_acc_name, bank_acc_no, bank_branch, bank_ifsc
                    ], scroll=ft.ScrollMode.AUTO)
                )
            ],
            expand=1,
        )
    )

def start_flet():
    ft.app(target=main)

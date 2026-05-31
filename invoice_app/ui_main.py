"""
PySide6 GUI aligned to your requested layout:
- Adds Challan No/Date (below UDYAM in PDF meta)
- Two-column blocks: Invoice To (left) & Ship To (right) with Name/Address/GSTIN
- Recursion fix: block table signals during totals update
- Robust View PDF button in Actions column
"""
import os
import sys
from typing import Optional
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QPushButton,
    QTableWidget, QTableWidgetItem, QDialog, QFormLayout, QFileDialog,
    QMessageBox, QTextEdit, QDateEdit, QFrame, QRadioButton, QButtonGroup, QCheckBox,
    QCalendarWidget, QComboBox
)
from PySide6.QtCore import Qt, QDate, QUrl
from PySide6.QtGui import QFont, QDesktopServices, QIcon

from .models import Invoice, LineItem, InvoiceDB, ConfigManager
from .pdf_generator import generate_pdf


class DatePickerDialog(QDialog):
    """Dialog with calendar widget for date selection."""
    def __init__(self, parent=None, initial_date: QDate = None):
        super().__init__(parent)
        self.setWindowTitle("Select Date")
        self.setGeometry(100, 100, 350, 350)
        layout = QVBoxLayout()
        
        self.calendar = QCalendarWidget()
        if initial_date:
            self.calendar.setSelectedDate(initial_date)
        else:
            self.calendar.setSelectedDate(QDate.currentDate())
        
        layout.addWidget(self.calendar)
        
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
    
    def get_date(self) -> QDate:
        return self.calendar.selectedDate()


class LineItemDialog(QDialog):
    # Class variable to track last used tax rates
    last_sgst_rate = 9.0
    last_cgst_rate = 9.0
    
    def __init__(self, parent=None, item: LineItem = None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Line Item")
        self.setGeometry(100, 100, 420, 380)
        layout = QFormLayout()
        self.description_input = QLineEdit()
        self.hsn_input = QLineEdit()
        self.qty_input = QDoubleSpinBox(); self.qty_input.setRange(0, 999999.99); self.qty_input.setValue(1)
        self.uom_input = QLineEdit()
        self.unit_price_input = QDoubleSpinBox(); self.unit_price_input.setRange(0, 99999999.99); self.unit_price_input.setDecimals(2)
        self.sgst_input = QDoubleSpinBox(); self.sgst_input.setRange(0, 100); self.sgst_input.setValue(LineItemDialog.last_sgst_rate)
        self.cgst_input = QDoubleSpinBox(); self.cgst_input.setRange(0, 100); self.cgst_input.setValue(LineItemDialog.last_cgst_rate)
        layout.addRow("Description:", self.description_input)
        layout.addRow("HSN:", self.hsn_input)
        layout.addRow("Quantity:", self.qty_input)
        layout.addRow("UOM:", self.uom_input)
        layout.addRow("Unit Price (₹):", self.unit_price_input)
        layout.addRow("SGST (%):", self.sgst_input)
        layout.addRow("CGST (%):", self.cgst_input)
        if item:
            self.description_input.setText(item.description)
            self.hsn_input.setText(item.hsn)
            self.qty_input.setValue(item.qty)
            self.uom_input.setText(item.uom)
            self.unit_price_input.setValue(item.unit_price)
            self.sgst_input.setValue(item.sgst_rate)
            self.cgst_input.setValue(item.cgst_rate)
        btns = QHBoxLayout(); save_btn = QPushButton("Save"); cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(self.accept); cancel_btn.clicked.connect(self.reject)
        btns.addWidget(save_btn); btns.addWidget(cancel_btn)
        layout.addRow(btns)
        self.setLayout(layout)

    def get_item(self) -> LineItem:
        sgst_val = self.sgst_input.value()
        cgst_val = self.cgst_input.value()
        # Save the rates for next time
        LineItemDialog.last_sgst_rate = sgst_val
        LineItemDialog.last_cgst_rate = cgst_val
        return LineItem(
            description=self.description_input.text(), hsn=self.hsn_input.text(),
            qty=self.qty_input.value(), uom=self.uom_input.text(), unit_price=self.unit_price_input.value(),
            sgst_rate=sgst_val, cgst_rate=cgst_val
        )


class InvoiceApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Invoice Generator")
        self.setGeometry(100, 100, 1200, 720)
        self.db = InvoiceDB()
        self.config = ConfigManager()
        
        # Try to load logo from config, or use bundled logo if available
        self.logo_path = self.config.get('logo_path', '')
        if not self.logo_path or not os.path.exists(self.logo_path):
            # Try to find bundled logo
            try:
                if hasattr(sys, '_MEIPASS'):
                    # Running as exe (bundled by PyInstaller)
                    bundled_logo = os.path.join(sys._MEIPASS, 'invoice_app', 'logo.png')
                else:
                    # Running from source
                    bundled_logo = os.path.join(os.path.dirname(__file__), 'logo.png')
                
                if os.path.exists(bundled_logo):
                    self.logo_path = bundled_logo
            except Exception:
                pass
        
        self.init_ui()

    def init_ui(self):
        tabs = QTabWidget()
        tabs.addTab(self.create_invoice_tab(), "Create Invoice")
        tabs.addTab(self.create_view_tab(), "View Invoices")
        self.setCentralWidget(tabs)

    def create_invoice_tab(self) -> QWidget:
        widget = QWidget(); layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Company block - loaded from last invoice (now editable)
        details_layout = QHBoxLayout()
        company_frame = QFrame(); company_layout = QFormLayout(); company_layout.setVerticalSpacing(6)
        self.company_name_input = QLineEdit()
        self.company_address_input = QLineEdit()
        self.company_gstin_input = QLineEdit()
        self.company_phone_input = QLineEdit()
        self.company_email_input = QLineEdit()
        self.udyam_input = QLineEdit()
        self.pan_input = QLineEdit()
        company_layout.addRow("Company Name:", self.company_name_input)
        company_layout.addRow("Address:", self.company_address_input)
        company_layout.addRow("GSTIN:", self.company_gstin_input)
        company_layout.addRow("Phone:", self.company_phone_input)
        company_layout.addRow("Email:", self.company_email_input)
        company_layout.addRow("UDYAM Registration:", self.udyam_input)
        company_layout.addRow("PAN No:", self.pan_input)
        company_frame.setLayout(company_layout); details_layout.addWidget(company_frame)

        # Invoice/PO/Challan block
        invoice_frame = QFrame(); invoice_layout = QFormLayout(); invoice_layout.setVerticalSpacing(6)
        self.invoice_number_input = QLineEdit()
        self.invoice_date_input = QDateEdit(); self.invoice_date_input.setDate(QDate.currentDate()); self.invoice_date_input.setDisplayFormat("dd-MM-yyyy")
        self.po_number_input = QLineEdit()
        self.po_date_input = QLineEdit(); self.po_date_input.setPlaceholderText("dd-MM-yyyy"); self.po_date_input.setText(QDate.currentDate().toString("dd-MM-yyyy"))
        self.challan_number_input = QLineEdit()
        self.challan_date_input = QLineEdit(); self.challan_date_input.setPlaceholderText("dd-MM-yyyy")

        num_row = QWidget(); num_row_layout = QHBoxLayout(num_row)
        num_row_layout.setContentsMargins(0, 0, 0, 0)
        num_row_layout.setSpacing(6)
        num_row_layout.addWidget(self.invoice_number_input, 1)
        num_row_layout.addStretch()

        # Invoice Date with picker
        inv_date_row = QWidget(); inv_date_layout = QHBoxLayout(inv_date_row)
        inv_date_layout.setContentsMargins(0, 0, 0, 0)
        inv_date_layout.setSpacing(6)
        inv_date_picker_btn = QPushButton("📅"); inv_date_picker_btn.setMaximumWidth(40); inv_date_picker_btn.setMinimumHeight(28)
        inv_date_picker_btn.clicked.connect(lambda: self.open_date_picker(self.invoice_date_input))
        inv_date_layout.addWidget(self.invoice_date_input, 1)
        inv_date_layout.addWidget(inv_date_picker_btn, 0)

        # PO Date with picker and clear button
        po_date_row = QWidget(); po_date_layout = QHBoxLayout(po_date_row)
        po_date_layout.setContentsMargins(0, 0, 0, 0)
        po_date_layout.setSpacing(6)
        po_date_picker_btn = QPushButton("📅"); po_date_picker_btn.setMaximumWidth(40); po_date_picker_btn.setMinimumHeight(28)
        po_date_picker_btn.clicked.connect(lambda: self.open_date_picker_for_lineedit(self.po_date_input))
        po_date_clear_btn = QPushButton("✕"); po_date_clear_btn.setMaximumWidth(40); po_date_clear_btn.setMinimumHeight(28)
        po_date_clear_btn.clicked.connect(lambda: self.po_date_input.clear())
        po_date_layout.addWidget(self.po_date_input, 1)
        po_date_layout.addWidget(po_date_picker_btn, 0)
        po_date_layout.addWidget(po_date_clear_btn, 0)

        # Challan Date with picker and clear button
        challan_date_row = QWidget(); challan_date_layout = QHBoxLayout(challan_date_row)
        challan_date_layout.setContentsMargins(0, 0, 0, 0)
        challan_date_layout.setSpacing(6)
        challan_date_picker_btn = QPushButton("📅"); challan_date_picker_btn.setMaximumWidth(40); challan_date_picker_btn.setMinimumHeight(28)
        challan_date_picker_btn.clicked.connect(lambda: self.open_date_picker_for_lineedit(self.challan_date_input))
        challan_date_clear_btn = QPushButton("✕"); challan_date_clear_btn.setMaximumWidth(40); challan_date_clear_btn.setMinimumHeight(28)
        challan_date_clear_btn.clicked.connect(lambda: self.challan_date_input.clear())
        challan_date_layout.addWidget(self.challan_date_input, 1)
        challan_date_layout.addWidget(challan_date_picker_btn, 0)
        challan_date_layout.addWidget(challan_date_clear_btn, 0)

        invoice_layout.addRow("Invoice Number:", num_row)
        invoice_layout.addRow("Invoice Date:", inv_date_row)
        invoice_layout.addRow("PO Number:", self.po_number_input)
        invoice_layout.addRow("PO Date:", po_date_row)
        invoice_layout.addRow("Challan No:", self.challan_number_input)
        invoice_layout.addRow("Challan Date:", challan_date_row)
        
        # Additional Info rows
        self.additional_info_line1_input = QLineEdit()
        self.additional_info_line2_input = QLineEdit()
        invoice_layout.addRow("", QLabel(""))  # Blank row
        invoice_layout.addRow("Additional Info 1:", self.additional_info_line1_input)
        invoice_layout.addRow("Additional Info 2:", self.additional_info_line2_input)
        
        invoice_frame.setLayout(invoice_layout); details_layout.addWidget(invoice_frame)
        layout.addLayout(details_layout)

        # Invoice To & Ship To (two-column)
        two_col = QHBoxLayout()
        inv_to_frame = QFrame(); inv_to_layout = QFormLayout()
        self.customer_name_input = QComboBox()
        self.customer_name_input.setEditable(True)
        self.customer_name_input.lineEdit().setPlaceholderText("Type or select customer name")
        self.customer_address_input = QTextEdit(); self.customer_address_input.setMaximumHeight(60)
        self.customer_gstin_input = QLineEdit()
        inv_to_layout.addRow("Invoice To Name:", self.customer_name_input)
        inv_to_layout.addRow("Invoice To Address:", self.customer_address_input)
        inv_to_layout.addRow("Invoice To GSTIN:", self.customer_gstin_input)
        inv_to_frame.setLayout(inv_to_layout)

        ship_to_frame = QFrame(); ship_to_layout = QFormLayout()
        self.ship_to_name_input = QLineEdit()
        self.ship_to_address_input = QTextEdit(); self.ship_to_address_input.setMaximumHeight(60)
        self.ship_to_gstin_input = QLineEdit()
        ship_to_layout.addRow("Ship To Name:", self.ship_to_name_input)
        ship_to_layout.addRow("Ship To Address:", self.ship_to_address_input)
        ship_to_layout.addRow("Ship To GSTIN:", self.ship_to_gstin_input)
        ship_to_frame.setLayout(ship_to_layout)

        two_col.addWidget(inv_to_frame)
        two_col.addWidget(ship_to_frame)
        layout.addLayout(two_col)
        
        # Connect customer name selection to auto-fill
        self.customer_name_input.currentTextChanged.connect(self.on_customer_selected)

        # --- Bottom split: left bank details, right items/totals/actions
        bottom_split = QHBoxLayout(); bottom_split.setSpacing(12)

        # Bank details - loaded from last invoice (now editable)
        bank_col = QVBoxLayout(); bank_col.setSpacing(8)
        bank_label = QLabel("Bank Details"); bank_label.setStyleSheet("font-weight: 600;")
        bank_col.addWidget(bank_label)
        bank_form = QFormLayout(); bank_form.setVerticalSpacing(6)
        self.bank_account_holder_input = QLineEdit()
        self.bank_account_input = QLineEdit(); self.bank_branch_name_input = QLineEdit(); self.bank_branch_ifsc_input = QLineEdit();
        self.bank_branch_address_input = QTextEdit(); self.bank_branch_address_input.setMaximumHeight(60)
        bank_form.addRow("Account Holder Name:", self.bank_account_holder_input)
        bank_form.addRow("Account No:", self.bank_account_input)
        bank_form.addRow("Branch Name:", self.bank_branch_name_input)
        bank_form.addRow("Branch IFSC:", self.bank_branch_ifsc_input)
        bank_form.addRow("Branch Address:", self.bank_branch_address_input)
        bank_col.addLayout(bank_form)
        bank_col.addStretch()

        # Right column: line items
        right_col = QVBoxLayout(); right_col.setSpacing(8)
        right_col.addWidget(QLabel("Line Items:"))
        self.items_table = QTableWidget(); self.items_table.setColumnCount(8)
        self.items_table.setHorizontalHeaderLabels(["Description", "HSN", "Qty", "UOM", "Unit Price", "SGST%", "CGST%", "Total Price"])
        self.items_table.itemChanged.connect(lambda _: self.update_totals())
        self.items_table.horizontalHeader().setStretchLastSection(True)
        right_col.addWidget(self.items_table, 1)

        item_btns = QHBoxLayout(); item_btns.setSpacing(6)
        add_item_btn = QPushButton("Add Item"); edit_item_btn = QPushButton("Edit Item"); remove_item_btn = QPushButton("Remove Item")
        for b in (add_item_btn, edit_item_btn, remove_item_btn):
            b.setMinimumHeight(28)
        add_item_btn.clicked.connect(self.add_line_item); edit_item_btn.clicked.connect(self.edit_line_item); remove_item_btn.clicked.connect(self.remove_line_item)
        item_btns.addWidget(add_item_btn); item_btns.addWidget(edit_item_btn); item_btns.addWidget(remove_item_btn); item_btns.addStretch()
        right_col.addLayout(item_btns)

        # Totals
        totals_layout = QHBoxLayout(); totals_layout.addStretch()
        self.subtotal_label = QLabel("Subtotal: ₹0.00")
        self.sgst_label = QLabel("SGST: ₹0.00"); self.cgst_label = QLabel("CGST: ₹0.00")
        self.total_label = QLabel("Total: ₹0.00"); self.roundoff_total_label = QLabel("Round-off Total: ₹0.00"); self.roundoff_diff_label = QLabel("Round Off: +0.00")
        bold = QFont(); bold.setBold(True); self.total_label.setFont(bold)
        totals_layout.addWidget(self.subtotal_label)
        totals_layout.addWidget(self.sgst_label); totals_layout.addWidget(self.cgst_label)
        totals_layout.addWidget(self.total_label); totals_layout.addWidget(self.roundoff_total_label); totals_layout.addWidget(self.roundoff_diff_label)
        right_col.addLayout(totals_layout)

        # Actions
        actions = QHBoxLayout(); actions.setSpacing(8)
        new_invoice_btn = QPushButton("New Invoice"); save_btn = QPushButton("Save Invoice"); gen_btn = QPushButton("Generate PDF"); open_folder_btn = QPushButton("Open Output Folder")
        for b in (new_invoice_btn, save_btn, gen_btn, open_folder_btn):
            b.setMinimumHeight(30)
        new_invoice_btn.clicked.connect(self.new_invoice); save_btn.clicked.connect(self.save_invoice); gen_btn.clicked.connect(self.generate_pdf_action); open_folder_btn.clicked.connect(self.open_output_folder)
        actions.addStretch(); actions.addWidget(new_invoice_btn); actions.addWidget(save_btn); actions.addWidget(gen_btn); actions.addWidget(open_folder_btn)
        right_col.addLayout(actions)

        bottom_split.addLayout(bank_col, 1)
        bottom_split.addLayout(right_col, 2)
        layout.addLayout(bottom_split)

        widget.setLayout(layout)
        
        # Auto-fill invoice number and company/bank details (after all widgets are created)
        self.fill_next_invoice_number()
        
        return widget

    def create_view_tab(self) -> QWidget:
        widget = QWidget(); layout = QVBoxLayout(); layout.addWidget(QLabel("Saved Invoices:"))
        self.invoices_table = QTableWidget(); self.invoices_table.setColumnCount(5)
        self.invoices_table.setHorizontalHeaderLabels(["Invoice Number", "Date", "Customer", "Total", "Actions"])

        self.invoices_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.invoices_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.invoices_table.setSelectionMode(QTableWidget.SingleSelection)

        header = self.invoices_table.horizontalHeader()
        header.setStretchLastSection(False)
        self.invoices_table.setColumnWidth(4, 210)

        layout.addWidget(self.invoices_table)

        btns = QHBoxLayout(); refresh_btn = QPushButton("Refresh"); load_btn = QPushButton("Load"); delete_btn = QPushButton("Delete")
        refresh_btn.clicked.connect(self.refresh_invoices_list); load_btn.clicked.connect(self.load_selected_invoice); delete_btn.clicked.connect(self.delete_selected_invoice)
        btns.addWidget(refresh_btn); btns.addWidget(load_btn); btns.addWidget(delete_btn); btns.addStretch(); layout.addLayout(btns)

        self.invoices_table.itemDoubleClicked.connect(lambda _: self.view_selected_invoice())

        widget.setLayout(layout); self.refresh_invoices_list(); return widget

    # Items
    def add_line_item(self):
        dialog = LineItemDialog(self)
        if dialog.exec():
            item = dialog.get_item(); self.add_item_to_table(item); self.update_totals()

    def edit_line_item(self):
        row = self.items_table.currentRow()
        if row < 0:
            return
        try:
            item = LineItem(
                description=self.items_table.item(row, 0).text(),
                hsn=self.items_table.item(row, 1).text(),
                qty=float(self.items_table.item(row, 2).text()),
                uom=self.items_table.item(row, 3).text(),
                unit_price=float(self.items_table.item(row, 4).text().replace('₹', '')),
                sgst_rate=float(self.items_table.item(row, 5).text()),
                cgst_rate=float(self.items_table.item(row, 6).text()),
            )
        except Exception:
            item = None
        dialog = LineItemDialog(self, item)
        if dialog.exec():
            item = dialog.get_item()
            self.items_table.setItem(row, 0, QTableWidgetItem(item.description))
            self.items_table.setItem(row, 1, QTableWidgetItem(item.hsn))
            self.items_table.setItem(row, 2, QTableWidgetItem(f"{item.qty:.2f}"))
            self.items_table.setItem(row, 3, QTableWidgetItem(item.uom))
            self.items_table.setItem(row, 4, QTableWidgetItem(f"₹{item.unit_price:.2f}"))
            self.items_table.setItem(row, 5, QTableWidgetItem(f"{item.sgst_rate:.0f}"))
            self.items_table.setItem(row, 6, QTableWidgetItem(f"{item.cgst_rate:.0f}"))
            self.items_table.setItem(row, 7, QTableWidgetItem(f"₹{item.total_price:.2f}"))
    def remove_line_item(self):
        r = self.items_table.currentRow()
        if r >= 0:
            self.items_table.removeRow(r)
        self.update_totals()

    def add_item_to_table(self, item: LineItem):
        row = self.items_table.rowCount(); self.items_table.insertRow(row)
        self.items_table.setItem(row, 0, QTableWidgetItem(item.description))
        self.items_table.setItem(row, 1, QTableWidgetItem(item.hsn))
        self.items_table.setItem(row, 2, QTableWidgetItem(f"{item.qty:.2f}"))
        self.items_table.setItem(row, 3, QTableWidgetItem(item.uom))
        self.items_table.setItem(row, 4, QTableWidgetItem(f"₹{item.unit_price:.2f}"))
        self.items_table.setItem(row, 5, QTableWidgetItem(f"{item.sgst_rate:.0f}"))
        self.items_table.setItem(row, 6, QTableWidgetItem(f"{item.cgst_rate:.0f}"))
        self.items_table.setItem(row, 7, QTableWidgetItem(f"₹{item.total_price:.2f}"))

    def update_totals(self):
        # Prevent recursive itemChanged while we update cells
        self.items_table.blockSignals(True)
        try:
            import decimal
            subtotal = 0.0
            sgst_total = 0.0
            cgst_total = 0.0
            for row in range(self.items_table.rowCount()):
                try:
                    qty = float(self.items_table.item(row, 2).text())
                    unit_price = float(self.items_table.item(row, 4).text().replace('₹', ''))
                    sgst_rate = float(self.items_table.item(row, 5).text())
                    cgst_rate = float(self.items_table.item(row, 6).text())
                    total_price = qty * unit_price
                    subtotal += total_price
                    sgst_total += total_price * (sgst_rate / 100.0)
                    cgst_total += total_price * (cgst_rate / 100.0)
                except Exception:
                    pass
            total = subtotal + sgst_total + cgst_total
            # Proper rounding: 0.5 rounds up
            round_total = float(decimal.Decimal(str(total)).quantize(decimal.Decimal('1'), rounding=decimal.ROUND_HALF_UP))
            round_diff = round_total - total
            sgst_eff = (sgst_total / subtotal * 100.0) if subtotal else 0.0
            cgst_eff = (cgst_total / subtotal * 100.0) if subtotal else 0.0
            self.subtotal_label.setText(f"Subtotal: ₹{subtotal:.2f}")
            self.sgst_label.setText(f"SGST ({sgst_eff:.2f}%): ₹{sgst_total:.2f}")
            self.cgst_label.setText(f"CGST ({cgst_eff:.2f}%): ₹{cgst_total:.2f}")
            self.total_label.setText(f"Total: ₹{total:.2f}")
            self.roundoff_total_label.setText(f"Round-off Total: ₹{round_total:.2f}")
            self.roundoff_diff_label.setText(f"Round Off: {round_diff:+.2f}")
        finally:
            self.items_table.blockSignals(False)

    # Persistence
    def save_invoice(self):
        if not self.invoice_number_input.text().strip():
            QMessageBox.warning(self, "Error", "Please enter an invoice number."); return
        customer_name = self.customer_name_input.currentText().strip()
        if not customer_name:
            QMessageBox.warning(self, "Error", "Please enter Invoice To Name."); return
        
        # Handle optional PO Date - only set if user has not cleared it
        po_date_str = self.po_date_input.text().strip()
        
        # Handle optional Challan Date - only set if user has selected a date (not empty)
        challan_date_str = self.challan_date_input.text().strip()
        
        inv = Invoice(
            invoice_number=self.invoice_number_input.text(),
            invoice_date=self.invoice_date_input.date().toString("dd-MM-yyyy"),
            po_number=self.po_number_input.text(),
            po_date=po_date_str,
            company_name=self.company_name_input.text(),
            company_address=self.company_address_input.text(),
            company_gstin=self.company_gstin_input.text(),
            company_phone=self.company_phone_input.text(),
            company_email=self.company_email_input.text(),
            pan_number=self.pan_input.text(),
            udyam_registration=self.udyam_input.text(),
            # Challan
            challan_number=self.challan_number_input.text(),
            challan_date=challan_date_str,
            # Additional Info
            additional_info_line1=self.additional_info_line1_input.text(),
            additional_info_line2=self.additional_info_line2_input.text(),
            # Invoice To
            customer_name=customer_name,
            customer_address=self.customer_address_input.toPlainText(),
            customer_gstin=self.customer_gstin_input.text(),
            # Ship To
            ship_to_name=self.ship_to_name_input.text(),
            ship_to_address=self.ship_to_address_input.toPlainText(),
            ship_to_gstin=self.ship_to_gstin_input.text(),
            # Bank
            bank_account_number=self.bank_account_input.text(),
            bank_account_holder_name=self.bank_account_holder_input.text(),
            bank_branch_name=self.bank_branch_name_input.text(),
            bank_branch_ifsc=self.bank_branch_ifsc_input.text(),
            bank_branch_address=self.bank_branch_address_input.toPlainText(),
        )
        for row in range(self.items_table.rowCount()):
            try:
                item = LineItem(
                    description=self.items_table.item(row, 0).text(),
                    hsn=self.items_table.item(row, 1).text(),
                    qty=float(self.items_table.item(row, 2).text()),
                    uom=self.items_table.item(row, 3).text(),
                    unit_price=float(self.items_table.item(row, 4).text().replace('₹', '')),
                    sgst_rate=float(self.items_table.item(row, 5).text()),
                    cgst_rate=float(self.items_table.item(row, 6).text()),
                )
                inv.add_item(item)
            except Exception:
                pass
        if self.db.save_invoice(inv):
            # Save company and bank details to config for next time
            self.config.set('company_name', self.company_name_input.text())
            self.config.set('company_address', self.company_address_input.text())
            self.config.set('company_gstin', self.company_gstin_input.text())
            self.config.set('company_phone', self.company_phone_input.text())
            self.config.set('company_email', self.company_email_input.text())
            self.config.set('udyam_registration', self.udyam_input.text())
            self.config.set('pan_number', self.pan_input.text())
            self.config.set('bank_account_number', self.bank_account_input.text())
            self.config.set('bank_account_holder_name', self.bank_account_holder_input.text())
            self.config.set('bank_branch_name', self.bank_branch_name_input.text())
            self.config.set('bank_branch_ifsc', self.bank_branch_ifsc_input.text())
            self.config.set('bank_branch_address', self.bank_branch_address_input.toPlainText())
            self.config.save()
            QMessageBox.information(self, "Success", "Invoice saved successfully!")
            # Refresh customer dropdown after saving
            self.populate_customer_dropdown()
            self.refresh_invoices_list()
        else:
            QMessageBox.critical(self, "Error", "Failed to save invoice.")

    def generate_pdf_action(self):
        if not self.invoice_number_input.text().strip():
            QMessageBox.warning(self, "Error", "Please enter an invoice number and save first."); return
        self.save_invoice()
        invoice = self.db.get_invoice(self.invoice_number_input.text())
        if invoice:
            pdf_path = generate_pdf(invoice, self.logo_path)
            QMessageBox.information(self, "Success", f"PDF generated:\n{pdf_path}")
            QDesktopServices.openUrl(QUrl.fromLocalFile(pdf_path))
        else:
            QMessageBox.critical(self, "Error", "Invoice not found. Please save it first.")

    def new_invoice(self):
        """Clear invoice-specific fields to create a new invoice."""
        # Generate next invoice number
        self.fill_next_invoice_number()
        
        # Clear Invoice To fields
        self.customer_name_input.setEditText("")
        self.customer_address_input.clear()
        self.customer_gstin_input.clear()
        
        # Clear Ship To fields
        self.ship_to_name_input.clear()
        self.ship_to_address_input.clear()
        self.ship_to_gstin_input.clear()
        
        # Clear PO and Challan fields
        self.po_number_input.clear()
        self.po_date_input.setText(QDate.currentDate().toString("dd-MM-yyyy"))
        self.challan_number_input.clear()
        self.challan_date_input.clear()
        
        # Clear Additional Info fields
        self.additional_info_line1_input.clear()
        self.additional_info_line2_input.clear()
        
        # Clear line items
        self.items_table.setRowCount(0)
        
        # Reset totals
        self.update_totals()
        
        QMessageBox.information(self, "New Invoice", "Ready to create a new invoice!")

    def send_invoice_dialog(self, invoice: Optional[Invoice] = None, from_view_tab: bool = False):
        """Open send dialog; can be launched from form (uses current invoice) or from a row (uses provided invoice)."""
        # Decide source invoice
        if invoice is None:
            if not self.invoice_number_input.text().strip():
                QMessageBox.warning(self, "Error", "Please enter an invoice number and save first."); return
            self.save_invoice()
            invoice = self.db.get_invoice(self.invoice_number_input.text())
            if not invoice:
                QMessageBox.critical(self, "Error", "Invoice not found. Please save it first."); return
        
        # Generate or locate PDF
        pdf_path = generate_pdf(invoice, self.logo_path)

        # Simple dialog - just ask for email
        dlg = QDialog(self); dlg.setWindowTitle("Send Invoice via Email")
        dlg.setMinimumWidth(450)
        form = QFormLayout(dlg)
        
        email_input = QLineEdit()
        email_input.setPlaceholderText("recipient@example.com")
        form.addRow("Recipient Email:", email_input)

        btns = QHBoxLayout()
        send_btn = QPushButton("Send")
        cancel_btn = QPushButton("Cancel")
        send_btn.setMinimumHeight(30); cancel_btn.setMinimumHeight(30)
        btns.addStretch(); btns.addWidget(send_btn); btns.addWidget(cancel_btn)
        form.addRow(btns)

        def open_gmail_compose():
            to_email = email_input.text().strip()
            if not to_email:
                QMessageBox.warning(dlg, "Missing", "Please enter recipient email."); return
            
            # Validate email format
            if '@' not in to_email or '.' not in to_email.split('@')[-1]:
                QMessageBox.warning(dlg, "Invalid Email", "Please enter a valid email address."); return
            
            import webbrowser
            import subprocess
            subject = f"Invoice {invoice.invoice_number}"
            body = f"Dear Customer,%0D%0A%0D%0APlease find attached invoice {invoice.invoice_number}.%0D%0A%0D%0AThank you for your business.%0D%0A%0D%0ARegards,%0D%0ANitra Enterprises"
            gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={to_email}&su={subject}&body={body}"
            
            # Open Gmail compose in browser
            webbrowser.open(gmail_url)
            
            # Open Windows Explorer with the PDF file selected (ready to drag and drop)
            subprocess.Popen(f'explorer /select,"{pdf_path}"')
            
            # Show instruction message
            QMessageBox.information(
                dlg, 
                "Ready to Send", 
                f"Gmail compose opened in your browser.\n\n"
                f"The PDF file is now selected in Explorer.\n"
                f"Simply drag and drop the file into Gmail to attach it.\n\n"
                f"File: {os.path.basename(pdf_path)}"
            )
            
            dlg.accept()

        send_btn.clicked.connect(open_gmail_compose)
        cancel_btn.clicked.connect(dlg.reject)
        email_input.setFocus()
        dlg.exec()

    def refresh_invoices_list(self):
        self.invoices_table.setRowCount(0)
        for invoice in self.db.get_all_invoices():
            row = self.invoices_table.rowCount(); self.invoices_table.insertRow(row)
            self.invoices_table.setItem(row, 0, QTableWidgetItem(invoice.invoice_number))
            self.invoices_table.setItem(row, 1, QTableWidgetItem(invoice.invoice_date))
            self.invoices_table.setItem(row, 2, QTableWidgetItem(invoice.customer_name))
            self.invoices_table.setItem(row, 3, QTableWidgetItem(f"₹{invoice.grand_total:.2f}"))

            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(6, 2, 6, 2)
            cell_layout.setAlignment(Qt.AlignCenter)

            view_btn = QPushButton("View PDF"); view_btn.setMinimumWidth(90)
            send_btn = QPushButton("Send"); send_btn.setMinimumWidth(90)
            view_btn.clicked.connect(lambda checked=False, inv=invoice: self.view_pdf(inv))
            send_btn.clicked.connect(lambda checked=False, inv=invoice: self.send_invoice_dialog(inv, from_view_tab=True))
            cell_layout.addWidget(view_btn)
            cell_layout.addWidget(send_btn)
            cell_layout.addStretch()
            self.invoices_table.setCellWidget(row, 4, cell)

    def load_selected_invoice(self):
        r = self.invoices_table.currentRow()
        if r < 0:
            return
        num = self.invoices_table.item(r, 0).text()
        inv = self.db.get_invoice(num)
        if inv:
            self.invoice_number_input.setText(inv.invoice_number)
            self.invoice_date_input.setDate(QDate.fromString(inv.invoice_date, "dd-MM-yyyy"))
            self.po_number_input.setText(inv.po_number)
            # Load PO Date only if it exists (not empty)
            if inv.po_date and inv.po_date.strip():
                self.po_date_input.setText(inv.po_date)
            else:
                self.po_date_input.clear()
            self.challan_number_input.setText(inv.challan_number)
            # Load Challan Date only if it exists (not empty)
            if inv.challan_date and inv.challan_date.strip():
                self.challan_date_input.setText(inv.challan_date)
            else:
                self.challan_date_input.clear()
            self.additional_info_line1_input.setText(inv.additional_info_line1)
            self.additional_info_line2_input.setText(inv.additional_info_line2)
            self.company_name_input.setText(inv.company_name)
            self.company_address_input.setText(inv.company_address)
            self.company_gstin_input.setText(inv.company_gstin)
            self.company_phone_input.setText(inv.company_phone)
            self.company_email_input.setText(inv.company_email)
            self.udyam_input.setText(inv.udyam_registration)
            self.pan_input.setText(inv.pan_number)
            # Set customer name in combo box
            self.customer_name_input.setCurrentText(inv.customer_name) if inv.customer_name else self.customer_name_input.setEditText("")
            self.customer_address_input.setText(inv.customer_address)
            self.customer_gstin_input.setText(inv.customer_gstin)
            self.ship_to_name_input.setText(inv.ship_to_name)
            self.ship_to_address_input.setText(inv.ship_to_address)
            self.ship_to_gstin_input.setText(inv.ship_to_gstin)
            self.bank_account_holder_input.setText(inv.bank_account_holder_name)
            self.bank_account_input.setText(inv.bank_account_number)
            self.bank_branch_name_input.setText(inv.bank_branch_name)
            self.bank_branch_ifsc_input.setText(inv.bank_branch_ifsc)
            self.bank_branch_address_input.setText(inv.bank_branch_address)
            self.items_table.setRowCount(0)
            for item in inv.line_items:
                self.add_item_to_table(item)
            self.update_totals()

    def delete_selected_invoice(self):
        r = self.invoices_table.currentRow()
        if r < 0:
            return
        num = self.invoices_table.item(r, 0).text()
        reply = QMessageBox.question(self, "Confirm Delete", f"Delete invoice {num}?")
        if reply == QMessageBox.Yes:
            self.db.delete_invoice(num)
            self.refresh_invoices_list()

    def view_selected_invoice(self):
        r = self.invoices_table.currentRow()
        if r < 0:
            return
        num_item = self.invoices_table.item(r, 0)
        if not num_item:
            return
        inv = self.db.get_invoice(num_item.text())
        if inv:
            self.view_pdf(inv)

    def view_pdf(self, invoice: Invoice):
        if not invoice:
            return
        pdf_path = generate_pdf(invoice, self.logo_path)
        QDesktopServices.openUrl(QUrl.fromLocalFile(pdf_path))

    def browse_logo(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Logo", "", "Image Files (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            self.logo_path = file_path; self.logo_path_label.setText(file_path)
            self.config.set('logo_path', file_path); self.config.save()

    def save_defaults(self):
        # kept for backward compatibility if called elsewhere
        pass

    def fill_next_invoice_number(self):
        prefix = self.config.get('invoice_prefix', 'INV'); width = int(self.config.get('series_width', 4))
        next_num = self.db.get_next_invoice_number(prefix=prefix, series_year=True, width=width)
        self.invoice_number_input.setText(next_num)
        # Load company/bank details from last invoice
        self.load_last_invoice_details()
        # Populate customer dropdown
        self.populate_customer_dropdown()
    
    def populate_customer_dropdown(self):
        """Populate the Invoice To Name dropdown with all unique customers."""
        self.customer_name_input.blockSignals(True)
        current_text = self.customer_name_input.currentText()
        self.customer_name_input.clear()
        
        customers = self.db.get_unique_customers()
        customer_names = sorted(customers.keys())
        
        if customer_names:
            self.customer_name_input.addItems(customer_names)
        
        # Restore previous selection if it exists
        if current_text and current_text in customer_names:
            self.customer_name_input.setCurrentText(current_text)
        
        self.customer_name_input.blockSignals(False)
    
    def on_customer_selected(self, customer_name: str):
        """Auto-fill customer address and GSTIN when a customer is selected."""
        if not customer_name or not customer_name.strip():
            return
        
        customers = self.db.get_unique_customers()
        if customer_name in customers:
            customer_data = customers[customer_name]
            self.customer_address_input.setPlainText(customer_data.get('address', ''))
            self.customer_gstin_input.setText(customer_data.get('gstin', ''))
            self.ship_to_name_input.setText(customer_data.get('ship_to_name', ''))
            self.ship_to_address_input.setPlainText(customer_data.get('ship_to_address', ''))
            self.ship_to_gstin_input.setText(customer_data.get('ship_to_gstin', ''))
    
    def open_date_picker(self, date_input: QDateEdit):
        """Open a calendar picker dialog to select a date."""
        dialog = DatePickerDialog(self, date_input.date())
        if dialog.exec():
            selected_date = dialog.get_date()
            date_input.setDate(selected_date)
    
    def open_date_picker_for_lineedit(self, line_input: QLineEdit):
        """Open a calendar picker dialog for QLineEdit date fields."""
        # Try to parse existing date, otherwise use current date
        current_text = line_input.text().strip()
        if current_text:
            try:
                initial_date = QDate.fromString(current_text, "dd-MM-yyyy")
                if not initial_date.isValid():
                    initial_date = QDate.currentDate()
            except:
                initial_date = QDate.currentDate()
        else:
            initial_date = QDate.currentDate()
        
        dialog = DatePickerDialog(self, initial_date)
        if dialog.exec():
            selected_date = dialog.get_date()
            line_input.setText(selected_date.toString("dd-MM-yyyy"))
    
    def clear_date_input(self, date_input: QDateEdit):
        """Completely clear a date input field."""
        date_input.setDate(QDate(2000, 1, 1))
        date_input.clear()
    
    def load_last_invoice_details(self):
        """Load company and bank details from the last saved invoice."""
        invoices = self.db.get_all_invoices()
        if invoices:
            last_invoice = invoices[-1]
            self.company_name_input.setText(last_invoice.company_name)
            self.company_address_input.setText(last_invoice.company_address)
            self.company_gstin_input.setText(last_invoice.company_gstin)
            self.company_phone_input.setText(last_invoice.company_phone)
            self.company_email_input.setText(last_invoice.company_email)
            self.udyam_input.setText(last_invoice.udyam_registration)
            self.pan_input.setText(last_invoice.pan_number)
            self.bank_account_holder_input.setText(last_invoice.bank_account_holder_name)
            self.bank_account_input.setText(last_invoice.bank_account_number)
            self.bank_branch_name_input.setText(last_invoice.bank_branch_name)
            self.bank_branch_ifsc_input.setText(last_invoice.bank_branch_ifsc)
            self.bank_branch_address_input.setText(last_invoice.bank_branch_address)
        else:
            # Load from config if no previous invoice
            self.company_name_input.setText(self.config.get('company_name', ''))
            self.company_address_input.setText(self.config.get('company_address', ''))
            self.company_gstin_input.setText(self.config.get('company_gstin', ''))
            self.company_phone_input.setText(self.config.get('company_phone', ''))
            self.company_email_input.setText(self.config.get('company_email', ''))
            self.udyam_input.setText(self.config.get('udyam_registration', ''))
            self.pan_input.setText(self.config.get('pan_number', ''))
            self.bank_account_holder_input.setText(self.config.get('bank_account_holder_name', ''))
            self.bank_account_input.setText(self.config.get('bank_account_number', ''))
            self.bank_branch_name_input.setText(self.config.get('bank_branch_name', ''))
            self.bank_branch_ifsc_input.setText(self.config.get('bank_branch_ifsc', ''))
            self.bank_branch_address_input.setText(self.config.get('bank_branch_address', ''))

    def open_output_folder(self):
        from .pdf_generator import OUTPUT_DIR
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(OUTPUT_DIR)))


def main():
    app = QApplication(sys.argv)
    window = InvoiceApp(); window.show(); sys.exit(app.exec())

if __name__ == "__main__":
    main()

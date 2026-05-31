"""
Invoice data models, config, and database management (aligned with updated PDF/UI):
- Adds Challan No/Date
- Adds Invoice To GSTIN (customer_gstin) and Ship To block (name/address/gstin)
"""
import sqlite3
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# Determine DATA_DIR based on environment
def get_data_dir():
    if hasattr(sys, '_MEIPASS'):
        return Path(sys.executable).parent / "data"
    
    local_dir = Path(__file__).parent.parent / "data"
    try:
        local_dir.mkdir(parents=True, exist_ok=True)
        return local_dir
    except (PermissionError, OSError):
        pass
        
    home_dir = os.environ.get("HOME")
    if home_dir:
        try:
            android_dir = Path(home_dir) / "data"
            android_dir.mkdir(parents=True, exist_ok=True)
            return android_dir
        except (PermissionError, OSError):
            pass
            
    import tempfile
    return Path(tempfile.gettempdir()) / "data"

DATA_DIR = get_data_dir()
DB_PATH = DATA_DIR / "invoices.db"
CONFIG_PATH = DATA_DIR / "config.json"


class LineItem:
    """Represents a single line item in an invoice with per-item tax rates."""
    def __init__(self, description: str, hsn: str, qty: float, uom: str, unit_price: float, sgst_rate: float = 0.0, cgst_rate: float = 0.0):
        self.description = description
        self.hsn = hsn
        self.qty = qty
        self.uom = uom
        self.unit_price = unit_price
        self.sgst_rate = sgst_rate
        self.cgst_rate = cgst_rate

    @property
    def total_price(self) -> float:
        return self.qty * self.unit_price

    @property
    def sgst_amount(self) -> float:
        return self.total_price * (self.sgst_rate / 100.0)

    @property
    def cgst_amount(self) -> float:
        return self.total_price * (self.cgst_rate / 100.0)

    @property
    def item_total_with_tax(self) -> float:
        return self.total_price + self.sgst_amount + self.cgst_amount

    # Backward-compatible alias
    @property
    def total_amount(self) -> float:
        return self.total_price

    def to_dict(self) -> Dict:
        return {
            "description": self.description,
            "hsn": self.hsn,
            "qty": self.qty,
            "uom": self.uom,
            "unit_price": self.unit_price,
            "sgst_rate": self.sgst_rate,
            "cgst_rate": self.cgst_rate,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "LineItem":
        return cls(
            description=data.get("description", ""),
            hsn=data.get("hsn", ""),
            qty=float(data.get("qty", 0)),
            uom=data.get("uom", ""),
            unit_price=float(data.get("unit_price", 0)),
            sgst_rate=float(data.get("sgst_rate", 0.0)),
            cgst_rate=float(data.get("cgst_rate", 0.0)),
        )


class Invoice:
    """Represents a complete invoice aligned to PDF generator and UI."""
    def __init__(self,
                 invoice_number: str,
                 invoice_date: str,
                 po_number: str = "",
                 po_date: str = "",
                 company_name: str = "",
                 company_address: str = "",
                 company_gstin: str = "",
                 company_phone: str = "",
                 company_email: str = "",
                 udyam_registration: str = "",
                 pan_number: str = "",
                 # Invoice To
                 customer_name: str = "",
                 customer_address: str = "",
                 customer_gstin: str = "",
                 # Ship To
                 ship_to_name: str = "",
                 ship_to_address: str = "",
                 ship_to_gstin: str = "",
                 # Challan
                 challan_number: str = "",
                 challan_date: str = "",
                 # Additional Info (2 rows for user notes)
                 additional_info_line1: str = "",
                 additional_info_line2: str = "",
                 # Bank
                 bank_account_number: str = "",
                 bank_account_holder_name: str = "",
                 bank_branch_name: str = "",
                 bank_branch_ifsc: str = "",
                 bank_branch_address: str = "",
                 # Tax
                 sgst_rate: float = 9.0,
                 cgst_rate: float = 9.0,
                 jurisdiction_note: str = "Subject to Vadodara Jurisdiction",
                 ):
        self.invoice_number = invoice_number
        self.invoice_date = invoice_date
        self.po_number = po_number
        self.po_date = po_date
        self.company_name = company_name
        self.company_address = company_address
        self.company_gstin = company_gstin
        self.company_phone = company_phone
        self.company_email = company_email
        self.udyam_registration = udyam_registration
        self.pan_number = pan_number
        # Invoice To
        self.customer_name = customer_name
        self.customer_address = customer_address
        self.customer_gstin = customer_gstin
        # Ship To
        self.ship_to_name = ship_to_name
        self.ship_to_address = ship_to_address
        self.ship_to_gstin = ship_to_gstin
        # Challan
        self.challan_number = challan_number
        self.challan_date = challan_date
        # Additional Info
        self.additional_info_line1 = additional_info_line1
        self.additional_info_line2 = additional_info_line2
        # Bank
        self.bank_account_number = bank_account_number
        self.bank_account_holder_name = bank_account_holder_name
        self.bank_branch_name = bank_branch_name
        self.bank_branch_ifsc = bank_branch_ifsc
        self.bank_branch_address = bank_branch_address
        # Tax
        self.sgst_rate = sgst_rate
        self.cgst_rate = cgst_rate
        self.jurisdiction_note = jurisdiction_note
        self.line_items: List[LineItem] = []

    def add_item(self, item: LineItem):
        self.line_items.append(item)

    @property
    def subtotal(self) -> float:
        return sum(item.total_price for item in self.line_items)

    @property
    def sgst_amount(self) -> float:
        """Calculate total SGST from all line items."""
        return sum(item.sgst_amount for item in self.line_items)

    @property
    def cgst_amount(self) -> float:
        """Calculate total CGST from all line items."""
        return sum(item.cgst_amount for item in self.line_items)

    @property
    def grand_total(self) -> float:
        """Total with per-item taxes."""
        return self.subtotal + self.sgst_amount + self.cgst_amount

    # Backward-compatible alias
    @property
    def gst_number(self) -> str:
        return getattr(self, "company_gstin", "")

    def to_dict(self) -> Dict:
        return {
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date,
            "po_number": self.po_number,
            "po_date": self.po_date,
            "company_name": self.company_name,
            "company_address": self.company_address,
            "company_gstin": self.company_gstin,
            "company_phone": self.company_phone,
            "company_email": self.company_email,
            "udyam_registration": self.udyam_registration,
            "pan_number": self.pan_number,
            "customer_name": self.customer_name,
            "customer_address": self.customer_address,
            "customer_gstin": self.customer_gstin,
            "ship_to_name": self.ship_to_name,
            "ship_to_address": self.ship_to_address,
            "ship_to_gstin": self.ship_to_gstin,
            "challan_number": self.challan_number,
            "challan_date": self.challan_date,
            "additional_info_line1": self.additional_info_line1,
            "additional_info_line2": self.additional_info_line2,
            "bank_account_number": self.bank_account_number,
            "bank_account_holder_name": self.bank_account_holder_name,
            "bank_branch_name": self.bank_branch_name,
            "bank_branch_ifsc": self.bank_branch_ifsc,
            "bank_branch_address": self.bank_branch_address,
            "sgst_rate": self.sgst_rate,
            "cgst_rate": self.cgst_rate,
            "jurisdiction_note": self.jurisdiction_note,
            "line_items": [item.to_dict() for item in self.line_items],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Invoice":
        inv = cls(
            invoice_number=data.get("invoice_number", ""),
            invoice_date=data.get("invoice_date", ""),
            po_number=data.get("po_number", ""),
            po_date=data.get("po_date", ""),
            company_name=data.get("company_name", ""),
            company_address=data.get("company_address", ""),
            company_gstin=data.get("company_gstin", ""),
            company_phone=data.get("company_phone", ""),
            company_email=data.get("company_email", ""),
            udyam_registration=data.get("udyam_registration", ""),
            pan_number=data.get("pan_number", ""),
            customer_name=data.get("customer_name", ""),
            customer_address=data.get("customer_address", ""),
            customer_gstin=data.get("customer_gstin", ""),
            ship_to_name=data.get("ship_to_name", ""),
            ship_to_address=data.get("ship_to_address", ""),
            ship_to_gstin=data.get("ship_to_gstin", ""),
            challan_number=data.get("challan_number", ""),
            challan_date=data.get("challan_date", ""),
            additional_info_line1=data.get("additional_info_line1", ""),
            additional_info_line2=data.get("additional_info_line2", ""),
            bank_account_number=data.get("bank_account_number", ""),
            bank_account_holder_name=data.get("bank_account_holder_name", ""),
            bank_branch_name=data.get("bank_branch_name", ""),
            bank_branch_ifsc=data.get("bank_branch_ifsc", ""),
            bank_branch_address=data.get("bank_branch_address", ""),
            sgst_rate=float(data.get("sgst_rate", 9.0)),
            cgst_rate=float(data.get("cgst_rate", 9.0)),
            jurisdiction_note=data.get("jurisdiction_note", "Subject to Vadodara Jurisdiction"),
        )
        for item_data in data.get("line_items", []):
            inv.add_item(LineItem.from_dict(item_data))
        return inv


class ConfigManager:
    """Persist simple app config (defaults, logo path, optional font)."""
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._data = {
            "company_name": "",
            "company_address": "",
            "company_gstin": "",
            "company_phone": "",
            "company_email": "",
            "pan_number": "",
            "udyam_registration": "",
            "bank_account_number": "",
            "bank_account_holder_name": "",
            "bank_branch_name": "",
            "bank_branch_ifsc": "",
            "bank_branch_address": "",
            "logo_path": "",
            "font_path": "",  # optional Unicode font path for ₹
            "invoice_prefix": "INV",
            "series_year": True,
            "series_width": 4,
            # Email sending
            "smtp_host": "",
            "smtp_port": 587,
            "smtp_user": "",
            "smtp_password": "",
            "smtp_use_tls": True,
            "from_name": "",
            "from_email": "",
        }
        self.load()

    def load(self):
        if CONFIG_PATH.exists():
            try:
                self._data.update(json.loads(CONFIG_PATH.read_text(encoding='utf-8')))
            except Exception:
                pass

    def save(self):
        CONFIG_PATH.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding='utf-8')

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value


class InvoiceDB:
    """SQLite database manager for invoices."""
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT UNIQUE NOT NULL,
                invoice_date TEXT NOT NULL,
                company_name TEXT,
                company_address TEXT,
                customer_name TEXT,
                customer_address TEXT,
                company_gstin TEXT,
                pan_number TEXT,
                data JSON NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.commit()

    def save_invoice(self, invoice: Invoice) -> bool:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO invoices
                    (invoice_number, invoice_date, company_name, company_address,
                     customer_name, customer_address, company_gstin, pan_number, data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invoice.invoice_number,
                        invoice.invoice_date,
                        invoice.company_name,
                        invoice.company_address,
                        invoice.customer_name,
                        invoice.customer_address,
                        invoice.company_gstin,
                        invoice.pan_number,
                        json.dumps(invoice.to_dict(), ensure_ascii=False),
                    ),
                )
                conn.commit()
            return True
        except Exception as e:
            print(f"Error saving invoice: {e}")
            return False

    def get_invoice(self, invoice_number: str) -> Optional[Invoice]:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT data FROM invoices WHERE invoice_number = ?", (invoice_number,))
                row = cursor.fetchone()
                if row:
                    return Invoice.from_dict(json.loads(row[0]))
        except Exception as e:
            print(f"Error retrieving invoice: {e}")
        return None

    def get_all_invoices(self) -> List[Invoice]:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT data FROM invoices ORDER BY created_at DESC")
                return [Invoice.from_dict(json.loads(row[0])) for row in cursor.fetchall()]
        except Exception as e:
            print(f"Error retrieving invoices: {e}")
        return []

    def delete_invoice(self, invoice_number: str) -> bool:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM invoices WHERE invoice_number = ?", (invoice_number,))
                conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting invoice: {e}")
            return False

    def get_unique_customers(self) -> Dict[str, Dict]:
        """Get all unique customers with their details (address and GSTIN).
        Returns dict: {customer_name: {address: str, gstin: str, ship_to_name: str, ship_to_address: str, ship_to_gstin: str}}
        """
        customers = {}
        try:
            with sqlite3.connect(DB_PATH) as conn:
                cursor = conn.cursor()
                # Get data from JSON column
                cursor.execute("""
                    SELECT DISTINCT data FROM invoices
                    WHERE customer_name IS NOT NULL AND customer_name != ''
                    ORDER BY customer_name
                """)
                for row in cursor.fetchall():
                    try:
                        invoice_data = json.loads(row[0])
                        customer_name = invoice_data.get('customer_name', '')
                        if customer_name and customer_name not in customers:
                            customers[customer_name] = {
                                'address': invoice_data.get('customer_address', ''),
                                'gstin': invoice_data.get('customer_gstin', ''),
                                'ship_to_name': invoice_data.get('ship_to_name', ''),
                                'ship_to_address': invoice_data.get('ship_to_address', ''),
                                'ship_to_gstin': invoice_data.get('ship_to_gstin', ''),
                            }
                    except Exception:
                        pass
        except Exception as e:
            print(f"Error retrieving unique customers: {e}")
        return customers

    def get_next_invoice_number(self, prefix: str = "INV", series_year: bool = True, width: int = 4) -> str:
        year = datetime.now().strftime('%Y')
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            like_pattern = f"{prefix}-{'%' if series_year else ''}%"
            cursor.execute("SELECT invoice_number FROM invoices WHERE invoice_number LIKE ?", (like_pattern,))
            nums = []
            for (inv_num,) in cursor.fetchall():
                try:
                    parts = inv_num.split('-')
                    n = int(parts[-1])
                    if series_year:
                        if len(parts) >= 3 and parts[-2] == year:
                            nums.append(n)
                    else:
                        nums.append(n)
                except Exception:
                    pass
            next_n = (max(nums) + 1) if nums else 1
        return f"{prefix}-{year}-{str(next_n).zfill(width)}" if series_year else f"{prefix}-{str(next_n).zfill(width)}"

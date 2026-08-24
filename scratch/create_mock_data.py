import csv
import sys
from pathlib import Path

# Add project root to python path
sys.path.append(str(Path(__file__).parent.parent))

from core.config import settings

desktop_path = settings.desktop_dir
target_file = desktop_path / "transactions.csv"

# Mock financial data: Date, Description, Category, Amount (positive for revenue, negative for expense)
transactions = [
    ["Date", "Description", "Category", "Amount"],
    ["2026-08-01", "Client Consulting Invoice #101", "Revenue", "2500.00"],
    ["2026-08-02", "Office Rent Payment", "Rent", "-1200.00"],
    ["2026-08-03", "Software Subscription (Adobe)", "Software", "-49.99"],
    ["2026-08-04", "Local Soccer Team Sponsorship", "Marketing", "-350.00"],
    ["2026-08-05", "Client Website Maintenance #102", "Revenue", "850.00"],
    ["2026-08-06", "Office Stationery & Supplies", "Office Expense", "-120.50"],
    ["2026-08-08", "Consulting Retainer Fee", "Revenue", "3000.00"],
    ["2026-08-10", "California Franchise Tax Board (FTB)", "Tax", "-800.00"],
    ["2026-08-12", "Electricity & Utility Bill", "Utilities", "-210.30"],
    ["2026-08-15", "Payroll Withholding (PIT & SDI)", "Payroll", "-1500.00"],
    ["2026-08-18", "Client Custom Dev Work #103", "Revenue", "4500.00"],
    ["2026-08-20", "Hardware Upgrade (SSD)", "Office Expense", "-180.00"],
    ["2026-08-22", "Coffee and Snacks for Team Meeting", "Meals", "-45.60"],
    ["2026-08-24", "Monthly Bookkeeping Software Fee", "Software", "-99.00"]
]

try:
    with open(target_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(transactions)
    print(f"[SUCCESS] Mock transactions file created at: {target_file}")
except Exception as e:
    print(f"[ERROR] Failed to write mock transactions file: {e}")

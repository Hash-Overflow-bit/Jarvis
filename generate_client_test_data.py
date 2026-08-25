import os
import csv
import random
from pathlib import Path
from datetime import datetime, timedelta

def generate_test_data():
    desktop_dir = Path.home() / "Desktop"
    
    print(f"Generating test data on: {desktop_dir}")
    
    # 1. CPA Compliance Audit Data
    print("Generating CPA compliance document...")
    ca_compliance_path = desktop_dir / "ca_compliance_2026.md"
    ca_compliance_path.write_text("""# California Franchise Tax Board (FTB) Compliance 2026

## 1. State Income Tax Withholding
Employers are required to withhold state income tax for all employees residing in or performing services within California. The 2026 withholding schedules require all resident employees earning over $25,000 annually to have a minimum of 4.5% withheld for state taxes.

## 2. Minimum Franchise Tax
Every corporation that is incorporated, registered, or doing business in California must pay a minimum franchise tax of $800.

## 3. Compliance Timelines
- Q1 Estimated Tax: April 15, 2026
- Q2 Estimated Tax: June 15, 2026
- Q3 Estimated Tax: September 15, 2026
- Q4 Estimated Tax: December 15, 2026

## 4. Audit Triggers
Failure to allocate state tax withholdings for California residents will result in automatic FTB audits.
""")

    print("Generating Q3 payroll CSV (approx 5,000 rows)...")
    payroll_path = desktop_dir / "payroll_Q3_2026.csv"
    with open(payroll_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Employee_ID", "Name", "State", "Gross_Pay", "Fed_Tax", "State_Tax"])
        
        for i in range(1, 5001):
            emp_id = f"EMP{i:04d}"
            name = f"Employee {i}"
            state = random.choices(["CA", "NY", "TX", "WA"], weights=[0.4, 0.2, 0.2, 0.2])[0]
            gross = round(random.uniform(25000, 150000), 2)
            fed_tax = round(gross * 0.22, 2)
            
            # INJECT COMPLIANCE VIOLATION: 
            # 5% chance a CA employee has 0.00 State_Tax withheld despite earning > $25k
            if state == "CA" and random.random() < 0.05:
                state_tax = 0.00
            else:
                state_tax = round(gross * (0.045 if state == "CA" else 0.03), 2) if state != "TX" and state != "WA" else 0.00
                
            writer.writerow([emp_id, name, state, gross, fed_tax, state_tax])


    # 2. Bookkeeper Reconciliation Data
    print("Generating transaction logs...")
    transactions_dir = desktop_dir / "transactions"
    transactions_dir.mkdir(exist_ok=True)
    
    for batch in range(1, 4):
        batch_path = transactions_dir / f"august_batch_{batch}.csv"
        with open(batch_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Description", "Amount", "Ledger_Class"])
            
            start_date = datetime(2026, 8, 1)
            for i in range(10000):
                tx_date = (start_date + timedelta(days=random.randint(0, 30))).strftime("%Y-%m-%d")
                tx_class = random.choice(["Revenue", "Expense", "Liability", "Asset"])
                
                if tx_class == "Revenue":
                    amount = round(random.uniform(100, 5000), 2)
                    desc = f"Client Invoice {random.randint(1000, 9999)}"
                else:
                    amount = round(random.uniform(-5000, -10), 2)
                    desc = f"Vendor Payment {random.randint(100, 999)}"
                    
                writer.writerow([tx_date, desc, amount, tx_class])

    
    # 3. Data Hygiene / Retention Data
    print("Generating legacy ledgers...")
    legacy_dir = desktop_dir / "legacy_ledgers"
    legacy_dir.mkdir(exist_ok=True)
    
    years = [2017, 2018, 2019, 2025]
    for year in years:
        legacy_path = legacy_dir / f"transactions_{year}.csv"
        with open(legacy_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Description", "Amount"])
            
            start_date = datetime(year, 1, 1)
            for i in range(500):
                tx_date = (start_date + timedelta(days=random.randint(0, 364))).strftime("%Y-%m-%d")
                amount = round(random.uniform(-1000, 1000), 2)
                writer.writerow([tx_date, f"Legacy Entry {i}", amount])
                
    print("\nData generation complete! The files are ready on the Desktop.")

if __name__ == "__main__":
    generate_test_data()

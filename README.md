# Diligent — E-commerce Synthetic Data Exercise (live link- https://e-com-diligent-pmpnjeudecefvgqesgrczb.streamlit.app/)

note- because of some login issues i could not use cursor ide


This project demonstrates:
- Generating synthetic e-commerce data (customers, categories, products, orders, order_items)
- Saving the data as CSV files
- Ingesting the CSVs into a SQLite database (`ecom.db`)
- Running SQL join queries
- Generating analytical reports (top customers, category sales, order-line details)


---


## 📁 Project Structure


diligent/
├── data/
│ ├── customers.csv
│ ├── categories.csv
│ ├── products.csv
│ ├── orders.csv
│ ├── order_items.csv
│ └── ecom.db
├── scripts/
│ ├── data_gen.py
│ ├── ingest_sqlite.py
│ ├── query_join.py
│ └── reports_export.py
└── README.md


---

## 🧰 Features of the Streamlit Application

🔗 Multi-table Join Builder

Select any 2+ tables

Arrange join order

Choose columns to include

Select join keys and join types

Preview sample data

Run join and download result CSV

🧾 SQL Console

Run read-only SQL SELECT queries

View and download results

📈 Analytics Dashboard

View join operations, query logs, and chart events

Daily usage trends

Filter logs by type/date

Download analytics CSV


Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\Activate
python -m pip install pandas faker


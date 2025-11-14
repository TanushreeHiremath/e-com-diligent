# Diligent — E-commerce Synthetic Data Exercise (live link- https://jobyaari-chatbot-cdsfxsakhc9fygdwdhtu8u.streamlit.app/)


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


## ⚙️ Setup (Windows / PowerShell)


### 1. Create & activate virtual environment


python -m venv .venv
.\.venv\Scripts\Activate


---


### 2. Install required libraries


python -m pip install pandas faker


---


## 🏗️ Generate Synthetic CSV Data


python .\scripts\data_gen.py


---


## 🗄️ Ingest CSVs into SQLite Database


python .\scripts\ingest_sqlite.py


---


## 🔍 Preview Database (Join Sample)


python .\scripts\query_join.py


---


## 📊 Export Analytical Reports


python .\scripts\reports_export.py


---


## 📌 Notes


- If your virtual environment breaks or pandas cannot be imported, recreate the venv:


Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\Activate
python -m pip install pandas faker


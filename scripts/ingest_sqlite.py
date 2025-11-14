import sqlite3
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
DB = DATA / "ecom.db"

# Read CSVs
customers = pd.read_csv(DATA / "customers.csv")
categories = pd.read_csv(DATA / "categories.csv")
products = pd.read_csv(DATA / "products.csv")
orders = pd.read_csv(DATA / "orders.csv")
order_items = pd.read_csv(DATA / "order_items.csv")

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.executescript("""
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS order_items;

CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY,
  name TEXT,
  email TEXT,
  created_at TEXT
);

CREATE TABLE categories (
  category_id INTEGER PRIMARY KEY,
  name TEXT
);

CREATE TABLE products (
  product_id INTEGER PRIMARY KEY,
  name TEXT,
  category_id INTEGER,
  price REAL,
  FOREIGN KEY(category_id) REFERENCES categories(category_id)
);

CREATE TABLE orders (
  order_id INTEGER PRIMARY KEY,
  customer_id INTEGER,
  order_date TEXT,
  total_amount REAL,
  FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
  order_item_id INTEGER PRIMARY KEY,
  order_id INTEGER,
  product_id INTEGER,
  quantity INTEGER,
  unit_price REAL,
  FOREIGN KEY(order_id) REFERENCES orders(order_id),
  FOREIGN KEY(product_id) REFERENCES products(product_id)
);
""")

customers.to_sql("customers", conn, if_exists="append", index=False)
categories.to_sql("categories", conn, if_exists="append", index=False)
products.to_sql("products", conn, if_exists="append", index=False)
orders.to_sql("orders", conn, if_exists="append", index=False)
order_items.to_sql("order_items", conn, if_exists="append", index=False)

conn.commit()

for t in ["customers","categories","products","orders","order_items"]:
    c = pd.read_sql_query(f"SELECT count(*) AS cnt FROM {t}", conn)
    print(f"{t}: {int(c['cnt'][0])} rows")
    print(pd.read_sql_query(f"SELECT * FROM {t} LIMIT 5", conn))
    print("-"*40)

conn.close()

print("SQLite DB created at diligent/data/ecom.db")

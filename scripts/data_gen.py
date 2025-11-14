from faker import Faker
import pandas as pd
import random
from pathlib import Path

fake = Faker()

# Output folder: diligent/data/
out = Path(__file__).resolve().parents[1] / "data"
out.mkdir(parents=True, exist_ok=True)

# ----------------- CUSTOMERS -----------------
customers = []
for i in range(1, 201):
    customers.append({
        "customer_id": i,
        "name": fake.name(),
        "email": fake.unique.email(),
        "created_at": fake.date_between(start_date='-3y', end_date='today').isoformat()
    })
pd.DataFrame(customers).to_csv(out / "customers.csv", index=False)

# ----------------- CATEGORIES -----------------
categories = []
for i in range(1, 21):
    categories.append({
        "category_id": i,
        "name": fake.word().capitalize()
    })
pd.DataFrame(categories).to_csv(out / "categories.csv", index=False)

# ----------------- PRODUCTS -----------------
products = []
for i in range(1, 301):
    cat = random.choice(categories)["category_id"]
    products.append({
        "product_id": i,
        "name": fake.word().capitalize() + " " + fake.word().capitalize(),
        "category_id": cat,
        "price": round(random.uniform(5.0, 500.0), 2)
    })
pd.DataFrame(products).to_csv(out / "products.csv", index=False)

# ----------------- ORDERS + ORDER ITEMS -----------------
orders = []
order_items = []
order_item_id = 1

for order_id in range(1, 1001):
    cust = random.choice(customers)["customer_id"]
    order_date = fake.date_between(start_date='-2y', end_date='today')

    num_items = random.randint(1, 5)
    items = random.sample(products, num_items)

    total = 0
    for prod in items:
        qty = random.randint(1, 4)
        unit_price = prod["price"]
        total += qty * unit_price

        order_items.append({
            "order_item_id": order_item_id,
            "order_id": order_id,
            "product_id": prod["product_id"],
            "quantity": qty,
            "unit_price": unit_price
        })
        order_item_id += 1

    orders.append({
        "order_id": order_id,
        "customer_id": cust,
        "order_date": order_date.isoformat(),
        "total_amount": round(total, 2)
    })

pd.DataFrame(orders).to_csv(out / "orders.csv", index=False)
pd.DataFrame(order_items).to_csv(out / "order_items.csv", index=False)

print("CSV files generated inside diligent/data/")

import mysql.connector
from datetime import date

db_config = {
    'host': 'localhost',
    'user': '.', 
    'password': '.',  
    'database': 'restaurant' 
}

conn = mysql.connector.connect(**db_config)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS daily_summary (
        summary_date DATE PRIMARY KEY,
        total_amount DECIMAL(10, 2)
    )
''')
conn.commit()

def get_customer_details():
    print("\nPlease Enter Customer Details:")
    name = input("Name: ")
    mobile = input("Mobile Number: ")
    cursor.execute('''
        INSERT INTO customers (name, mobile)
        VALUES (%s, %s)
    ''', (name, mobile))
    conn.commit()
    return cursor.lastrowid

def menu():
    print("\t\t\t░M░e░n░u░")
    print("\n1. Breakfast")
    print("2. Main Course")
    print("3. Dessert")
    print("4. Print Bill")
    print("5. Today's Summary")
    print("6. Quit")
    choice = input("Enter Your Choice: ").strip()
    return choice

def display_menu(items):
    for idx, (item, price) in enumerate(items.items(), start=1):
        print(f"{idx}. {item:<30} {price}")
    print()

def handle_order(menu_items, current_order):
    display_menu(menu_items)
    selected_items = input("Enter item numbers separated by commas: ").strip()
    if not selected_items:
        print("No items selected.")
        return current_order
    for item_no in map(int, selected_items.split(',')):
        if 1 <= item_no <= len(menu_items):
            item_name = list(menu_items.keys())[item_no - 1]
            price_per_item = list(menu_items.values())[item_no - 1]
            quantity = int(input(f"Enter quantity for {item_name}: "))
            total_price = quantity * price_per_item
            current_order.append((item_name, quantity, price_per_item, total_price))
            print(f"Added {quantity} x {item_name} to your order.")
        else:
            print(f"Invalid item number: {item_no}")
    return current_order

def update_daily_summary(total_amount):
    today = date.today()
    cursor.execute('''
        INSERT INTO daily_summary (summary_date, total_amount)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE total_amount = total_amount + %s
    ''', (today, total_amount, total_amount))
    conn.commit()

def view_daily_summary():
    print("\n---------------- Daily Summary ----------------")
    print(f"{'Date':<15}{'Total Amount'}")
    print("-" * 30)
    cursor.execute('SELECT summary_date, total_amount FROM daily_summary ORDER BY summary_date DESC')
    for summary_date, total_amount in cursor.fetchall():
        print(f"{summary_date:<15}{total_amount}")
    print("-" * 30)

def generate_bill(current_order, customer_id):
    print("\n--------------------------- BILL -----------------------------")
    print(f"Customer ID: {customer_id}")
    print(f"{'Item':<30}{'Quantity':<10}{'Price/Item':<15}{'Total'}")
    print("-" * 60)
    total_amount = 0
    for item_name, quantity, price_per_item, total_price in current_order:
        print(f"{item_name:<30}{quantity:<10}{price_per_item:<15}{total_price}")
        total_amount += total_price
        cursor.execute('''
            INSERT INTO orders (customer_id, item_name, quantity, price_per_item, total_price)
            VALUES (%s, %s, %s, %s, %s)
        ''', (customer_id, item_name, quantity, price_per_item, total_price))
    conn.commit()
    
    gst = round(0.18 * total_amount, 2)
    grand_total = total_amount + gst
    print("-" * 60)
    print(f"{'Subtotal':<30}{'':<10}{'':<15}{total_amount}")
    print(f"{'GST (18%)':<30}{'':<10}{'':<15}{gst}")
    print(f"{'Grand Total':<30}{'':<10}{'':<15}{grand_total}")
    print("\nThanks for Visiting!")

    # Update daily summary
    update_daily_summary(grand_total)

def main():
    print("Welcome To Paisa Wasool Restaurant!")
    customer_id = get_customer_details()
    current_order = []
    while True:
        choice = menu()
        if choice == "1":
            print("\nWelcome To Breakfast Menu")
            breakfast_items = {
                "Coffee": 350, "Chai": 200, "Maggi": 250,
                "Italian Pasta": 350, "Paneer Tikka": 400,
                "Chilly Potato": 400, "Baby Corn": 400,
                "Spring Roll": 375, "Fried Momos": 450
            }
            current_order = handle_order(breakfast_items, current_order)
        elif choice == "2":
            print("\nWelcome To Main Course Menu")
            main_course_items = {
                "Veg Seekh Kabab": 400, "Kadhai Paneer": 850,
                "Malai Kofta": 850, "Dal Makhni": 850,
                "Butter Naan": 450, "Stuffed Kulcha": 450,
                "Paneer Makkhanwala": 1200, "Veg Biryani": 800,
                "Makke Di Roti Sarso Ka Saag": 1350
            }
            current_order = handle_order(main_course_items, current_order)
        elif choice == "3":
            print("\nWelcome To Dessert Menu")
            dessert_items = {
                "Kheer": 450, "Gulab Jamun": 700, "Rasgulla": 800,
                "Rasmalai": 1200, "Laddoo": 500,
                "Black Forest": 750, "Oreo Shake": 900,
                "Tutty Fruity": 600, "Chocolate Brownie": 850, "Marble Cake": 1200
            }
            current_order = handle_order(dessert_items, current_order)
        elif choice == "4":
            if current_order:
                generate_bill(current_order, customer_id)
                current_order = []
            else:
                print("No items ordered yet.")
        elif choice == "5":
            view_daily_summary()
        elif choice == "6":
            print("Exiting... Thank you for visiting!")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()

conn.close()

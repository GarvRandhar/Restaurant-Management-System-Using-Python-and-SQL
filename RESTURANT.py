import mysql.connector
import os
import logging
import configparser
from datetime import date, datetime
from tabulate import tabulate 
import bcrypt  
import re  
from decimal import Decimal, ROUND_HALF_UP

logging.basicConfig(
    filename='restaurant.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class DatabaseManager:
    def __init__(self, config_file='config.ini'):
        """Initialize database connection using configuration file"""
        try:
            self.config = configparser.ConfigParser()
            
            if not os.path.exists(config_file):
                self.config['DATABASE'] = {
                    'host': 'localhost',
                    'user': 'username',
                    'password': 'passwd',
                    'database': 'restaurant'
                }
                with open(config_file, 'w') as f:
                    self.config.write(f)
                print(f"Created default configuration file: {config_file}")
                print("Please update with your database credentials and restart.")
                exit(0)
            
            self.config.read(config_file)
            self.db_config = {
                'host': self.config['DATABASE']['host'],
                'user': self.config['DATABASE']['user'],
                'password': self.config['DATABASE']['password'],
                'database': self.config['DATABASE']['database']
            }
            
            self.conn = mysql.connector.connect(**self.db_config)
            self.cursor = self.conn.cursor(dictionary=True)
            
            self._initialize_database()
            logging.info("Database connection established successfully")
        
        except mysql.connector.Error as err:
            logging.error(f"Database error: {err}")
            print(f"Database error: {err}")
            exit(1)
    
    def _initialize_database(self):
        """Create necessary tables if they don't exist"""
        try:
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(100) NOT NULL,
                    role ENUM('admin', 'manager', 'waiter', 'cashier') NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS customers (
                    customer_id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    mobile VARCHAR(15) NOT NULL,
                    email VARCHAR(100),
                    loyalty_points INT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_visit TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS menu_categories (
                    category_id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(50) NOT NULL,
                    description TEXT
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS menu_items (
                    item_id INT AUTO_INCREMENT PRIMARY KEY,
                    category_id INT,
                    name VARCHAR(100) NOT NULL,
                    price DECIMAL(10, 2) NOT NULL,
                    description TEXT,
                    is_available BOOLEAN DEFAULT TRUE,
                    FOREIGN KEY (category_id) REFERENCES menu_categories(category_id)
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS tables (
                    table_id INT AUTO_INCREMENT PRIMARY KEY,
                    table_number INT NOT NULL UNIQUE,
                    capacity INT NOT NULL,
                    is_occupied BOOLEAN DEFAULT FALSE
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS reservations (
                    reservation_id INT AUTO_INCREMENT PRIMARY KEY,
                    customer_id INT,
                    table_id INT,
                    reservation_time DATETIME NOT NULL,
                    party_size INT NOT NULL,
                    status ENUM('confirmed', 'seated', 'completed', 'cancelled') DEFAULT 'confirmed',
                    notes TEXT,
                    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
                    FOREIGN KEY (table_id) REFERENCES tables(table_id)
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    order_id INT AUTO_INCREMENT PRIMARY KEY,
                    customer_id INT,
                    table_id INT,
                    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status ENUM('pending', 'preparing', 'served', 'paid') DEFAULT 'pending',
                    server_id INT,
                    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
                    FOREIGN KEY (table_id) REFERENCES tables(table_id),
                    FOREIGN KEY (server_id) REFERENCES users(user_id)
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS order_items (
                    order_item_id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id INT,
                    item_id INT,
                    quantity INT NOT NULL,
                    unit_price DECIMAL(10, 2) NOT NULL,
                    notes TEXT,
                    FOREIGN KEY (order_id) REFERENCES orders(order_id),
                    FOREIGN KEY (item_id) REFERENCES menu_items(item_id)
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS bills (
                    bill_id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id INT UNIQUE,
                    subtotal DECIMAL(10, 2) NOT NULL,
                    tax_amount DECIMAL(10, 2) NOT NULL,
                    discount_amount DECIMAL(10, 2) DEFAULT 0,
                    total_amount DECIMAL(10, 2) NOT NULL,
                    payment_method ENUM('cash', 'credit_card', 'debit_card', 'upi', 'other') DEFAULT 'cash',
                    payment_status ENUM('pending', 'completed', 'refunded') DEFAULT 'pending',
                    payment_time TIMESTAMP NULL,
                    FOREIGN KEY (order_id) REFERENCES orders(order_id)
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS inventory_items (
                    inventory_id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    quantity DECIMAL(10, 2) NOT NULL,
                    unit VARCHAR(20) NOT NULL,
                    reorder_level DECIMAL(10, 2) DEFAULT 0,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            ''')
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_summary (
                    summary_date DATE PRIMARY KEY,
                    total_orders INT DEFAULT 0,
                    total_revenue DECIMAL(10, 2) DEFAULT 0,
                    average_bill DECIMAL(10, 2) DEFAULT 0
                )
            ''')
            
            self.cursor.execute('SELECT COUNT(*) as count FROM menu_categories')
            if self.cursor.fetchone()['count'] == 0:
                categories = [
                    ('Breakfast', 'Morning delights to start your day'),
                    ('Main Course', 'Hearty meals for lunch and dinner'),
                    ('Dessert', 'Sweet treats to complete your meal')
                ]
                self.cursor.executemany(
                    'INSERT INTO menu_categories (name, description) VALUES (%s, %s)',
                    categories
                )
            
            self.cursor.execute('SELECT COUNT(*) as count FROM menu_items')
            if self.cursor.fetchone()['count'] == 0:
                self.cursor.execute('SELECT category_id, name FROM menu_categories')
                categories = {row['name']: row['category_id'] for row in self.cursor.fetchall()}
                
                breakfast_items = [
                    (categories['Breakfast'], 'Coffee', 350, 'Freshly brewed hot coffee'),
                    (categories['Breakfast'], 'Chai', 200, 'Traditional Indian tea with spices'),
                    (categories['Breakfast'], 'Maggi', 250, 'Classic instant noodles with vegetables'),
                    (categories['Breakfast'], 'Italian Pasta', 350, 'Pasta with homemade tomato sauce'),
                    (categories['Breakfast'], 'Paneer Tikka', 400, 'Grilled cottage cheese with spices'),
                    (categories['Breakfast'], 'Chilly Potato', 400, 'Spicy potato fries with bell peppers'),
                    (categories['Breakfast'], 'Baby Corn', 400, 'Crispy fried baby corn with spices'),
                    (categories['Breakfast'], 'Spring Roll', 375, 'Vegetable filled crispy rolls'),
                    (categories['Breakfast'], 'Fried Momos', 450, 'Deep-fried dumplings with spicy sauce')
                ]
                
                main_course_items = [
                    (categories['Main Course'], 'Veg Seekh Kabab', 400, 'Vegetable skewers grilled to perfection'),
                    (categories['Main Course'], 'Kadhai Paneer', 850, 'Cottage cheese in spicy gravy'),
                    (categories['Main Course'], 'Malai Kofta', 850, 'Cheese dumplings in rich cream sauce'),
                    (categories['Main Course'], 'Dal Makhni', 850, 'Black lentils cooked overnight'),
                    (categories['Main Course'], 'Butter Naan', 450, 'Indian bread with butter'),
                    (categories['Main Course'], 'Stuffed Kulcha', 450, 'Indian bread stuffed with potatoes'),
                    (categories['Main Course'], 'Paneer Makkhanwala', 1200, 'Cottage cheese in buttery tomato gravy'),
                    (categories['Main Course'], 'Veg Biryani', 800, 'Rice cooked with vegetables and spices'),
                    (categories['Main Course'], 'Makke Di Roti Sarso Ka Saag', 1350, 'Traditional Punjabi dish')
                ]
                
                dessert_items = [
                    (categories['Dessert'], 'Kheer', 450, 'Rice pudding with nuts'),
                    (categories['Dessert'], 'Gulab Jamun', 700, 'Deep-fried milk solids in sugar syrup'),
                    (categories['Dessert'], 'Rasgulla', 800, 'Cheese balls in sugar syrup'),
                    (categories['Dessert'], 'Rasmalai', 1200, 'Cheese patties in sweet milk'),
                    (categories['Dessert'], 'Laddoo', 500, 'Sweet ball-shaped dessert'),
                    (categories['Dessert'], 'Black Forest', 750, 'Chocolate cake with cherries'),
                    (categories['Dessert'], 'Oreo Shake', 900, 'Milkshake with Oreo cookies'),
                    (categories['Dessert'], 'Tutty Fruity', 600, 'Ice cream with mixed fruits'),
                    (categories['Dessert'], 'Chocolate Brownie', 850, 'Warm chocolate brownie'),
                    (categories['Dessert'], 'Marble Cake', 1200, 'Vanilla and chocolate swirl cake')
                ]
                
                all_items = breakfast_items + main_course_items + dessert_items
                self.cursor.executemany(
                    'INSERT INTO menu_items (category_id, name, price, description) VALUES (%s, %s, %s, %s)',
                    all_items
                )
            
            self.cursor.execute('SELECT COUNT(*) as count FROM tables')
            if self.cursor.fetchone()['count'] == 0:
                tables = [(i, 4) for i in range(1, 11)] 
                tables.extend([(i, 6) for i in range(11, 16)])  
                tables.append((16, 10))
                self.cursor.executemany(
                    'INSERT INTO tables (table_number, capacity) VALUES (%s, %s)',
                    tables
                )
            
            self.cursor.execute('SELECT COUNT(*) as count FROM users')
            if self.cursor.fetchone()['count'] == 0:
                password = "admin123"
                hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                self.cursor.execute(
                    'INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)',
                    ('admin', hashed_password, 'admin')
                )
                print("Created default admin user. Username: admin, Password: admin123")
                print("Please change this password after first login.")
            
            self.conn.commit()
        except mysql.connector.Error as err:
            self.conn.rollback()
            logging.error(f"Failed to initialize database: {err}")
            print(f"Failed to initialize database: {err}")
            exit(1)
    
    def execute_query(self, query, params=None, fetch=False):
        """Execute a query with error handling and transaction support"""
        try:
            self.cursor.execute(query, params)
            if fetch == 'one':
                return self.cursor.fetchone()
            elif fetch == 'all':
                return self.cursor.fetchall()
            else:
                self.conn.commit()
                return self.cursor.lastrowid
        except mysql.connector.Error as err:
            self.conn.rollback()
            logging.error(f"Query execution error: {err}")
            print(f"Database error: {err}")
            return None
    
    def close(self):
        """Close database connection"""
        if hasattr(self, 'conn') and self.conn.is_connected():
            self.cursor.close()
            self.conn.close()
            logging.info("Database connection closed")


class AuthManager:
    def __init__(self, db_manager):
        self.db = db_manager
        self.current_user = None
    
    def login(self, username, password):
        """Authenticate a user"""
        query = "SELECT user_id, username, password_hash, role FROM users WHERE username = %s"
        user = self.db.execute_query(query, (username,), 'one')
        
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            self.current_user = {
                'user_id': user['user_id'],
                'username': user['username'],
                'role': user['role']
            }
            logging.info(f"User {username} logged in successfully")
            return True
        
        logging.warning(f"Failed login attempt for username: {username}")
        return False
    
    def logout(self):
        """Log out the current user"""
        if self.current_user:
            logging.info(f"User {self.current_user['username']} logged out")
            self.current_user = None
        return True
    
    def create_user(self, username, password, role):
        """Create a new user with the given role"""
        if not self.is_admin():
            logging.warning(f"Non-admin user {self.current_user['username']} attempted to create a new user")
            return False, "Only administrators can create new users"
        
        check_query = "SELECT COUNT(*) as count FROM users WHERE username = %s"
        result = self.db.execute_query(check_query, (username,), 'one')
        
        if result and result['count'] > 0:
            return False, "Username already exists"
        
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        insert_query = "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)"
        user_id = self.db.execute_query(insert_query, (username, hashed_password, role))
        
        if user_id:
            logging.info(f"Created new user {username} with role {role}")
            return True, f"User {username} created successfully with role {role}"
        
        return False, "Failed to create user"
    
    def change_password(self, old_password, new_password):
        """Change the current user's password"""
        if not self.current_user:
            return False, "No user is logged in"
        
        query = "SELECT password_hash FROM users WHERE user_id = %s"
        user = self.db.execute_query(query, (self.current_user['user_id'],), 'one')
        
        if not user or not bcrypt.checkpw(old_password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            logging.warning(f"Failed password change attempt for user {self.current_user['username']}")
            return False, "Current password is incorrect"
        
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        update_query = "UPDATE users SET password_hash = %s WHERE user_id = %s"
        self.db.execute_query(update_query, (hashed_password, self.current_user['user_id']))
        
        logging.info(f"Password changed for user {self.current_user['username']}")
        return True, "Password changed successfully"
    
    def is_authenticated(self):
        """Check if a user is currently logged in"""
        return self.current_user is not None
    
    def is_admin(self):
        """Check if the current user is an admin"""
        return self.current_user and self.current_user['role'] == 'admin'
    
    def is_manager_or_above(self):
        """Check if the current user is a manager or admin"""
        return self.current_user and self.current_user['role'] in ['admin', 'manager']
    
    def get_current_user(self):
        """Get the current user's information"""
        return self.current_user


class CustomerManager:
    def __init__(self, db_manager):
        self.db = db_manager
    
    def add_customer(self, name, mobile, email=None):
        """Add a new customer to the database"""
        if not name or not mobile:
            return False, "Name and mobile number are required"
        
        if not re.match(r'^\d{10}$', mobile):
            return False, "Mobile number must be 10 digits"
        
        if email and not re.match(r'^\S+@\S+\.\S+$', email):
            return False, "Invalid email format"
        
        check_query = "SELECT customer_id FROM customers WHERE mobile = %s"
        existing = self.db.execute_query(check_query, (mobile,), 'one')
        
        if existing:
            return False, f"Customer with mobile {mobile} already exists (ID: {existing['customer_id']})"
        
        insert_query = """
            INSERT INTO customers (name, mobile, email)
            VALUES (%s, %s, %s)
        """
        customer_id = self.db.execute_query(insert_query, (name, mobile, email))
        
        if customer_id:
            logging.info(f"Added new customer: {name}, {mobile}")
            return True, customer_id
        
        return False, "Failed to add customer"
    
    def search_customers(self, search_term):
        """Search for customers by name or mobile number"""
        query = """
            SELECT customer_id, name, mobile, email, loyalty_points, last_visit
            FROM customers
            WHERE name LIKE %s OR mobile LIKE %s
            ORDER BY name
            LIMIT 20
        """
        search_param = f"%{search_term}%"
        results = self.db.execute_query(query, (search_param, search_param), 'all')
        return results
    
    def get_customer(self, customer_id):
        """Get a customer by ID"""
        query = """
            SELECT customer_id, name, mobile, email, loyalty_points, created_at, last_visit
            FROM customers
            WHERE customer_id = %s
        """
        return self.db.execute_query(query, (customer_id,), 'one')
    
    def update_customer(self, customer_id, name=None, mobile=None, email=None):
        """Update customer information"""
        customer = self.get_customer(customer_id)
        if not customer:
            return False, "Customer not found"
        
        name = name if name else customer['name']
        mobile = mobile if mobile else customer['mobile']
        email = email if email is not None else customer['email']
        
        if not re.match(r'^\d{10}$', mobile):
            return False, "Mobile number must be 10 digits"
        
        if email and not re.match(r'^\S+@\S+\.\S+$', email):
            return False, "Invalid email format"
        
        update_query = """
            UPDATE customers
            SET name = %s, mobile = %s, email = %s
            WHERE customer_id = %s
        """
        self.db.execute_query(update_query, (name, mobile, email, customer_id))
        
        logging.info(f"Updated customer ID {customer_id}")
        return True, "Customer updated successfully"
    
    def add_loyalty_points(self, customer_id, points):
        """Add loyalty points to a customer"""
        if points <= 0:
            return False, "Points must be positive"
        
        query = """
            UPDATE customers
            SET loyalty_points = loyalty_points + %s
            WHERE customer_id = %s
        """
        self.db.execute_query(query, (points, customer_id))
        
        logging.info(f"Added {points} loyalty points to customer ID {customer_id}")
        return True, f"Added {points} loyalty points"
    
    def use_loyalty_points(self, customer_id, points):
        """Use loyalty points from a customer's balance"""
        if points <= 0:
            return False, "Points must be positive"
        
        customer = self.get_customer(customer_id)
        if not customer:
            return False, "Customer not found"
        
        if customer['loyalty_points'] < points:
            return False, f"Customer only has {customer['loyalty_points']} points available"
        
        query = """
            UPDATE customers
            SET loyalty_points = loyalty_points - %s
            WHERE customer_id = %s
        """
        self.db.execute_query(query, (points, customer_id))
        
        logging.info(f"Used {points} loyalty points from customer ID {customer_id}")
        return True, f"Used {points} loyalty points"


class MenuManager:
    def __init__(self, db_manager):
        self.db = db_manager
    
    def get_categories(self):
        """Get all menu categories"""
        query = "SELECT category_id, name, description FROM menu_categories ORDER BY name"
        return self.db.execute_query(query, fetch='all')
    
    def get_menu_items(self, category_id=None):
        """Get menu items, optionally filtered by category"""
        if category_id:
            query = """
                SELECT m.item_id, m.name, m.price, m.description, m.is_available, 
                       c.name as category_name
                FROM menu_items m
                JOIN menu_categories c ON m.category_id = c.category_id
                WHERE m.category_id = %s
                ORDER BY m.name
            """
            return self.db.execute_query(query, (category_id,), 'all')
        else:
            query = """
                SELECT m.item_id, m.name, m.price, m.description, m.is_available, 
                       c.name as category_name
                FROM menu_items m
                JOIN menu_categories c ON m.category_id = c.category_id
                ORDER BY c.name, m.name
            """
            return self.db.execute_query(query, fetch='all')
    
    def add_menu_item(self, name, price, category_id, description="", is_available=True):
        """Add a new menu item"""
        if not name or not price or not category_id:
            return False, "Name, price, and category are required"
        
        try:
            price = float(price)
            if price <= 0:
                return False, "Price must be positive"
        except ValueError:
            return False, "Price must be a number"
        
        check_query = "SELECT COUNT(*) as count FROM menu_categories WHERE category_id = %s"
        result = self.db.execute_query(check_query, (category_id,), 'one')
        if not result or result['count'] == 0:
            return False, "Category does not exist"
        
        insert_query = """
            INSERT INTO menu_items (name, price, category_id, description, is_available)
            VALUES (%s, %s, %s, %s, %s)
        """
        item_id = self.db.execute_query(
            insert_query, 
            (name, price, category_id, description, is_available)
        )
        
        if item_id:
            logging.info(f"Added new menu item: {name}, price: {price}")
            return True, item_id
        
        return False, "Failed to add menu item"
    
    def update_menu_item(self, item_id, name=None, price=None, description=None, is_available=None):
        """Update a menu item"""
        query = "SELECT * FROM menu_items WHERE item_id = %s"
        item = self.db.execute_query(query, (item_id,), 'one')
        if not item:
            return False, "Menu item not found"
        
        name = name if name is not None else item['name']
        price = price if price is not None else item['price']
        description = description if description is not None else item['description']
        is_available = is_available if is_available is not None else item['is_available']
        
        try:
            price = float(price)
            if price <= 0:
                return False, "Price must be positive"
        except ValueError:
            return False, "Price must be a number"
        
        update_query = """
            UPDATE menu_items
            SET name = %s, price = %s, description = %s, is_available = %s
            WHERE item_id = %s
        """
        self.db.execute_query(update_query, (name, price, description, is_available, item_id))
        
        logging.info(f"Updated menu item ID {item_id}")
        return True, "Menu item updated successfully"
    
    def toggle_availability(self, item_id):
        """Toggle the availability of a menu item"""
        query = "SELECT is_available FROM menu_items WHERE item_id = %s"
        item = self.db.execute_query(query, (item_id,), 'one')
        if not item:
            return False, "Menu item not found"
        
        new_status = not item['is_available']
        update_query = "UPDATE menu_items SET is_available = %s WHERE item_id = %s"
        self.db.execute_query(update_query, (new_status, item_id))
        
        status_text = "available" if new_status else "unavailable"
        logging.info(f"Menu item ID {item_id} is now {status_text}")
        return True, f"Item is now {status_text}"


class OrderManager:
    def __init__(self, db_manager):
        self.db = db_manager
    
    def create_order(self, customer_id, table_id, server_id):
        """Create a new order"""
        if not customer_id or not table_id or not server_id:
            return False, "Customer, table, and server are required"
        
        insert_query = """
            INSERT INTO orders (customer_id, table_id, server_id, status)
            VALUES (%s, %s, %s, 'pending')
        """
        order_id = self.db.execute_query(insert_query, (customer_id, table_id, server_id))
        
        if order_id:
            self.db.execute_query(
                "UPDATE tables SET is_occupied = TRUE WHERE table_id = %s",
                (table_id,)
            )
            
            logging.info(f"Created new order ID {order_id} for customer {customer_id} at table {table_id}")
            return True, order_id
        
        return False, "Failed to create order"
    
    def add_order_item(self, order_id, item_id, quantity, notes=""):
        """Add an item to an order"""
        if not order_id or not item_id or not quantity:
            return False, "Order ID, item ID, and quantity are required"
        
        try:
            quantity = int(quantity)
            if quantity <= 0:
                return False, "Quantity must be positive"
        except ValueError:
            return False, "Quantity must be a number"
        
        check_query = "SELECT status FROM orders WHERE order_id = %s"
        order = self.db.execute_query(check_query, (order_id,), 'one')
        if not order:
            return False, "Order not found"
        
        if order['status'] == 'paid':
            return False, "Cannot add items to a paid order"
        
        item_query = "SELECT price, name FROM menu_items WHERE item_id = %s"
        item = self.db.execute_query(item_query, (item_id,), 'one')
        if not item:
            return False, "Menu item not found"
        
        insert_query = """
            INSERT INTO order_items (order_id, item_id, quantity, unit_price, notes)
            VALUES (%s, %s, %s, %s, %s)
        """
        order_item_id = self.db.execute_query(
            insert_query, 
            (order_id, item_id, quantity, item['price'], notes)
        )
        
        if order_item_id:
            logging.info(f"Added {quantity} x {item['name']} to order {order_id}")
            return True, order_item_id
        
        return False, "Failed to add item to order"
    
    def remove_order_item(self, order_item_id):
        """Remove an item from an order"""
        check_query = """
            SELECT oi.order_item_id, o.status, oi.quantity, mi.name 
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            JOIN menu_items mi ON oi.item_id = mi.item_id
            WHERE oi.order_item_id = %s
        """
        item = self.db.execute_query(check_query, (order_item_id,), 'one')
        if not item:
            return False, "Order item not found"
        
        if item['status'] == 'paid':
            return False, "Cannot modify a paid order"
        
        delete_query = "DELETE FROM order_items WHERE order_item_id = %s"
        self.db.execute_query(delete_query, (order_item_id,))
        
        logging.info(f"Removed {item['quantity']} x {item['name']} from order")
        return True, "Item removed from order"
    
    def update_order_status(self, order_id, status):
        """Update the status of an order"""
        valid_statuses = ['pending', 'preparing', 'served', 'paid']
        if status not in valid_statuses:
            return False, f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        
        update_query = "UPDATE orders SET status = %s WHERE order_id = %s"
        self.db.execute_query(update_query, (status, order_id))
        
        if status == 'paid':
            self.db.execute_query("""
                UPDATE tables SET is_occupied = FALSE 
                WHERE table_id = (SELECT table_id FROM orders WHERE order_id = %s)
            """, (order_id,))
        
        logging.info(f"Updated order {order_id} status to {status}")
        return True, f"Order status updated to {status}"
    
    def get_order_details(self, order_id):
        """Get detailed information about an order"""
        order_query = """
            SELECT o.order_id, o.order_date, o.status,
                   c.customer_id, c.name as customer_name, c.mobile as customer_mobile,
                   t.table_number, u.username as server_name
            FROM orders o
            JOIN customers c ON o.customer_id = c.customer_id
            JOIN tables t ON o.table_id = t.table_id
            JOIN users u ON o.server_id = u.user_id
            WHERE o.order_id = %s
        """
        order = self.db.execute_query(order_query, (order_id,), 'one')
        if not order:
            return None
        
        items_query = """
            SELECT oi.order_item_id, mi.name, oi.quantity, oi.unit_price, 
                   (oi.quantity * oi.unit_price) as total_price, oi.notes
            FROM order_items oi
            JOIN menu_items mi ON oi.item_id = mi.item_id
            WHERE oi.order_id = %s
        """
        items = self.db.execute_query(items_query, (order_id,), 'all')
        
        subtotal = sum(item['total_price'] for item in items) if items else 0
        
        bill_query = "SELECT * FROM bills WHERE order_id = %s"
        bill = self.db.execute_query(bill_query, (order_id,), 'one')
        
        order_details = {
            'order': order,
            'items': items,
            'subtotal': subtotal,
            'bill': bill
        }
        
        return order_details
    
    def get_active_orders(self):
        """Get all active (non-paid) orders"""
        query = """
            SELECT o.order_id, o.order_date, o.status,
                   c.name as customer_name, t.table_number,
                   COUNT(oi.order_item_id) as item_count,
                   SUM(oi.quantity * oi.unit_price) as subtotal
            FROM orders o
            JOIN customers c ON o.customer_id = c.customer_id
            JOIN tables t ON o.table_id = t.table_id
            LEFT JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.status != 'paid'
            GROUP BY o.order_id, o.order_date, o.status, c.name, t.table_number
            ORDER BY o.order_date
        """
        return self.db.execute_query(query, fetch='all')
    
    def create_bill(self, order_id, discount_amount=0, payment_method='cash'):
        """Create a bill for an order"""
        order_details = self.get_order_details(order_id)
        if not order_details:
            return False, "Order not found"

        if not order_details['items']:
            return False, "Cannot create bill for an order with no items"

        if order_details['order']['status'] == 'paid':
            return False, "Bill already exists for this order"

        try:
            subtotal = Decimal(str(order_details['subtotal']))
            discount_amount = Decimal(str(discount_amount or 0))

            if discount_amount < 0:
                return False, "Discount cannot be negative"
            if discount_amount > subtotal:
                return False, "Discount cannot exceed subtotal"

            tax_rate = Decimal('0.18')
            tax_amount = (subtotal * tax_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            total_amount = (subtotal + tax_amount - discount_amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            insert_query = """
                INSERT INTO bills (
                    order_id, subtotal, tax_amount, discount_amount, 
                    total_amount, payment_method, payment_status
                ) VALUES (%s, %s, %s, %s, %s, %s, 'pending')
            """
            bill_id = self.db.execute_query(
                insert_query,
                (order_id, subtotal, tax_amount, discount_amount, total_amount, payment_method)
            )

            if bill_id:
                logging.info(f"Created bill for order {order_id}, total: {total_amount}")
                return True, bill_id

            return False, "Failed to create bill"
        except Exception as e:
            logging.error(f"Error while creating bill: {e}")
            return False, f"Error creating bill: {e}"
    
    def complete_payment(self, order_id):
        """Mark a bill as paid and complete the order"""
        bill_update = """
            UPDATE bills 
            SET payment_status = 'completed', payment_time = NOW()
            WHERE order_id = %s AND payment_status = 'pending'
        """
        self.db.execute_query(bill_update, (order_id,))
        
        order_update = "UPDATE orders SET status = 'paid' WHERE order_id = %s"
        self.db.execute_query(order_update, (order_id,))
        
        table_update = """
            UPDATE tables SET is_occupied = FALSE 
            WHERE table_id = (SELECT table_id FROM orders WHERE order_id = %s)
        """
        self.db.execute_query(table_update, (order_id,))
        
        bill_query = """
            SELECT b.total_amount, o.customer_id 
            FROM bills b
            JOIN orders o ON b.order_id = o.order_id
            WHERE b.order_id = %s
        """
        bill = self.db.execute_query(bill_query, (order_id,), 'one')
        
        if bill:
            points_earned = int(bill['total_amount'] / 100)
            if points_earned > 0:
                loyalty_query = """
                    UPDATE customers 
                    SET loyalty_points = loyalty_points + %s
                    WHERE customer_id = %s
                """
                self.db.execute_query(loyalty_query, (points_earned, bill['customer_id']))
                logging.info(f"Added {points_earned} loyalty points to customer {bill['customer_id']}")
            
            self._update_daily_summary(bill['total_amount'])
        
        logging.info(f"Completed payment for order {order_id}")
        return True, "Payment completed successfully"
    
    def _update_daily_summary(self, amount):
        """Update daily summary with order amount"""
        today = date.today()
        
        query = "SELECT * FROM daily_summary WHERE summary_date = %s"
        summary = self.db.execute_query(query, (today,), 'one')
        
        if summary:
            total_orders = summary['total_orders'] + 1
            total_revenue = summary['total_revenue'] + amount
            average_bill = total_revenue / total_orders
            
            update_query = """
                UPDATE daily_summary
                SET total_orders = %s, total_revenue = %s, average_bill = %s
                WHERE summary_date = %s
            """
            self.db.execute_query(update_query, (total_orders, total_revenue, average_bill, today))
        else:
            insert_query = """
                INSERT INTO daily_summary (summary_date, total_orders, total_revenue, average_bill)
                VALUES (%s, 1, %s, %s)
            """
            self.db.execute_query(insert_query, (today, amount, amount))
        
        logging.info(f"Updated daily summary for {today} with amount {amount}")


class TableManager:
    def __init__(self, db_manager):
        self.db = db_manager
    
    def get_tables(self, available_only=False):
        """Get all tables, optionally filtering for available ones only"""
        if available_only:
            query = """
                SELECT table_id, table_number, capacity, is_occupied
                FROM tables
                WHERE is_occupied = FALSE
                ORDER BY table_number
            """
            return self.db.execute_query(query, fetch='all')
        else:
            query = """
                SELECT t.table_id, t.table_number, t.capacity, t.is_occupied,
                       o.order_id, c.name as customer_name
                FROM tables t
                LEFT JOIN orders o ON t.table_id = o.table_id AND o.status != 'paid'
                LEFT JOIN customers c ON o.customer_id = c.customer_id
                ORDER BY t.table_number
            """
            return self.db.execute_query(query, fetch='all')
    
    def add_table(self, table_number, capacity):
        """Add a new table"""
        try:
            table_number = int(table_number)
            capacity = int(capacity)
            if table_number <= 0 or capacity <= 0:
                return False, "Table number and capacity must be positive"
        except ValueError:
            return False, "Table number and capacity must be numbers"
        
        check_query = "SELECT COUNT(*) as count FROM tables WHERE table_number = %s"
        result = self.db.execute_query(check_query, (table_number,), 'one')
        
        if result and result['count'] > 0:
            return False, f"Table {table_number} already exists"
        
        insert_query = "INSERT INTO tables (table_number, capacity) VALUES (%s, %s)"
        table_id = self.db.execute_query(insert_query, (table_number, capacity))
        
        if table_id:
            logging.info(f"Added new table {table_number} with capacity {capacity}")
            return True, table_id
        
        return False, "Failed to add table"


class ReservationManager:
    def __init__(self, db_manager):
        self.db = db_manager
    
    def create_reservation(self, customer_id, reservation_time, party_size, notes=""):
        """Create a new table reservation"""
        try:
            party_size = int(party_size)
            if party_size <= 0:
                return False, "Party size must be positive"
            
            if isinstance(reservation_time, str):
                try:
                    reservation_time = datetime.strptime(reservation_time, "%Y-%m-%d %H:%M")
                except ValueError:
                    return False, "Invalid date format. Use YYYY-MM-DD HH:MM"
            
            if reservation_time < datetime.now():
                return False, "Reservation time must be in the future"
        except ValueError:
            return False, "Party size must be a number"
        
        table_query = """
            SELECT table_id, table_number, capacity 
            FROM tables 
            WHERE capacity >= %s
            ORDER BY capacity ASC
            LIMIT 1
        """
        table = self.db.execute_query(table_query, (party_size,), 'one')
        
        if not table:
            return False, f"No suitable table available for party of {party_size}"
        
        overlap_query = """
            SELECT COUNT(*) as count FROM reservations
            WHERE table_id = %s 
            AND reservation_time BETWEEN 
                DATE_SUB(%s, INTERVAL 2 HOUR) AND DATE_ADD(%s, INTERVAL 2 HOUR)
            AND status IN ('confirmed', 'seated')
        """
        overlap = self.db.execute_query(
            overlap_query, 
            (table['table_id'], reservation_time, reservation_time), 
            'one'
        )
        
        if overlap and overlap['count'] > 0:
            return False, "Table not available at the requested time"
        
        insert_query = """
            INSERT INTO reservations 
            (customer_id, table_id, reservation_time, party_size, notes, status)
            VALUES (%s, %s, %s, %s, %s, 'confirmed')
        """
        reservation_id = self.db.execute_query(
            insert_query,
            (customer_id, table['table_id'], reservation_time, party_size, notes)
        )
        
        if reservation_id:
            logging.info(f"Created reservation {reservation_id} for customer {customer_id}")
            return True, reservation_id
        
        return False, "Failed to create reservation"
    
    def get_reservations(self, date=None, status=None):
        """Get reservations, optionally filtered by date and status"""
        query_params = []
        where_clauses = []
        
        if date:
            where_clauses.append("DATE(r.reservation_time) = %s")
            query_params.append(date)
        
        if status:
            where_clauses.append("r.status = %s")
            query_params.append(status)
        
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        
        query = f"""
            SELECT r.reservation_id, r.reservation_time, r.party_size, r.status, r.notes,
                   c.name as customer_name, c.mobile as customer_mobile,
                   t.table_number
            FROM reservations r
            JOIN customers c ON r.customer_id = c.customer_id
            JOIN tables t ON r.table_id = t.table_id
            {where_sql}
            ORDER BY r.reservation_time
        """
        
        return self.db.execute_query(query, query_params if query_params else None, 'all')
    
    def update_reservation_status(self, reservation_id, status):
        """Update the status of a reservation"""
        valid_statuses = ['confirmed', 'seated', 'completed', 'cancelled']
        if status not in valid_statuses:
            return False, f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        
        update_query = "UPDATE reservations SET status = %s WHERE reservation_id = %s"
        self.db.execute_query(update_query, (status, reservation_id))
        
        logging.info(f"Updated reservation {reservation_id} status to {status}")
        return True, f"Reservation status updated to {status}"


class ReportManager:
    def __init__(self, db_manager):
        self.db = db_manager
    
    def get_daily_summary(self, start_date=None, end_date=None):
        """Get daily summary data, optionally between specific dates"""
        query_params = []
        where_clause = ""
        
        if start_date and end_date:
            where_clause = "WHERE summary_date BETWEEN %s AND %s"
            query_params.extend([start_date, end_date])
        elif start_date:
            where_clause = "WHERE summary_date >= %s"
            query_params.append(start_date)
        elif end_date:
            where_clause = "WHERE summary_date <= %s"
            query_params.append(end_date)
        
        query = f"""
            SELECT summary_date, total_orders, total_revenue, average_bill
            FROM daily_summary
            {where_clause}
            ORDER BY summary_date DESC
        """
        
        return self.db.execute_query(query, query_params if query_params else None, 'all')
    
    def get_sales_by_category(self, start_date=None, end_date=None):
        """Get sales figures broken down by menu category"""
        date_condition = ""
        query_params = []
        
        if start_date and end_date:
            date_condition = "WHERE o.order_date BETWEEN %s AND %s"
            query_params.extend([start_date, end_date])
        elif start_date:
            date_condition = "WHERE o.order_date >= %s"
            query_params.append(start_date)
        elif end_date:
            date_condition = "WHERE o.order_date <= %s"
            query_params.append(end_date)
        
        query = f"""
            SELECT mc.name as category, 
                   COUNT(oi.order_item_id) as items_sold,
                   SUM(oi.quantity) as total_quantity,
                   SUM(oi.quantity * oi.unit_price) as total_sales
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            JOIN menu_items mi ON oi.item_id = mi.item_id
            JOIN menu_categories mc ON mi.category_id = mc.category_id
            {date_condition}
            GROUP BY mc.name
            ORDER BY total_sales DESC
        """
        
        return self.db.execute_query(query, query_params if query_params else None, 'all')
    
    def get_top_selling_items(self, limit=10, start_date=None, end_date=None):
        """Get the top selling menu items"""
        date_condition = ""
        query_params = []
        
        if start_date and end_date:
            date_condition = "WHERE o.order_date BETWEEN %s AND %s"
            query_params.extend([start_date, end_date])
        elif start_date:
            date_condition = "WHERE o.order_date >= %s"
            query_params.append(start_date)
        elif end_date:
            date_condition = "WHERE o.order_date <= %s"
            query_params.append(end_date)
        
        query_params.append(limit)
        
        query = f"""
            SELECT mi.name as item_name, mc.name as category,
                   COUNT(oi.order_item_id) as order_count,
                   SUM(oi.quantity) as quantity_sold,
                   AVG(oi.unit_price) as average_price,
                   SUM(oi.quantity * oi.unit_price) as total_revenue
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.order_id
            JOIN menu_items mi ON oi.item_id = mi.item_id
            JOIN menu_categories mc ON mi.category_id = mc.category_id
            {date_condition}
            GROUP BY mi.name, mc.name
            ORDER BY quantity_sold DESC
            LIMIT %s
        """
        
        return self.db.execute_query(query, query_params, 'all')
    
    def get_customer_stats(self, limit=10):
        """Get statistics on top customers"""
        query = """
            SELECT c.customer_id, c.name, c.mobile, c.loyalty_points,
                   COUNT(DISTINCT o.order_id) as visit_count,
                   SUM(b.total_amount) as total_spent,
                   AVG(b.total_amount) as average_bill,
                   MAX(o.order_date) as last_visit
            FROM customers c
            JOIN orders o ON c.customer_id = o.customer_id
            JOIN bills b ON o.order_id = b.order_id
            WHERE b.payment_status = 'completed'
            GROUP BY c.customer_id, c.name, c.mobile, c.loyalty_points
            ORDER BY total_spent DESC
            LIMIT %s
        """
        
        return self.db.execute_query(query, (limit,), 'all')


class InventoryManager:
    def __init__(self, db_manager):
        self.db = db_manager
    
    def get_inventory(self, low_stock_only=False):
        """Get inventory items, optionally filtering for low stock items"""
        if low_stock_only:
            query = """
                SELECT inventory_id, name, quantity, unit, reorder_level, last_updated
                FROM inventory_items
                WHERE quantity <= reorder_level
                ORDER BY name
            """
        else:
            query = """
                SELECT inventory_id, name, quantity, unit, reorder_level, last_updated
                FROM inventory_items
                ORDER BY name
            """
        
        return self.db.execute_query(query, fetch='all')
    
    def add_inventory_item(self, name, quantity, unit, reorder_level=0):
        """Add a new inventory item"""
        if not name or not unit:
            return False, "Name and unit are required"
        
        try:
            quantity = float(quantity)
            reorder_level = float(reorder_level)
            if quantity < 0 or reorder_level < 0:
                return False, "Quantity and reorder level cannot be negative"
        except ValueError:
            return False, "Quantity and reorder level must be numbers"
        
        check_query = "SELECT inventory_id FROM inventory_items WHERE name = %s"
        existing = self.db.execute_query(check_query, (name,), 'one')
        
        if existing:
            return False, f"Item '{name}' already exists"
        
        insert_query = """
            INSERT INTO inventory_items (name, quantity, unit, reorder_level)
            VALUES (%s, %s, %s, %s)
        """
        item_id = self.db.execute_query(insert_query, (name, quantity, unit, reorder_level))
        
        if item_id:
            logging.info(f"Added new inventory item: {name}, quantity: {quantity} {unit}")
            return True, item_id
        
        return False, "Failed to add inventory item"
    
    def update_inventory(self, inventory_id, quantity_change):
        """Update inventory quantity (positive for adding, negative for using)"""
        query = "SELECT name, quantity, unit FROM inventory_items WHERE inventory_id = %s"
        item = self.db.execute_query(query, (inventory_id,), 'one')
        if not item:
            return False, "Inventory item not found"
        
        try:
            quantity_change = float(quantity_change)
        except ValueError:
            return False, "Quantity must be a number"
        
        new_quantity = item['quantity'] + quantity_change
        if new_quantity < 0:
            return False, "Not enough inventory available"
        
        update_query = "UPDATE inventory_items SET quantity = %s WHERE inventory_id = %s"
        self.db.execute_query(update_query, (new_quantity, inventory_id))
        
        operation = "added to" if quantity_change > 0 else "removed from"
        logging.info(f"{abs(quantity_change)} {item['unit']} {operation} {item['name']} inventory")
        return True, f"Inventory updated: {new_quantity} {item['unit']} remaining"
    
    def check_low_stock(self):
        """Check for items that are below their reorder level"""
        query = """
            SELECT inventory_id, name, quantity, unit, reorder_level
            FROM inventory_items
            WHERE quantity <= reorder_level
        """
        return self.db.execute_query(query, fetch='all')


class RestaurantManager:
    def __init__(self):
        """Initialize the main restaurant management system"""
        self.db = DatabaseManager()
        self.auth = AuthManager(self.db)
        self.customers = CustomerManager(self.db)
        self.menu = MenuManager(self.db)
        self.tables = TableManager(self.db)
        self.orders = OrderManager(self.db)
        self.reservations = ReservationManager(self.db)
        self.inventory = InventoryManager(self.db)
        self.reports = ReportManager(self.db)
    
    def close(self):
        """Close the database connection"""
        self.db.close()


def main():
    """Main function to run the restaurant management system"""
    print("=" * 50)
    print("Restaurant Management System")
    print("=" * 50)

    manager = RestaurantManager()

    username = input("Username: ")
    password = input("Password: ")

    if manager.auth.login(username, password):
        current_user = manager.auth.get_current_user()
        print(f"Welcome, {current_user['username']} ({current_user['role']})")

        while True:
            print("\nMain Menu:")
            print("1. View Tables")
            print("2. Place Full Order by Category")
            print("3. Check Low Stock")
            print("4. Add Customer")
            print("5. Search Customers")
            print("6. Create Order")
            print("7. Add Order Item")
            print("8. View Active Orders")
            print("9. Create Reservation")
            print("10. View Daily Summary")
            print("11. Create Bill")
            print("12. Complete Payment")
            print("13. Logout")
            choice = input("Choose an option: ")

            if choice == "1":
                tables = manager.tables.get_tables()
                table_data = [[t['table_number'], t['capacity'], 'Occupied' if t['is_occupied'] else 'Available']
                              for t in tables]
                print(tabulate(table_data, headers=['Table', 'Capacity', 'Status'], tablefmt='pretty'))

            elif choice == "2":
                try:
                    customer_id = int(input("Customer ID: "))
                    table_id = int(input("Table ID: "))
                    server_id = current_user['user_id']
                    success, order_id = manager.orders.create_order(customer_id, table_id, server_id)
                    if not success:
                        print(order_id)
                        continue
                    print(f"Order created with ID: {order_id}")

                    categories = manager.menu.get_categories()
                    for cat in categories:
                        print(f"\n--- {cat['name']} ---")
                        items = manager.menu.get_menu_items(cat['category_id'])
                        for item in items:
                            print(f"{item['item_id']}. {item['name']} - ₹{item['price']:.2f}")

                        while True:
                            item_input = input(f"Add item ID from {cat['name']} (or press Enter to skip): ")
                            if not item_input:
                                break
                            try:
                                item_id = int(item_input)
                                quantity = int(input("Quantity: "))
                                notes = input("Notes (optional): ")
                                success, result = manager.orders.add_order_item(order_id, item_id, quantity, notes)
                                print(result)
                            except ValueError:
                                print("Invalid input.")

                    discount = input("Discount Amount (default 0): ") or 0
                    payment_method = input("Payment Method (cash/credit_card/upi/other): ") or 'cash'
                    success, result = manager.orders.create_bill(order_id, discount, payment_method)
                    print(result)

                    if success:
                        success, result = manager.orders.complete_payment(order_id)
                        print(result)

                except ValueError:
                    print("Invalid input.")

            elif choice == "3":
                low_stock = manager.inventory.check_low_stock()
                if low_stock:
                    print("\nLow Stock Alert:")
                    stock_data = [[i['name'], f"{i['quantity']} {i['unit']}", i['reorder_level']]
                                  for i in low_stock]
                    print(tabulate(stock_data, headers=['Item', 'Current Stock', 'Reorder Level'], tablefmt='pretty'))
                else:
                    print("All inventory items are sufficiently stocked.")

            elif choice == "4":
                name = input("Customer Name: ")
                mobile = input("Mobile Number: ")
                email = input("Email (optional): ") or None
                success, msg = manager.customers.add_customer(name, mobile, email)
                print(msg)

            elif choice == "5":
                search_term = input("Search customers by name or mobile: ")
                results = manager.customers.search_customers(search_term)
                if results:
                    print(tabulate([[c['customer_id'], c['name'], c['mobile'], c['email']] for c in results],
                                   headers=["ID", "Name", "Mobile", "Email"], tablefmt='pretty'))
                else:
                    print("No customers found.")

            elif choice == "6":
                try:
                    customer_id = int(input("Customer ID: "))
                    table_id = int(input("Table ID: "))
                    server_id = current_user['user_id']
                    success, result = manager.orders.create_order(customer_id, table_id, server_id)
                    print(result)
                except ValueError:
                    print("Invalid input.")

            elif choice == "7":
                try:
                    order_id = int(input("Order ID: "))
                    item_id = int(input("Menu Item ID: "))
                    quantity = int(input("Quantity: "))
                    notes = input("Notes (optional): ")
                    success, result = manager.orders.add_order_item(order_id, item_id, quantity, notes)
                    print(result)
                except ValueError:
                    print("Invalid input.")

            elif choice == "8":
                orders = manager.orders.get_active_orders()
                if orders:
                    print(tabulate([[o['order_id'], o['customer_name'], o['table_number'], o['status'], o['subtotal']]
                                    for o in orders],
                                   headers=["Order ID", "Customer", "Table", "Status", "Subtotal"],
                                   tablefmt='pretty'))
                else:
                    print("No active orders.")

            elif choice == "9":
                try:
                    customer_id = int(input("Customer ID: "))
                    time_str = input("Reservation Time (YYYY-MM-DD HH:MM): ")
                    party_size = int(input("Party Size: "))
                    notes = input("Notes (optional): ")
                    success, result = manager.reservations.create_reservation(customer_id, time_str, party_size, notes)
                    print(result)
                except ValueError:
                    print("Invalid input.")

            elif choice == "10":
                summary = manager.reports.get_daily_summary()
                if summary:
                    print(tabulate([[s['summary_date'], s['total_orders'], s['total_revenue'], s['average_bill']]
                                   for s in summary],
                                   headers=["Date", "Orders", "Revenue", "Avg Bill"],
                                   tablefmt='pretty'))
                else:
                    print("No summary data found.")

            elif choice == "11":
                try:
                    order_id = int(input("Order ID: "))
                    discount = input("Discount Amount (default 0): ") or 0
                    payment_method = input("Payment Method (cash/credit_card/upi/other): ") or 'cash'
                    success, result = manager.orders.create_bill(order_id, discount, payment_method)
                    print(result)
                except ValueError:
                    print("Invalid input.")

            elif choice == "12":
                try:
                    order_id = int(input("Order ID to complete payment: "))
                    success, result = manager.orders.complete_payment(order_id)
                    print(result)
                except ValueError:
                    print("Invalid input.")

            elif choice == "13":
                print("Logging out...")
                manager.auth.logout()
                break

            else:
                print("Invalid option. Please try again.")
    else:
        print("Login failed. Invalid username or password.")

    manager.close()


if __name__ == "__main__":
    main()

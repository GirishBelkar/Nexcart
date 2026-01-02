from flask import Flask, render_template, session, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import or_
import os

app = Flask(__name__)
# In production, use os.environ.get('SECRET_KEY')
app.secret_key = 'dev_key_nexcart_2024'

# --- CONFIGURATION ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'shop.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static/images')

db = SQLAlchemy(app)

# --- LOGIN CONFIG ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' 

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False) # Changed to Float for cents
    image = db.Column(db.String(100), nullable=True) # Allow null for fallback images
    description = db.Column(db.String(500), default="")
    category = db.Column(db.String(50), default="General")

    @property
    def image_url(self):
        """Logic to return local file or None (triggering HTML fallback)"""
        if self.image and os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], self.image)):
            return url_for('static', filename='images/' + self.image)
        return None  # HTML template will handle Unsplash fallback

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="Pending")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- CONTEXT PROCESSOR ---
@app.context_processor
def inject_cart_count():
    """Makes cart_count available in Navbar across all pages"""
    cart = session.get('cart', [])
    return dict(cart_count=len(cart))

# --- AUTH ROUTES ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('User already exists!', 'danger')
            return redirect(url_for('register'))
        
        new_user = User(username=username)
        new_user.set_password(password)
        
        # Make first user Admin automatically
        if User.query.count() == 0: 
            new_user.is_admin = True
            
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        flash('Account created successfully!', 'success')
        return redirect(url_for('home'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))

# --- MAIN ROUTES ---
@app.route('/')
def home():
    # Grab 3 random products for the "Trending" section
    featured = Product.query.order_by(db.func.random()).limit(3).all()
    return render_template('index.html', featured_products=featured)

@app.route('/shop')
def shop_page():
    # Start the query
    query = Product.query

    # 1. Search Logic
    search_query = request.args.get('q') # From <input name="q">
    if search_query:
        query = query.filter(
            or_(
                Product.name.contains(search_query),
                Product.description.contains(search_query)
            )
        )

    # 2. Filter Logic (e.g. ?category=Hardware)
    category_filter = request.args.get('category')
    if category_filter:
        query = query.filter_by(category=category_filter)

    products = query.all()
    return render_template('products.html', products=products)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('detail.html', product=product)

# --- CART SYSTEM ---
@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    if 'cart' not in session:
        session['cart'] = []
    
    # We need to re-assign the list to trigger session update
    cart_list = session['cart']
    cart_list.append(product_id)
    session['cart'] = cart_list
    
    flash('Item added to cart!', 'success')
    # Return to previous page or shop
    return redirect(request.referrer or url_for('shop_page'))

@app.route('/cart')
def view_cart():
    cart_ids = session.get('cart', [])
    cart_items = []
    total_price = 0
    
    # Simple logic: Fetch product for every ID in cart
    # (Note: In a real app, you'd group by ID to show quantity)
    for p_id in cart_ids:
        item = Product.query.get(p_id)
        if item:
            cart_items.append(item)
            total_price += item.price
            
    return render_template('cart.html', cart_items=cart_items, total=total_price)

@app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    if 'cart' in session:
        cart_list = session['cart']
        if product_id in cart_list:
            cart_list.remove(product_id) # Removes only the first occurrence
            session['cart'] = cart_list
            flash('Item removed.', 'info')
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    cart_ids = session.get('cart', [])
    if not cart_ids:
        flash("Your cart is empty.", "warning")
        return redirect(url_for('shop_page'))

    total_price = sum([Product.query.get(i).price for i in cart_ids if Product.query.get(i)])

    if request.method == 'POST':
        customer_name = request.form.get('name')
        address = request.form.get('address')
        
        new_order = Order(
            customer_name=customer_name, 
            address=address, 
            total_price=total_price
        )
        db.session.add(new_order)
        db.session.commit()
        
        # Clear cart
        session.pop('cart', None)
        return render_template('success.html', name=customer_name)

    return render_template('checkout.html', total=total_price)

# --- ADMIN ---
@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash("Access Denied.", "danger")
        return redirect(url_for('home'))

    if request.method == 'POST':
        p_name = request.form.get('product_name')
        p_price = request.form.get('product_price')
        p_desc = request.form.get('product_desc')
        p_cat = request.form.get('product_category')
        
        file = request.files.get('product_image')
        filename = None
        
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
        new_product = Product(
            name=p_name, 
            price=float(p_price), 
            image=filename,
            description=p_desc,
            category=p_cat
        )
        db.session.add(new_product)
        db.session.commit()
        flash('Product Added!', 'success')

    products = Product.query.all()
    return render_template('admin.html', products=products)

# --- DATABASE SETUP (THEMED DATA) ---
def setup_database():
    with app.app_context():
        # Create folder for uploads
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])
            
        db.create_all()
        
        if not Product.query.first():
            print("⚡ Database empty. Seeding Nexcart data...")
            
            # Themed Data: Hardware, Software, Merch
            seed_data = [
                # Hardware
                {"name": "Mechanical Keycaps (Python Ed.)", "category": "Hardware", "price": 49.99, "desc": "Custom PBT keycaps in blue and yellow colors."},
                {"name": "Ultrawide Monitor Stand", "category": "Hardware", "price": 120.00, "desc": "Aluminum stand for your dual-monitor coding setup."},
                {"name": "Ergonomic Vertical Mouse", "category": "Hardware", "price": 35.50, "desc": "Save your wrist during long debugging sessions."},
                
                # Software
                {"name": "Flask Pro Template", "category": "Software", "price": 29.00, "desc": "Production-ready boilerplate with Auth, Admin, and Stripe."},
                {"name": "API Access Key (Lifetime)", "category": "Software", "price": 99.00, "desc": "Unlimited requests to our machine learning backend."},
                {"name": "Cloud Deployment Script", "category": "Software", "price": 15.00, "desc": "Automated bash scripts for AWS/DigitalOcean."},
                
                # Merchandise
                {"name": "Developer Hoodie (Black)", "category": "Merchandise", "price": 55.00, "desc": "Heavyweight cotton. 'It works on my machine' print."},
                {"name": "Vacuum Insulated Mug", "category": "Merchandise", "price": 22.00, "desc": "Keeps your coffee hot for 6 hours while you code."},
                {"name": "Laptop Sticker Pack", "category": "Merchandise", "price": 8.00, "desc": "High-quality vinyl stickers: Python, Docker, Linux."},
                
                # Accessories
                {"name": "Blue Light Glasses", "category": "Accessories", "price": 45.00, "desc": "Protect your eyes from screen fatigue."},
                {"name": "Desk Mat (900x400)", "category": "Accessories", "price": 25.00, "desc": "Smooth surface with code cheat sheets printed on it."}
            ]
            
            for item in seed_data:
                p = Product(
                    name=item['name'],
                    price=item['price'],
                    description=item['desc'],
                    category=item['category'],
                    image=None # Set to None so HTML uses Unsplash fallback
                )
                db.session.add(p)
            
            db.session.commit()
            print(f"✅ Added {len(seed_data)} developer-themed products!")

if __name__ == '__main__':
    setup_database()
    app.run(debug=True)
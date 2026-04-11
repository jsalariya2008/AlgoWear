from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename, send_from_directory
import os
import json
import mysql.connector
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'algo_streetwear_secret_2024'
app.config['UPLOAD_FOLDER'] = 'uploads/products'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '1872008'
app.config['MYSQL_DB'] = 'algo_store'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ── HOMEPAGE ──────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM products WHERE is_active=1 ORDER BY created_at DESC LIMIT 6")
    featured = cur.fetchall()
    cur.execute("SELECT * FROM products WHERE is_upcoming=1 LIMIT 5")
    upcoming = cur.fetchall()
    cur.close()
    cart_count = sum(item['qty'] for item in session.get('cart', {}).values()) if session.get('cart') else 0
    return render_template('index.html', featured=featured, upcoming=upcoming, cart_count=cart_count)

# ── PRODUCTS ──────────────────────────────────────────────────────────────────
@app.route('/collection')
def collection():
    category = request.args.get('category', '')
    cur = mysql.connection.cursor()
    if category:
        cur.execute("SELECT * FROM products WHERE is_active=1 AND category=%s ORDER BY created_at DESC", (category,))
    else:
        cur.execute("SELECT * FROM products WHERE is_active=1 ORDER BY created_at DESC")
    products = cur.fetchall()
    cur.execute("SELECT DISTINCT category FROM products WHERE is_active=1")
    categories = [r['category'] for r in cur.fetchall()]
    cur.close()
    cart_count = sum(item['qty'] for item in session.get('cart', {}).values()) if session.get('cart') else 0
    return render_template('collection.html', products=products, categories=categories, selected=category, cart_count=cart_count)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM products WHERE id=%s AND is_active=1", (product_id,))
    product = cur.fetchone()
    if not product:
        return redirect(url_for('collection'))
    cur.execute("SELECT * FROM products WHERE category=%s AND id != %s AND is_active=1 LIMIT 4", (product['category'], product_id))
    related = cur.fetchall()
    cur.close()
    cart_count = sum(item['qty'] for item in session.get('cart', {}).values()) if session.get('cart') else 0
    return render_template('product_detail.html', product=product, related=related, cart_count=cart_count)

# ── CART ──────────────────────────────────────────────────────────────────────
@app.route('/cart')
def cart():
    cart = session.get('cart', {})
    items = []
    total = 0
    if cart:
        cur = mysql.connection.cursor()
        for pid, info in cart.items():
            cur.execute("SELECT * FROM products WHERE id=%s", (pid,))
            p = cur.fetchone()
            if p:
                subtotal = p['price'] * info['qty']
                total += subtotal
                items.append({**p, 'qty': info['qty'], 'size': info.get('size','M'), 'subtotal': subtotal})
        cur.close()
    cart_count = sum(item['qty'] for item in cart.values()) if cart else 0
    return render_template('cart.html', items=items, total=total, cart_count=cart_count)

@app.route('/cart/add', methods=['POST'])
def add_to_cart():
    data = request.get_json()
    pid = str(data.get('product_id'))
    size = data.get('size', 'M')
    qty = int(data.get('qty', 1))
    cart = session.get('cart', {})
    key = f"{pid}_{size}"
    if key in cart:
        cart[key]['qty'] += qty
    else:
        cart[key] = {'product_id': pid, 'qty': qty, 'size': size}
    session['cart'] = cart
    total_items = sum(i['qty'] for i in cart.values())
    return jsonify({'success': True, 'cart_count': total_items})

@app.route('/cart/remove', methods=['POST'])
def remove_from_cart():
    data = request.get_json()
    key = data.get('key')
    cart = session.get('cart', {})
    if key in cart:
        del cart[key]
    session['cart'] = cart
    return jsonify({'success': True})

@app.route('/cart/update', methods=['POST'])
def update_cart():
    data = request.get_json()
    key = data.get('key')
    qty = int(data.get('qty', 1))
    cart = session.get('cart', {})
    if key in cart:
        if qty <= 0:
            del cart[key]
        else:
            cart[key]['qty'] = qty
    session['cart'] = cart
    return jsonify({'success': True})

# ── AUTH ──────────────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['name']
            session['is_admin'] = bool(user['is_admin'])
            return redirect(url_for('index'))
        flash('Invalid credentials', 'error')
    cart_count = sum(item['qty'] for item in session.get('cart', {}).values()) if session.get('cart') else 0
    return render_template('auth.html', mode='login', cart_count=cart_count)

# ── EMAIL CONFIG ─────────────────────────────
from flask_mail import Mail, Message
import random

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'algowear.co@gmail.com'
app.config['MAIL_PASSWORD'] = 'vhxqxfrccoevzmzb'

mail = Mail(app)

# ── OTP FUNCTIONS ─────────────────────────────
def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp(email, otp):
    msg = Message(
        'Your OTP Code',
        sender=app.config['MAIL_USERNAME'],
        recipients=[email]
    )
    msg.body = f'Your OTP is {otp}'
    mail.send(msg)


# ── SIGNUP WITH OTP ─────────────────────────────
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        cur = mysql.connection.cursor()
        cur.execute("SELECT id FROM users WHERE email=%s", (email,))
        if cur.fetchone():
            cur.close()
            flash('Email already registered', 'error')
            return redirect(url_for('signup'))

        # Generate OTP
        otp = generate_otp()

        # Save temp user
        session['temp_user'] = {
            'name': name,
            'email': email,
            'password': generate_password_hash(password)
        }
        session['otp'] = otp

        # Send OTP
        send_otp(email, otp)

        flash('OTP sent to your email', 'success')
        return redirect(url_for('verify_otp_page'))

    cart_count = sum(item['qty'] for item in session.get('cart', {}).values()) if session.get('cart') else 0
    return render_template('auth.html', mode='signup', cart_count=cart_count)


# ── VERIFY OTP ─────────────────────────────
@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp_page():
    if request.method == 'POST':
        user_otp = request.form['otp']

        if user_otp == session.get('otp'):
            user = session.get('temp_user')

            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO users (name,email,password_hash)
                VALUES(%s,%s,%s)
            """, (user['name'], user['email'], user['password']))
            mysql.connection.commit()
            cur.close()

            session.pop('otp', None)
            session.pop('temp_user', None)

            flash('Account created successfully!', 'success')
            return redirect(url_for('login'))
        else:
            flash('Invalid OTP', 'error')

    return render_template('verify_otp.html')


#LOGOUT
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ── LOOKBOOK ──────────────────────────────────────────────────────────────────
@app.route('/lookbook')
def lookbook():
    cart_count = sum(item['qty'] for item in session.get('cart', {}).values()) if session.get('cart') else 0
    return render_template('lookbook.html', cart_count=cart_count)

# ── ADMIN ──────────────────────────────────────────────────────────────────────
@app.route('/admin')
@admin_required
def admin():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM products ORDER BY created_at DESC")
    products = cur.fetchall()
    cur.execute("SELECT COUNT(*) as cnt FROM users")
    user_count = cur.fetchone()['cnt']
    cur.close()
    return render_template('admin.html', products=products, user_count=user_count)

@app.route('/admin/product/add', methods=['GET', 'POST'])
@admin_required
def admin_add_product():
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        description = request.form['description']
        category = request.form['category']
        stock = int(request.form['stock'])
        is_upcoming = 1 if request.form.get('is_upcoming') else 0
        image_url = ''
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_url = f'/uploads/products/{filename}'
        cur = mysql.connection.cursor()
        cur.execute("""INSERT INTO products (name,price,description,category,stock,image_url,is_upcoming,is_active)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,1)""",
                    (name, price, description, category, stock, image_url, is_upcoming))
        mysql.connection.commit()
        cur.close()
        flash('Product added!', 'success')
        return redirect(url_for('admin'))
    return render_template('admin_product_form.html', product=None)

@app.route('/admin/product/edit/<int:pid>', methods=['GET', 'POST'])
@admin_required
def admin_edit_product(pid):
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        description = request.form['description']
        category = request.form['category']
        stock = int(request.form['stock'])
        is_upcoming = 1 if request.form.get('is_upcoming') else 0
        is_active = 1 if request.form.get('is_active') else 0
        cur.execute("""UPDATE products SET name=%s,price=%s,description=%s,category=%s,
                       stock=%s,is_upcoming=%s,is_active=%s WHERE id=%s""",
                    (name, price, description, category, stock, is_upcoming, is_active, pid))
        mysql.connection.commit()
        cur.close()
        flash('Product updated!', 'success')
        return redirect(url_for('admin'))
    cur.execute("SELECT * FROM products WHERE id=%s", (pid,))
    product = cur.fetchone()
    cur.close()
    return render_template('admin_product_form.html', product=product)

@app.route('/admin/product/delete/<int:pid>', methods=['POST'])
@admin_required
def admin_delete_product(pid):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM products WHERE id=%s", (pid,))
    mysql.connection.commit()
    cur.close()
    return jsonify({'success': True})

@app.route('/admin/orders')
@admin_required
def admin_orders():
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT o.id, o.total_amount, o.status, o.created_at, u.name
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.id
        ORDER BY o.created_at DESC
    """)
    orders = cur.fetchall()
    cur.close()
    return render_template('admin_orders.html', orders=orders)

# ── API for cart count ─────────────────────────────────────────────────────────
@app.route('/api/cart-count')
def cart_count_api():
    cart = session.get('cart', {})
    count = sum(i['qty'] for i in cart.values()) if cart else 0
    return jsonify({'count': count})

import os

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(
        os.path.join(app.config['UPLOAD_FOLDER'], 't-shirts'),
        filename
    )

import razorpay
import hmac
import hashlib
import os

# Init Razorpay client
rz_client = razorpay.Client(
    auth=(os.getenv('RAZORPAY_KEY_ID'), os.getenv('RAZORPAY_KEY_SECRET'))
)

# ── CHECKOUT: create a Razorpay order ─────────────────────────────
@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():

    cart = session.get('cart', {})
    if not cart:
        return redirect(url_for('cart'))

    cur = mysql.connection.cursor()
    cart_items = []
    subtotal = 0

    for key, item in cart.items():
        pid = item.get('product_id') or key.split('_')[0]
        cur.execute("SELECT * FROM products WHERE id=%s", (pid,))
        p = cur.fetchone()
        if p:
            sub = p['price'] * item['qty']
            subtotal += sub
            cart_items.append({
                **p,
                'qty': item['qty'],
                'size': item.get('size', 'M'),
                'subtotal': sub
            })

    shipping = 0 if subtotal >= 999 else 99
    grand_total = subtotal + shipping

    # 👉 JUST SHOW PAGE (no order creation yet)
    return render_template(
        'checkout.html',
        cart_items=cart_items,
        subtotal=subtotal,
        grand_total=grand_total,
        cart_count=0
    )

    # Create Razorpay order
    import time
    rz_order = rz_client.order.create({
        'amount': amount_paise,
        'currency': 'INR',
        'receipt': f"algo_{session['user_id']}_{int(time.time())}",
    })

    # Save pending order in DB
    cur.execute("""
        INSERT INTO orders (user_id, total_amount, status, razorpay_order_id)
        VALUES (%s, %s, 'pending', %s)
    """, (session['user_id'], grand_total, rz_order['id']))
    mysql.connection.commit()
    order_id = cur.lastrowid
    cur.close()

    return render_template('checkout.html',
        rz_key=os.getenv('RAZORPAY_KEY_ID'),
        rz_order_id=rz_order['id'],
        amount=amount_paise,
        order_id=order_id,
        subtotal=subtotal,
        grand_total=grand_total,
        cart_items=cart_items,
        cart_count=0
    )
@app.route('/place-order', methods=['POST'])
@login_required
def place_order():
    """Handles COD orders — no payment needed upfront."""
    
    order_id = request.form.get('order_id')
    payment_method = request.form.get('payment_method', 'cod')

    if payment_method != 'cod':
        return redirect(url_for('cart'))

    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE orders
        SET status='confirmed', payment_method='cod'
        WHERE id=%s AND user_id=%s
    """, (order_id, session['user_id']))
    
    mysql.connection.commit()

    # ✅ SEND EMAIL INSIDE FUNCTION
    try:
        msg = Message(
            subject="🛒 New COD Order - ALGO",
            sender=app.config['MAIL_USERNAME'],
            recipients=['algowear.co@gmail.com']
        )

        msg.body = f"""
New COD Order Received!

Order ID: {order_id}
Payment: Cash on Delivery

Check admin panel for details.
"""

        mail.send(msg)

    except Exception as e:
        print("Email error:", e)

    # ✅ CLEAR CART
    session.pop('cart', None)

    cur.close()

    # ✅ RETURN MUST BE LAST INSIDE FUNCTION
    return redirect(url_for('order_success', order_id=order_id))

# ── PAYMENT VERIFICATION: called after user pays ──────────────────
@app.route('/payment/verify', methods=['POST'])
@login_required
def verify_payment():

    data = request.get_json()
    rz_order_id   = data.get('razorpay_order_id')
    rz_payment_id = data.get('razorpay_payment_id')
    rz_signature  = data.get('razorpay_signature')
    db_order_id   = data.get('order_id')

    # HMAC-SHA256 signature verification
    msg = f"{rz_order_id}|{rz_payment_id}".encode()
    secret = os.getenv('RAZORPAY_KEY_SECRET').encode()
    expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, rz_signature):
        return jsonify({'success': False, 'error': 'Invalid signature'}), 400

    # ✅ Update DB
    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE orders SET
            status='confirmed',
            razorpay_payment_id=%s,
            razorpay_signature=%s,
            paid_at=NOW()
        WHERE id=%s AND user_id=%s
    """, (rz_payment_id, rz_signature, db_order_id, session['user_id']))
    
    mysql.connection.commit()

    # ✅ SEND EMAIL INSIDE FUNCTION
    try:
        msg = Message(
            subject="💳 New Paid Order - ALGO",
            sender=app.config['MAIL_USERNAME'],
            recipients=['algowear.co@gmail.com']
        )

        msg.body = f"""
New Paid Order Received!

Order ID: {db_order_id}
Payment ID: {rz_payment_id}

Check admin panel for details.
"""

        mail.send(msg)

    except Exception as e:
        print("Email error:", e)

    # ✅ Clear cart ALWAYS
    session.pop('cart', None)

    cur.close()

    # ✅ Always return
    return jsonify({'success': True, 'order_id': db_order_id})


# ── WEBHOOK: Razorpay server-to-server notification ───────────────
@app.route('/webhook/razorpay', methods=['POST'])
def razorpay_webhook():
    webhook_secret = os.getenv('RAZORPAY_WEBHOOK_SECRET', '')
    payload = request.get_data()
    received_sig = request.headers.get('X-Razorpay-Signature', '')

    # Verify webhook signature
    expected = hmac.new(
        webhook_secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, received_sig):
        return jsonify({'error': 'Invalid webhook'}), 400

    event = request.get_json()
    if event.get('event') == 'payment.captured':
        payment = event['payload']['payment']['entity']
        rz_order_id = payment.get('order_id')
        cur = mysql.connection.cursor()
        cur.execute("""
            UPDATE orders SET status='confirmed', paid_at=NOW()
            WHERE razorpay_order_id=%s AND status='pending'
        """, (rz_order_id,))
        mysql.connection.commit()
        cur.close()

    return jsonify({'status': 'ok'})


# ── ORDER SUCCESS PAGE ─────────────────────────────────────────────
@app.route('/order/success/<int:order_id>')
@login_required
def order_success(order_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM orders WHERE id=%s AND user_id=%s",
                (order_id, session['user_id']))
    order = cur.fetchone()
    cur.close()
    cart_count = 0
    return render_template('order_success.html', order=order, cart_count=cart_count)

if __name__ == "__main__":
    app.run(debug=True)
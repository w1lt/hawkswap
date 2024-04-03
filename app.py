from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import datetime
import psycopg2
from flask import g
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

DATABASE = 'marketplace.db'

def get_db_connection():
    if 'db_connection' not in g:
        DATABASE_URL = os.environ.get('DATABASE_URL')
        g.db_connection = psycopg2.connect(DATABASE_URL, sslmode='require')
    return g.db_connection

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    conn.close()
    if user:
        return User(user['id'], user['username'])
    return None


@app.route('/user/<username>')
def show_user_profile(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    #find all listings by this user
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE seller = %s", (username,))
    listings = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('userpage.html', user=user, listings=listings)

@app.route('/listing/<id>')
def show_listing(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id = %s", (id,))
    listing = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('listing.html', listing=listing)

@app.route('/inbox')
def inbox():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM messages WHERE receiver = %s", (current_user.username,))
    messages = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('inbox.html', messages=messages)

@app.route('/message-seller/<listing_id>', methods=['GET', 'POST'])
def message_seller(listing_id):
    # find user from listing id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE id = %s", (listing_id,))
    listing = cursor.fetchone()
    cursor.close()
    conn.close()
    if request.method == 'POST':
        message = request.form['message']
        sender = current_user.username
        receiver = listing['seller']
        date_sent = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO messages (sender, receiver, message, datesent, listing_id) VALUES (%s, %s, %s, %s, %s)', (sender, receiver, message, date_sent, listing_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('index'))
    return render_template('message_seller.html', listing=listing)
    
    
    

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']

        # Check if the email is from the @ku.edu domain
        if not email.endswith('@ku.edu'):
            flash('Email must be from the @ku.edu domain.', 'error')
            return redirect(url_for('register'))
        
        conn = get_db_connection()
        if conn.execute('SELECT * FROM users WHERE username = %s', (username,)).fetchone():
            flash('Username is already taken.', 'error')
            conn.close()
            return redirect(url_for('register'))
        conn.execute('INSERT INTO users (username, password, email) VALUES (%s, %s, %s)', (username, password, email))
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/create-listing', methods=['GET', 'POST'])
def create_listing():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = request.form['price']
        date_posted = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        seller = current_user.username

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO products (name, description, price, dateposted, seller) VALUES (%s, %s, %s, %s, %s)', (name, description, price, date_posted, seller, ))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('index'))
    return render_template('create_listing.html')



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password)).fetchone()
        conn.close()
        if user:
            login_user(User(user['id'], user['username']))
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('index.html', products=products)

if __name__ == '__main__':
    app.run(debug=True)

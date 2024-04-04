from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import datetime
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

DATABASE_URI = 'sqlite:///marketplace.db'
engine = create_engine(DATABASE_URI, connect_args={'timeout': 15})  # Set a 15-second timeout
db_session = scoped_session(sessionmaker(bind=engine))

def get_db_connection():
    return db_session()

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    session = get_db_connection() 
    user = session.execute('SELECT * FROM users WHERE id = :user_id', {'user_id': user_id}).fetchone()
    session.close()
    if user:
        return User(user['id'], user['username'])
    return None

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()


@app.route('/user/<username>')
@login_required
def show_user_profile(username):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = :username", {'username': username}).fetchone()
    listings = conn.execute("SELECT * FROM listings WHERE seller_id = :seller_id", {'seller_id': user['id']}).fetchall()
    conn.close()
    return render_template('userpage.html', user=user, listings=listings)

@app.route('/listing/<id>')
@login_required
def show_listing(id):
    conn = get_db_connection()
    listing = conn.execute("SELECT * FROM listings WHERE id = :id", {'id': id}).fetchone()
    seller = conn.execute("SELECT * FROM users WHERE id = :id", {'id': listing['seller_id']}).fetchone()
    conn.close()

    return render_template('listing.html', listing=listing, sellerusername=seller.username)

@app.route('/listing/<id>/edit', methods=['GET', 'POST'])
@login_required
def edit_listing(id):
    conn = get_db_connection()
    listing = conn.execute("SELECT * FROM listings WHERE id = :id", {'id': id}).fetchone()
    seller = conn.execute("SELECT * FROM users WHERE id = :id", {'id': listing['seller_id']}).fetchone()
    if current_user.id != seller['id']:
        return redirect(url_for('show_listing', id=id))
    conn.close()
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = (request.form['price'])
        conn = get_db_connection()
        conn.execute('UPDATE listings SET name = :name, description = :description, price = :price WHERE id = :id', {'name': name, 'description': description, 'price': price, 'id': id})
        conn.commit()
        conn.close()
        return redirect(url_for('show_listing', id=id))
    return render_template('edit_listing.html', listing=listing, sellerusername=seller.username)

@app.route('/listing/<id>/delete', methods=['POST'])
@login_required
def delete_listing(id):
    conn = get_db_connection()
    listing = conn.execute("SELECT * FROM listings WHERE id = :id", {'id': id}).fetchone()
    seller = conn.execute("SELECT * FROM users WHERE id = :id", {'id': listing['seller_id']}).fetchone()
    if current_user.id != seller['id']:
        return redirect(url_for('show_listing', id=id))
    conn.execute('DELETE FROM listings WHERE id = :id', {'id': id})
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/inbox')
@login_required
def inbox():
    conn = get_db_connection()
    chats = conn.execute("""
        SELECT c.chat_id, l.name, u.username, m.message_content, m.sent_at, m.sent_at,
               (SELECT COUNT(*) FROM messages WHERE chat_id = c.chat_id AND read_status = "0" AND sender_id != :user_id) AS unread_count
        FROM chats c
        JOIN listings l ON c.listing_id = l.id
        JOIN users u ON (c.buyer_id = u.id OR c.seller_id = u.id) AND u.id != :user_id
        JOIN (
            SELECT chat_id, MAX(sent_at) as max_sent_at
            FROM messages
            GROUP BY chat_id
        ) latest_msg ON c.chat_id = latest_msg.chat_id
        JOIN messages m ON c.chat_id = m.chat_id AND m.sent_at = latest_msg.max_sent_at
        WHERE c.buyer_id = :user_id OR c.seller_id = :user_id
        ORDER BY m.sent_at DESC
    """, {'user_id': current_user.id}).fetchall()
    conn.close()
    return render_template('inbox.html', chats=chats)

@app.route('/message-seller/<listing_id>', methods=['GET', 'POST'])
@login_required
def message_seller(listing_id):
    conn = get_db_connection()
    listing = conn.execute("SELECT * FROM listings WHERE id = :id", {'id': listing_id}).fetchone()
    seller_id = listing['seller_id']
    #if there is already a chat between the buyer and the seller, get the chat id and redirect to the chat page
    chat = conn.execute("""
        SELECT c.chat_id
        FROM chats c
        WHERE (listing_id = :listing_id AND seller_id = :seller_id AND buyer_id = :buyer_id) OR (listing_id = :listing_id AND seller_id = :buyer_id AND buyer_id = :seller_id)
    """, {'listing_id': listing_id, 'seller_id': seller_id, 'buyer_id': current_user.id}).fetchone()
    if chat:
        chat_id = chat['chat_id']
        conn.close()
        return redirect(url_for('chat', chat_id=chat_id))
    conn.close()

    if request.method == 'POST':
        message_content = request.form['message']
        sender_id = current_user.id
        sent_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = get_db_connection()
        chat = conn.execute("""
            SELECT c.chat_id
            FROM chats c
             WHERE (listing_id = :listing_id AND seller_id = :seller_id AND buyer_id = :buyer_id) OR (listing_id = :listing_id AND seller_id = :buyer_id AND buyer_id = :seller_id)
    """, {'listing_id': listing_id, 'seller_id': seller_id, 'buyer_id': current_user.id}).fetchone()
        if not chat:
            conn.execute("INSERT INTO chats (listing_id, seller_id, buyer_id) VALUES (:listing_id, :seller_id, :buyer_id)", {'listing_id': listing_id, 'seller_id': seller_id, 'buyer_id': sender_id})
            chat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        else:
            chat_id = chat['chat_id']
        conn.execute('INSERT INTO messages (chat_id, sender_id, message_content, sent_at) VALUES (:chat_id, :sender_id, :message_content, :sent_at)', {'chat_id': chat_id, 'sender_id': sender_id, 'message_content': message_content, 'sent_at': sent_at})
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    return render_template('message_seller.html', listing=listing)

@app.route('/chat/<chat_id>', methods=['GET', 'POST'])
@login_required
def chat(chat_id):
    conn = get_db_connection()
    messages = conn.execute("""
        SELECT m.message_content, m.sent_at, u.username, m.read_status
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.chat_id = :chat_id
        ORDER BY m.sent_at
    """, {'chat_id': chat_id}).fetchall()
    #when the user whose id is not the sender id  opens the chat, make all the read status boolean true
    conn.execute("""
        UPDATE messages
        SET read_status = TRUE
        WHERE chat_id = :chat_id AND sender_id != :user_id
    """, {'chat_id': chat_id, 'user_id': current_user.id})
    conn.commit()
    

    conn.close()

    if request.method == 'POST':
        message_content = request.form['message']
        sender_id = current_user.id
        sent_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_connection()
        conn.execute('INSERT INTO messages (chat_id, sender_id, message_content, sent_at) VALUES (:chat_id, :sender_id, :message_content, :sent_at)', {'chat_id': chat_id, 'sender_id': sender_id, 'message_content': message_content, 'sent_at': sent_at})
        conn.commit()
        conn.close()
        return redirect(url_for('chat', chat_id=chat_id))
    return render_template('chat.html', messages=messages)


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
        if conn.execute('SELECT * FROM users WHERE username = :username', {'username': username}).fetchone():
            flash('Username is already taken.', 'error')
            conn.close()
            return redirect(url_for('register'))
        conn.execute('INSERT INTO users (username, password, email) VALUES (:username, :password, :email)', {'username': username, 'password': password, 'email': email} )
        conn.commit()
        conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/create-listing', methods=['GET', 'POST'])
@login_required
def create_listing():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = (request.form['price'])
        date_posted = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        seller = str(current_user.id)

        conn = get_db_connection()
        conn.execute('INSERT INTO listings (name, description, price, dateposted, seller_id) VALUES (:name, :description, :price, :date_posted, :seller)', {'name': name, 'description': description, 'price': price, 'date_posted': date_posted, 'seller': seller})
        conn.commit()
        conn.close()

        return redirect(url_for('index'))
    return render_template('create_listing.html')

@app.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    if request.method == 'POST':
        search_query = request.form['search_query']
        conn = get_db_connection()
        listings = conn.execute('SELECT * FROM listings WHERE name LIKE :search_query', {'search_query': '%' + search_query + '%'}).fetchall()
        conn.close()
        return render_template('search.html', listings=listings)
    return render_template('search.html')



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        session = get_db_connection()  # Get the SQLAlchemy session
        user = session.execute('SELECT * FROM users WHERE username = :username AND password = :password', {'username': username, 'password': password}).fetchone()
        session.close()  # Close the session
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
    listings = conn.execute ('SELECT * FROM listings ORDER BY dateposted DESC').fetchall()
    conn.close()
    return render_template('index.html', listings=listings)

if __name__ == '__main__':
    app.run(host='192.168.1.128', port=3000, debug=True)

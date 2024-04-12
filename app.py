from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from flask import jsonify
from flask import request, redirect, url_for
from werkzeug.utils import secure_filename
import os
import pytz


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOADED_IMAGES_DEST'] = 'uploads'


login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

DATABASE_URI = 'sqlite:///marketplace.db'
engine = create_engine(DATABASE_URI, connect_args={'timeout': 15})  # Set a 15-second timeout
db_session = scoped_session(sessionmaker(bind=engine))

# Function to get the current time in UTC
def get_utc_now():
    return datetime.datetime.now(pytz.utc)

# When saving a datetime to the database, use get_utc_now()
date_posted = get_utc_now().strftime("%Y-%m-%d %H:%M:%S")

def get_db_connection():
    return db_session()

class User(UserMixin):
    def __init__(self, id, username, name_first):
        self.id = id
        self.username = username
        self.name_first = name_first


@login_manager.user_loader
def load_user(user_id):
    session = get_db_connection() 
    user = session.execute('SELECT * FROM users WHERE id = :user_id', {'user_id': user_id}).fetchone()
    session.close()
    if user:
        return User(user['id'], user['username'], user['name_first'])
    return None

@app.teardown_appcontext
def shutdown_session(exception=None):
    db_session.remove()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}



@app.route('/user/<username>')
@login_required
def show_user_profile(username):
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = :username", {'username': username}).fetchone()
    # Sort listings by 'is_sold' (unsold first) and then by 'dateposted' (most recent first)
    listings = conn.execute("SELECT * FROM listings WHERE seller_id = :seller_id ORDER BY is_sold ASC, dateposted DESC", {'seller_id': user['id']}).fetchall()
    conn.close()
    return render_template('userpage.html', user=user, listings=listings)


@app.route('/listing/<id>')
@login_required
def show_listing(id):
    conn = get_db_connection()
    listing = conn.execute("SELECT * FROM listings WHERE id = :id", {'id': id}).fetchone()
    seller = conn.execute("SELECT * FROM users WHERE id = :id", {'id': listing['seller_id']}).fetchone()
    saved = conn.execute("SELECT * FROM saves WHERE user_id = :user_id AND listing_id = :listing_id", {'user_id': current_user.id, 'listing_id': id}).fetchone()
    chat = conn.execute("""
        SELECT c.chat_id
        FROM chats c
        WHERE (listing_id = :listing_id AND seller_id = :seller_id AND buyer_id = :buyer_id) OR (listing_id = :listing_id AND seller_id = :buyer_id AND buyer_id = :seller_id)
    """, {'listing_id': id, 'seller_id': seller['id'], 'buyer_id': current_user.id}).fetchone()
    conn.close()

    return render_template('listing.html', listing=listing, sellerusername=seller.username, chat=chat, saved=saved)

@app.route('/listing/<id>/edit', methods=['GET', 'POST'])
@login_required
def edit_listing(id):
    conn = get_db_connection()
    listing = conn.execute("SELECT * FROM listings WHERE id = :id", {'id': id}).fetchone()
    seller = conn.execute("SELECT * FROM users WHERE id = :id", {'id': listing['seller_id']}).fetchone()
    if current_user.id != seller['id']:
        return redirect(url_for('show_listing', id=id))
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = request.form['price']
        image = request.files['image']
        if image and allowed_file(image.filename):
            filename = secure_filename(image.filename)
            image_path = os.path.join(app.config['UPLOADED_IMAGES_DEST'], filename)
            image.save(os.path.join(app.root_path, 'static', image_path))
            conn.execute('UPDATE listings SET name = :name, description = :description, price = :price, image_path = :image_path WHERE id = :id', {'name': name, 'description': description, 'price': price, 'image_path': image_path, 'id': id})
        else:
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
    if not listing:
        # If listing does not exist, redirect to index or another appropriate page
        return redirect(url_for('index'))

    seller = conn.execute("SELECT * FROM users WHERE id = :id", {'id': listing['seller_id']}).fetchone()
    if current_user.id != seller['id']:
        # If the current user is not the seller of the listing, redirect to listing page
        return redirect(url_for('show_listing', id=id))

    # First, delete messages linked to the chats associated with this listing
    conn.execute("""
        DELETE FROM messages WHERE chat_id IN (
            SELECT chat_id FROM chats WHERE listing_id = :id
        )
    """, {'id': id})

    # Then, delete the chats associated with the listing
    conn.execute('DELETE FROM chats WHERE listing_id = :id', {'id': id})

    # Finally, delete the listing itself
    conn.execute('DELETE FROM listings WHERE id = :id', {'id': id})
    conn.commit()
    conn.close()
    return redirect(url_for('index'))


@app.route('/listing/<id>/mark-as-sold', methods=['POST'])
@login_required
def mark_as_sold(id):
    conn = get_db_connection()
    listing = conn.execute("SELECT * FROM listings WHERE id = :id", {'id': id}).fetchone()
    seller = conn.execute("SELECT * FROM users WHERE id = :id", {'id': listing['seller_id']}).fetchone()
    if current_user.id != seller['id']:
        return redirect(url_for('show_listing', id=id))
    if listing['is_sold']:
        conn.execute('UPDATE listings SET is_sold = FALSE WHERE id = :id', {'id': id})
    else:
        conn.execute('UPDATE listings SET is_sold = TRUE WHERE id = :id', {'id': id})
    conn.commit()
    conn.close()
    return redirect(url_for('show_listing', id=id))


@app.route('/save-listing/<int:listing_id>', methods=['POST'])
@login_required
def save_listing(listing_id):
    #if the listing is already saved, unsave it
    conn = get_db_connection()
    saved = conn.execute("SELECT * FROM saves WHERE user_id = :user_id AND listing_id = :listing_id", {'user_id': current_user.id, 'listing_id': listing_id}).fetchone()
    if saved:
        conn.execute("DELETE FROM saves WHERE user_id = :user_id AND listing_id = :listing_id", {'user_id': current_user.id, 'listing_id': listing_id})
        conn.commit()
        conn.close()
        #redirect to the same page
        return redirect(url_for('show_listing', id=listing_id))
    saved_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("INSERT INTO saves (user_id, listing_id, saved_at) VALUES (:user_id, :listing_id, :saved_at)", {'user_id': current_user.id, 'listing_id': listing_id, 'saved_at': saved_at})
    conn.commit()
    conn.close()
    return redirect(url_for('show_listing', id=listing_id))


@app.route('/saved-listings')
@login_required
def saved_listings():
    conn = get_db_connection()
    saved_listings = conn.execute("""
        SELECT l.id, l.name, l.description, l.price, l.dateposted, s.saved_at, l.image_path, l.is_sold
        FROM saves s
        JOIN listings l ON s.listing_id = l.id
        WHERE s.user_id = :user_id
        ORDER BY s.saved_at DESC
    """, {'user_id': current_user.id}).fetchall()
    conn.close()
    return render_template('saved_listings.html', listings=saved_listings)

@app.route('/inbox')
@login_required
def inbox():
    conn = get_db_connection()
    chats = conn.execute("""          
        SELECT c.chat_id, l.name AS listing_name, u.username AS sender_username, m.message_content, m.sent_at, 
       (SELECT COUNT(*) FROM messages WHERE chat_id = c.chat_id AND read_status = 0 AND sender_id != :user_id) AS unread_count,
       seller.name_first AS seller_first_name
        FROM chats c
        JOIN listings l ON c.listing_id = l.id
        JOIN users seller ON l.seller_id = seller.id
        JOIN (
    SELECT chat_id, MAX(sent_at) as max_sent_at
    FROM messages
    GROUP BY chat_id
) latest_msg ON c.chat_id = latest_msg.chat_id
JOIN messages m ON c.chat_id = m.chat_id AND m.sent_at = latest_msg.max_sent_at
JOIN users u ON m.sender_id = u.id
WHERE c.buyer_id = :user_id OR c.seller_id = :user_id
ORDER BY m.sent_at DESC;

    """, {'user_id': current_user.id}).fetchall()
    conn.close()
    return render_template('inbox.html', chats=chats)


@app.route('/message-seller/<listing_id>', methods=['GET', 'POST'])
@login_required
def message_seller(listing_id):
    if request.method == 'POST':
        conn = get_db_connection()
        message_content = request.form['message']
        sender_id = current_user.id
        listing = conn.execute("SELECT * FROM listings WHERE id = :id", {'id': listing_id}).fetchone()
        seller_id = listing['seller_id']
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        chat = conn.execute("""
            SELECT c.chat_id
            FROM chats c
            WHERE (listing_id = :listing_id AND seller_id = :seller_id AND buyer_id = :buyer_id) OR (listing_id = :listing_id AND seller_id = :buyer_id AND buyer_id = :seller_id)
        """, {'listing_id': listing_id, 'seller_id': seller_id, 'buyer_id': current_user.id}).fetchone()
        if not chat:
            conn.execute("INSERT INTO chats (listing_id, seller_id, buyer_id, created_at) VALUES (:listing_id, :seller_id, :buyer_id, :created_at)", {'listing_id': listing_id, 'seller_id': seller_id, 'buyer_id': sender_id, 'created_at': current_time})
            chat_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        else:
            chat_id = chat['chat_id']
        sent_at = get_utc_now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute('INSERT INTO messages (chat_id, sender_id, message_content, sent_at) VALUES (:chat_id, :sender_id, :message_content, :sent_at)', {'chat_id': chat_id, 'sender_id': sender_id, 'message_content': message_content, 'sent_at': sent_at})
        conn.commit()
        conn.close()
        return redirect(url_for('index'))


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
    listing_info = conn.execute("""
        SELECT l.name AS listing_name, l.price 
        FROM chats c
        JOIN listings l ON c.listing_id = l.id
        WHERE c.chat_id = :chat_id
    """, {'chat_id': chat_id}).fetchone()
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
        sent_at = get_utc_now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_connection()
        conn.execute('INSERT INTO messages (chat_id, sender_id, message_content, sent_at) VALUES (:chat_id, :sender_id, :message_content, :sent_at)', {'chat_id': chat_id, 'sender_id': sender_id, 'message_content': message_content, 'sent_at': sent_at})
        conn.commit()
        conn.close()
        return redirect(url_for('chat', chat_id=chat_id))
    return render_template('chat.html', messages=messages, chat_id=chat_id, listing_name=listing_info['listing_name'], price=listing_info['price'])

@app.route('/get_messages/<chat_id>', methods=['GET'])
def get_messages(chat_id):
    conn = get_db_connection()
    messages = conn.execute("""
        SELECT m.message_content, m.sent_at, u.username, m.read_status
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.chat_id = :chat_id
        ORDER BY m.sent_at
    """, {'chat_id': chat_id}).fetchall()
    conn.execute("""
        UPDATE messages
        SET read_status = TRUE
        WHERE chat_id = :chat_id AND sender_id != :user_id
    """, {'chat_id': chat_id, 'user_id': current_user.id})
    conn.commit()
    conn.close()
    messages_dict = [dict(message) for message in messages]
    return jsonify(messages_dict)



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        first = request.form['first']
        last = request.form['last']
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
        conn.execute('INSERT INTO users (username, name_first, name_last, password, email) VALUES (:username, :name_first, :name_last, :password, :email)', {'username': username,'name_first': first,  'name_last': last, 'password': password, 'email': email} )
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
        price = request.form['price']
        date_posted = get_utc_now().strftime("%Y-%m-%d %H:%M:%S")
        seller = str(current_user.id)

        # Handle image upload
        image = request.files['image']
        if image:
            # Generate a unique filename by appending a timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            filename = secure_filename(f"{timestamp}_{image.filename}")
            # Save the image in the 'uploads' folder inside the 'static' directory
            image_path = os.path.join('uploads', filename)
            image.save(os.path.join('static', image_path))  # Save the image to the filesystem

        conn = get_db_connection()
        conn.execute('INSERT INTO listings (name, description, price, dateposted, seller_id, image_path) VALUES (:name, :description, :price, :date_posted, :seller, :image_path)', {'name': name, 'description': description, 'price': price, 'date_posted': date_posted, 'seller': seller, 'image_path': image_path})
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
            login_user(User(user['id'], user['username'], user['name_first']))
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html')



@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/home', methods=['GET', 'POST'])
@login_required
def index():
    conn = get_db_connection()
    listings = conn.execute ('SELECT * FROM listings where is_sold = "0" ORDER BY dateposted DESC').fetchall()
    conn.close()
    return render_template('index.html', listings=listings)

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return redirect(url_for('login'))

#get the number of unread messages and give that info to the header.html
@app.context_processor
def unread_message_count():
    if current_user.is_authenticated:
        conn = get_db_connection()
        unread_count = conn.execute("""
            SELECT COUNT(*) AS unread_count
            FROM messages
            WHERE chat_id IN (
                SELECT chat_id
                FROM chats
                WHERE (buyer_id = :user_id OR seller_id = :user_id)
            ) AND read_status = "0" AND sender_id != :user_id
        """, {'user_id': current_user.id}).fetchone()
        conn.close()
        return (unread_count)
    return {'unread_count': 0}

    


if __name__ == '__main__':
    app.run(debug=True )

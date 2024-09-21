from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Folder to store uploaded images
UPLOAD_FOLDER = 'static/uploads/'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Allowed file extensions for image upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database setup
def get_db_connection():
    conn = sqlite3.connect('events.db')
    conn.row_factory = sqlite3.Row
    return conn

# Home (Login) Page
@app.route('/')
def home():
    return render_template('login.html')

# Login Route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ? AND role = ?', (email, role)).fetchone()
        conn.close()

        if user and user['password'] == password:
            session['user'] = user['email']
            session['role'] = user['role']
            
            # Redirect based on role
            if user['role'] == 'student':
                return redirect(url_for('student_dashboard'))
            elif user['role'] == 'organizer':
                return redirect(url_for('organizer_dashboard'))
            elif user['role'] == 'admin':  # Admin Role
                return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid login credentials')
            return redirect(url_for('login'))

    return render_template('login.html')



# Student Dashboard (Event Browsing)
@app.route('/student_dashboard', methods=['GET'])
def student_dashboard():
    if 'user' not in session or session['role'] != 'student':
        return redirect(url_for('home'))

    # Get the filter parameters from the request
    search = request.args.get('search')
    max_price = request.args.get('price')
    keywords = request.args.get('keywords')
    date_range = request.args.get('date-range')
    location = request.args.get('location')
    group_restriction = request.args.get('group')
    free_food = request.args.get('free-food')

    # Query to select only approved events
    query = "SELECT * FROM events WHERE status = 'approved'"
    query_params = []

    # Search by event name
    if search:
        query += " AND name LIKE ?"
        query_params.append(f"%{search}%")

    # Filter by maximum price
    if max_price:
        query += " AND price <= ?"
        query_params.append(max_price)

    # Filter by keywords (area of interest)
    if keywords:
        keyword_list = [f"%{keyword.strip()}%" for keyword in keywords.split(",")]
        query += " AND (" + " OR ".join("keywords LIKE ?" for _ in keyword_list) + ")"
        query_params.extend(keyword_list)

    # Filter by date range
    if date_range:
        today = datetime.now().date()
        if date_range == 'next-week':
            next_week_start = today + timedelta(days=(7 - today.weekday()))  # Next Monday
            next_week_end = next_week_start + timedelta(days=6)  # Next Sunday
            query += " AND date BETWEEN ? AND ?"
            query_params.extend([next_week_start, next_week_end])
        elif date_range == 'next-month':
            next_month_start = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
            next_month_end = (next_month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            query += " AND date BETWEEN ? AND ?"
            query_params.extend([next_month_start, next_month_end])
        elif date_range == 'today':
            query += " AND date = ?"
            query_params.append(today)
        elif date_range == 'upcoming-weekend':
            # Get the dates for the upcoming Saturday and Sunday
            days_ahead = (5 - today.weekday()) % 7  # Days until Saturday
            saturday = today + timedelta(days_ahead)
            sunday = saturday + timedelta(days=1)
            query += " AND date BETWEEN ? AND ?"
            query_params.extend([saturday, sunday])

    # Filter by location
    if location:
        query += " AND location LIKE ?"
        query_params.append(f"%{location}%")

    # Filter by group restriction
    if group_restriction:
        if group_restriction == "anyone":
            query += " AND group_restriction = 'anyone'"
        elif group_restriction == "university":
            query += " AND group_restriction = 'university'"

    # Filter by free food
    if free_food:
        query += " AND free_food = ?"
        query_params.append(free_food)

    # Fetch the approved events
    conn = get_db_connection()
    events = conn.execute(query, query_params).fetchall()
    conn.close()

    return render_template('student_dashboard.html', events=events)

@app.route('/register_event/<int:event_id>', methods=['GET', 'POST'])
def register_event(event_id):
    conn = get_db_connection()

    if request.method == 'POST':
        # Collect form data
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        university = request.form['university']

        # Check if the student is already registered for the event
        existing_registration = conn.execute('''
            SELECT * FROM registrations WHERE event_id = ? AND student_email = ?
        ''', (event_id, email)).fetchone()

        if existing_registration:
            flash('You have already registered for this event.')
            return redirect(url_for('student_dashboard'))

        # Insert registration details into the database
        conn.execute('''
            INSERT INTO registrations (event_id, student_name, student_email, phone, university)
            VALUES (?, ?, ?, ?, ?)
        ''', (event_id, name, email, phone, university))
        conn.commit()
        conn.close()

        flash('You have successfully registered for the event!')
        return redirect(url_for('student_dashboard'))

    # Fetch the event details to display on the form
    event = conn.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    conn.close()

    return render_template('register_event.html', event=event)



@app.route('/food_events', methods=['GET'])
def food_events():
    location = request.args.get('location')
    event_date = request.args.get('event-date')  # Get selected date from the calendar

    query = "SELECT * FROM events WHERE free_food = 'yes'"
    query_params = []

    # Filter by location
    if location:
        query += " AND location LIKE ?"
        query_params.append(f"%{location}%")

    # Filter by specific date
    if event_date:
        query += " AND date = ?"
        query_params.append(event_date)

    # Sort by date in ascending order
    query += " ORDER BY date ASC"

    conn = get_db_connection()
    events = conn.execute(query, query_params).fetchall()
    conn.close()

    return render_template('food_events.html', events_on_selected_date=events, selected_date=event_date)

@app.route('/admin_dashboard', methods=['GET'])
def admin_dashboard():
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('home'))

    conn = get_db_connection()
    all_events = conn.execute('SELECT * FROM events').fetchall()
    pending_events = conn.execute('SELECT * FROM events WHERE status = "pending"').fetchall()
    conn.close()

    return render_template('admin_dashboard.html', pending_events=pending_events)

@app.route('/admin_approve_reject/<int:event_id>/<string:action>', methods=['POST'])
def admin_approve_reject(event_id, action):
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('home'))

    conn = get_db_connection()

    if action == 'approve':
        conn.execute('UPDATE events SET status = "approved" WHERE id = ?', (event_id,))
        flash('Event approved successfully!')
    elif action == 'reject':
        conn.execute('UPDATE events SET status = "rejected" WHERE id = ?', (event_id,))
        flash('Event rejected successfully!')

    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))


# Logout Route
@app.route('/logout')
def logout():
    # Clear the user session
    session.clear()
    
    # Render the logout success page with a countdown timer
    return render_template('logout_success.html')

if __name__ == '__main__':
    app.run(debug=True)

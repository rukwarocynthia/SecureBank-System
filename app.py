from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, timedelta
from reportlab.pdfgen import canvas
from dotenv import load_dotenv
load_dotenv()
import os
import sqlite3

app = Flask(__name__)

# ------------------- EMAIL CONFIGURATION ------------------- #
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')
mail = Mail(app)

# ------------------- GLOBAL CONSTANTS ------------------- #
ADMIN_EMAIL = "rukwarocynthia4093@gmail.com"
APPROVAL_LIMIT = 100000
TRANSFER_LIMIT = 100000
FRAUD_LIMIT = 500000
app.secret_key = "bank_secret_key"
serializer = URLSafeTimedSerializer(app.secret_key)

if os.environ.get('RENDER'):
    DATABASE_PATH = 'bank.db'
else:
    DATABASE_PATH = 'bank.db'

# ------------------- DATABASE INITIALIZATION ------------------- #
def create_tables():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 1. Users table 
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            is_admin INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active'
        )
    ''')

    # 2. Accounts table 
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            account_type TEXT NOT NULL,
            balance REAL DEFAULT 0.0,
            status TEXT DEFAULT 'active',
            maturity_date TEXT,
            interest_rate REAL DEFAULT 0.0,
            FOREIGN KEY (user_id) REFERENCES Users(id)
        )
    ''')

    # 3. Transactions table (Matches your deposit/withdraw logic)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            transaction_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            receiver_account TEXT,
            reference TEXT,
            description TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES Accounts(id),
            FOREIGN KEY (user_id) REFERENCES Users(id)
        )
    ''')

    # Seed Admin User
    admin_pass = generate_password_hash("kca2026")
    cursor.execute('''
        INSERT OR IGNORE INTO Users (username, password, email, is_admin, status)
        VALUES (?, ?, ?, ?, ?)
    ''', ("admin_cynthia", admin_pass, "rukwarocynthia4093@gmail.com", 1, "active"))

    conn.commit()
    conn.close()

create_tables()

# ------------------- DATABASE CONNECTION ------------------- #
def get_db_connection():

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ------------------- EMAIL & PDF UTILITIES ------------------- #
def send_email(subject, body, recipient=ADMIN_EMAIL):
    """Send email notification."""
    msg = Message(subject, sender=app.config['MAIL_USERNAME'], recipients=[recipient])
    msg.body = body
    mail.send(msg)

def generate_pdf(tx_id, sender, receiver, amount):
    """Generate PDF receipt for transfers."""
    filename = f"receipt_{tx_id}.pdf"
    filepath = os.path.join("static", filename)

    c = canvas.Canvas(filepath)
    c.drawString(100, 750, "BANK TRANSFER RECEIPT")
    c.drawString(100, 700, f"Transaction ID: {tx_id}")
    c.drawString(100, 670, f"Sender Account: {sender}")
    c.drawString(100, 640, f"Receiver Account: {receiver}")
    c.drawString(100, 610, f"Amount: {amount}")
    c.drawString(100, 580, f"Date: {datetime.now()}")
    c.save()

    return filename

# ------------------- HOME ------------------- #
@app.route("/")
def home():
    return render_template("home.html")

# ------------------- REGISTER ------------------- #
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check username
        cursor.execute("SELECT * FROM Users WHERE username=?", (username,))
        if cursor.fetchone():
            flash("Username already exists!", "danger")
            conn.close()
            return render_template("register.html")

        # Check email
        cursor.execute("SELECT * FROM Users WHERE email=?", (email,))
        if cursor.fetchone():
            flash("Email already registered!", "danger")
            conn.close()
            return render_template("register.html")

        cursor.execute(
            "INSERT INTO Users (username, email, password, status, is_admin) VALUES (?, ?, ?, ?, ?)",
            (username, email, hashed_password, 'active', 0)
        )
        
        conn.commit()
        conn.close()

        flash("Account created successfully! You can now login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")

# ------------------- COLLECT INTEREST ------------------- #
@app.route("/collect_interest/<int:account_id>", methods=["POST"])
def collect_interest(account_id):
    if "user_id" not in session: return redirect(url_for("login"))
    
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    account = conn.execute("SELECT * FROM Accounts WHERE id = ?", (account_id,)).fetchone()
    
    if account and account['account_type'] == "Fixed Deposit":
        today = datetime.now().strftime('%Y-%m-%d')
        
        if today >= account['maturity_date']:
            interest = account['balance'] * 0.10
            new_balance = account['balance'] + interest
            
            # Update account: Add interest and remove maturity date (unlocking it)
            # Or you can convert it to a 'Savings' account automatically
            conn.execute(
                "UPDATE Accounts SET balance = ?, maturity_date = NULL, account_type = 'Savings' WHERE id = ?", 
                (new_balance, account_id)
            )
            
            # Record the transaction
            conn.execute(
                "INSERT INTO Transactions (user_id, amount, type, status) VALUES (?, ?, ?, ?)",
                (session['user_id'], interest, 'Interest Payout', 'completed')
            )
            
            conn.commit()
            flash(f"Success! KES {interest:,.2f} interest added. Account is now unlocked.", "success")
        else:
            flash("Account is still locked!", "danger")
            
    conn.close()
    return redirect(url_for("dashboard"))

# ------------------- LOGIN ------------------- #
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        # Using row_factory allows us to access columns by name (user['id']) 
        # instead of index (user[0]), which is safer.
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM Users WHERE username=?", (username,))
        user = cursor.fetchone()
        conn.close()

        # 1. Check if user exists and password is correct
        if user and check_password_hash(user["password"], password):
            
            # 2. CRITICAL: Check if the user is frozen
            if user["status"] == "frozen":
                flash("Your account is frozen. Please contact administration.", "danger")
                return render_template("login.html")

            # 3. If not frozen, setup session
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = user["is_admin"]

            # 4. Redirect based on role
            if user["is_admin"] == 1:
                return redirect(url_for("admin_dashboard"))
            
            return redirect(url_for("dashboard"))

        # If password check fails or user not found
        flash("Invalid login details", "danger")

    return render_template("login.html")

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Users WHERE email=?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user:
            token = serializer.dumps(email, salt='password-reset-salt')
            reset_link = url_for('reset_password', token=token, _external=True)

            msg = Message(
                subject="SecureBank Password Reset",
                sender=app.config['MAIL_USERNAME'],
                recipients=[email]
            )
            msg.body = f"""
Hello,

Click the link below to reset your password:
{reset_link}

This link expires in 15 minutes.
"""
            mail.send(msg)

        flash("If this email exists, a reset link has been sent.", "info")
        return redirect(url_for('login'))

    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        # 1. Decode the token (900 seconds = 15 minutes)
        email = serializer.loads(
            token,
            salt='password-reset-salt',
            max_age=900
        )
    except Exception:
        flash("The reset link is invalid or has expired.", "danger")
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        # 2. Add a mismatch check
        if new_password != confirm_password:
            flash("Passwords do not match. Please try again.", "danger")
            return render_template('reset_password.html', token=token)

        # 3. Securely hash and update
        hashed_password = generate_password_hash(new_password)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE Users SET password=? WHERE email=?",
            (hashed_password, email)
        )
        conn.commit()
        conn.close()

        flash("Password reset successful! You can now log in.", "success")
        return redirect(url_for('login'))

    return render_template('reset_password.html', token=token)

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Users WHERE id=?", (session["user_id"],))
    user = cursor.fetchone()

    if request.method == "POST":
        new_username = request.form["username"]
        new_email = request.form["email"]

        # Check for duplicates
        cursor.execute("SELECT * FROM Users WHERE username=? AND id!=?", (new_username, session["user_id"]))
        if cursor.fetchone():
            flash("Username already taken!", "error")
            conn.close()
            return render_template("profile.html", user=user)

        cursor.execute("SELECT * FROM Users WHERE email=? AND id!=?", (new_email, session["user_id"]))
        if cursor.fetchone():
            flash("Email already in use!", "error")
            conn.close()
            return render_template("profile.html", user=user)

        cursor.execute(
            "UPDATE Users SET username=?, email=? WHERE id=?",
            (new_username, new_email, session["user_id"])
        )
        conn.commit()
        conn.close()

        session["username"] = new_username  # Update session
        flash("Profile updated successfully!", "success")
        return redirect(url_for("profile"))

    conn.close()
    return render_template("profile.html", user=user)

# ------------------- DASHBOARD ------------------- #
from datetime import datetime

@app.route("/dashboard")
def dashboard():
    # 1. Access & Admin Check
    if "user_id" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") in [1, True]:
        return redirect(url_for("admin_dashboard"))

    user_id = session["user_id"]
    username = session.get("username")
    today_str = datetime.now().strftime('%Y-%m-%d')

    # 2. Fetch Data
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row  # Crucial for using account['balance']
    cursor = conn.cursor()

    # Get User Accounts
    accounts = cursor.execute("SELECT * FROM Accounts WHERE user_id=?", (user_id,)).fetchall()

    pending_data = cursor.execute(
        "SELECT SUM(amount) as total_pending FROM Transactions WHERE user_id = ? AND status = 'pending'", 
        (user_id,)
    ).fetchone()
    pending_amount = pending_data['total_pending'] if pending_data['total_pending'] else 0

    # 4. Calculate Projected Interest
    projected_interest = 0
    for acc in accounts:
        if acc['account_type'] == 'Fixed Deposit' and acc['balance'] > 0:
            # Using the interest_rate from DB if it exists, otherwise default to 0.10
            rate = acc['interest_rate'] if 'interest_rate' in acc.keys() else 0.10
            projected_interest += (acc['balance'] * rate)

    conn.close()

    # 5. Render Template
    return render_template(
        "dashboard.html",
        username=username,
        accounts=accounts,
        today=today_str,
        pending_amount=pending_amount,
        projected_interest=projected_interest,
        is_admin=False
    )
# ------------------- CREATE ACCOUNT ------------------- #
@app.route("/create_account", methods=["POST"])
def create_account():
    if "user_id" not in session:
        return redirect(url_for("login"))

    account_type = request.form.get("account_type")
    user_id = session["user_id"]
    
    # Define default rates
    interest_rate = 0.02  
    maturity_date = None
    
    if account_type == "Fixed Deposit":
        interest_rate = 0.10 
    elif account_type == "Current":
        interest_rate = 0.00  

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """INSERT INTO Accounts 
               (user_id, account_type, balance, status, maturity_date, interest_rate) 
               VALUES (?, ?, 0, 'active', ?, ?)""",
            (user_id, account_type, maturity_date, interest_rate)
        )
        conn.commit()
        flash(f"New {account_type} opened successfully!", "success")
    except sqlite3.Error as e:
        flash(f"Database error: {e}", "danger")
    finally:
        conn.close()
    
    return redirect(url_for("dashboard"))

from datetime import datetime

# ------------------- REGULAR DEPOSIT ------------------- #
@app.route("/deposit/<int:account_id>", methods=["GET", "POST"])
def deposit(account_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()

    try:
        # Check ownership and type
        cursor.execute("SELECT * FROM Accounts WHERE id=? AND account_type != 'Fixed Deposit'", (account_id,))
        account = cursor.fetchone()
        
        if not account or account["user_id"] != session["user_id"]:
            flash("Unauthorized access or account not found.", "danger")
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            amount = float(request.form.get("amount", 0))
            if amount <= 0:
                flash("Enter a valid amount.", "warning")
                return redirect(url_for("deposit", account_id=account_id))

            # Check against the global APPROVAL_LIMIT
            status = "pending" if amount >= APPROVAL_LIMIT else "approved"

            if status == "approved":
                cursor.execute("UPDATE Accounts SET balance = balance + ? WHERE id=?", (amount, account_id))
                flash("Deposit successful!", "success")
            else:
                flash(f"KES {amount:,.2f} exceeds limit. Waiting for Admin Approval.", "warning")

            # Log Transaction
            cursor.execute("""
                INSERT INTO Transactions (user_id, account_id, amount, transaction_type, status) 
                VALUES (?, ?, ?, 'Deposit', ?)
            """, (session["user_id"], account_id, amount, status))
            
            conn.commit()
            return redirect(url_for("dashboard"))

    except Exception as e:
        conn.rollback()
        flash("A system error occurred.", "danger")
    finally:
        conn.close() 

    return render_template("deposit.html", account=account)


# ------------------- FIXED DEPOSIT SETUP ------------------- #
@app.route("/deposit_fixed/<int:account_id>", methods=["GET", "POST"])
def deposit_fixed(account_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row # Added for dictionary-style access
    cursor = conn.cursor()
    
    try:
        # Check ownership
        cursor.execute("SELECT * FROM Accounts WHERE id=? AND user_id=?", (account_id, session["user_id"]))
        account = cursor.fetchone()

        if not account:
            flash("Account not found.", "danger")
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            amount_str = request.form.get("amount")
            user_date = request.form.get("maturity_date")

            if not amount_str or float(amount_str) <= 0:
                flash("Please enter a valid deposit amount.", "warning")
                return redirect(url_for("deposit_fixed", account_id=account_id))

            amount = float(amount_str)
        
            # Update specifically for the logged-in user
            cursor.execute("""
                UPDATE Accounts 
                SET balance = balance + ?, 
                    maturity_date = ?, 
                    status = 'active' 
                WHERE id = ? AND user_id = ?
            """, (amount, user_date, account_id, session["user_id"]))

            cursor.execute("""
                INSERT INTO Transactions (user_id, account_id, amount, transaction_type, status, description) 
                VALUES (?, ?, ?, 'Fixed Deposit', 'approved', ?)
            """, (session["user_id"], account_id, amount, f"Fixed Deposit locked until {user_date}"))

            conn.commit()
            flash(f"Success! KES {amount:,.2f} locked until {user_date}.", "success")
            return redirect(url_for("dashboard"))

    except Exception as e:
        conn.rollback() 
        flash("An error occurred while processing your deposit.")
        return redirect(url_for("dashboard"))
    finally:
        conn.close()

    today = datetime.now().strftime('%Y-%m-%d')
    return render_template("deposit_fixed.html", account=account, min_date=today)

# ------------------- WITHDRAW ------------------- #
@app.route("/withdraw/<int:account_id>", methods=["GET", "POST"])
def withdraw(account_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    is_admin = session.get("is_admin") == 1
    current_user_id = session.get("user_id") # Clarified variable name

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch account details
    cursor.execute("SELECT * FROM Accounts WHERE id=?", (account_id,))
    account = cursor.fetchone()

    # Security & Status Checks
    if not account or (not is_admin and account["user_id"] != current_user_id):
        conn.close()
        flash("Unauthorized access or account not found.")
        return redirect(url_for("dashboard"))
    
    if account["status"] == "frozen":
        conn.close()
        flash("This account is frozen. Transactions are disabled.")
        return redirect(url_for("dashboard"))

    # Fixed Deposit Maturity Check
    if account["account_type"] == "Fixed Deposit" and not is_admin:
        maturity_str = account["maturity_date"]
        if maturity_str:
            try:
                maturity_date = datetime.strptime(maturity_str, '%Y-%m-%d').date()
                if datetime.now().date() < maturity_date:
                    conn.close()
                    flash(f"Access Denied: Fixed Deposit matures on {maturity_str}.")
                    return redirect(url_for("dashboard"))
            except ValueError:
                pass

    if request.method == "POST":
        try:
            try:
                amount = float(request.form["amount"])
            except ValueError:
                flash("Please enter a valid numeric amount.")
                return redirect(url_for("withdraw", account_id=account_id))

            if amount <= 0:
                flash("Amount must be greater than zero.")
                return redirect(url_for("withdraw", account_id=account_id))

            if amount > account["balance"]:
                flash("Insufficient funds.")
                return redirect(url_for("withdraw", account_id=account_id))

            # --- TRANSACTION LOGIC ---
            if is_admin or amount <= APPROVAL_LIMIT:
                cursor.execute("UPDATE Accounts SET balance = balance - ? WHERE id=?", (amount, account_id))
                status = "approved"
                flash(f"Successfully withdrawn KES {amount:,.2f}", "success")
            else:
                status = "pending"
                flash("Amount exceeds limit. Withdrawal pending admin approval.", "warning")

            # FIX: Included user_id to resolve IntegrityError
            cursor.execute(
                "INSERT INTO Transactions (account_id, user_id, amount, transaction_type, status) VALUES (?, ?, ?, ?, ?)",
                (account_id, current_user_id, amount, "Withdraw", status)
            )
            
            conn.commit() # Commit all changes together
            return redirect(url_for("dashboard"))

        except Exception as e:
            conn.rollback() # Undo changes if something fails (prevents partial updates)
            flash(f"An error occurred: {str(e)}")
            return redirect(url_for("withdraw", account_id=account_id))
        finally:
            conn.close() # Always close connection, even if an exception was raised

    conn.close()
    return render_template("withdraw.html", account=account)

# ------------------- TRANSFER ------------------- #
@app.route("/transfer/<int:account_id>", methods=["GET", "POST"])
def transfer(account_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get sender account
    cursor.execute("SELECT * FROM Accounts WHERE id=? AND (user_id=? OR ?)", 
                   (account_id, session["user_id"], session.get("is_admin")))
    sender = cursor.fetchone()

    if not sender:
        conn.close()
        flash("Sender account not found", "error")
        return redirect(url_for("dashboard"))

    # Block transfers OUT of a locked Fixed Deposit
    if sender["account_type"] == "Fixed Deposit" and sender["maturity_date"]:
        today = datetime.now().strftime('%Y-%m-%d')
        if today < sender["maturity_date"]:
            flash("Cannot transfer from a Locked Fixed Deposit until maturity!", "danger")
            return redirect(url_for("dashboard"))

    # Get receivers
    cursor.execute("SELECT a.id, a.account_type, u.username FROM Accounts a JOIN Users u ON a.user_id = u.id WHERE a.id != ?", (account_id,))
    receivers = cursor.fetchall()

    if request.method == "POST":
        receiver_id = int(request.form["receiver"])
        amount = float(request.form["amount"])

        cursor.execute("SELECT * FROM Accounts WHERE id=?", (receiver_id,))
        receiver = cursor.fetchone()

        if amount <= 0 or sender["balance"] < amount:
            flash("Invalid amount or insufficient funds", "error")
            return redirect(url_for("transfer", account_id=account_id))

        status = "approved" if amount <= TRANSFER_LIMIT or session.get("is_admin") else "pending"

        if status == "approved":
            cursor.execute("UPDATE Accounts SET balance = balance - ? WHERE id=?", (amount, account_id))
            cursor.execute("UPDATE Accounts SET balance = balance + ? WHERE id=?", (amount, receiver_id))
            
            # --- FIXED DEPOSIT ACTIVATION ---
            if receiver["account_type"] == "Fixed Deposit" and not receiver["maturity_date"]:
                maturity = (datetime.now() + timedelta(days=180)).strftime('%Y-%m-%d')
                cursor.execute("UPDATE Accounts SET maturity_date = ? WHERE id = ?", (maturity, receiver_id))
            # --------------------------------
            
            flash("Transfer successful!", "success")
        else:
            flash("Transfer submitted for approval.", "warning")

        cursor.execute("""
            INSERT INTO Transactions (user_id, account_id, receiver_account, amount, transaction_type, status)
            VALUES (?, ?, ?, ?, 'Transfer', ?)
        """, (session["user_id"], account_id, receiver_id, amount, status))

        conn.commit()
        conn.close()
        return redirect(url_for("dashboard"))

    conn.close()
    return render_template("transfer.html", sender=sender, receivers=receivers)

# ------------------- DOWNLOAD PDF ------------------- #
@app.route("/download/<filename>")
def download_receipt(filename):
    return redirect(url_for('static', filename=filename))

# ------------------- TRANSACTIONS ------------------- #
@app.route("/transactions")
def transactions():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.amount, t.transaction_type, t.status, t.timestamp, t.receiver_account, a.account_type
        FROM Transactions t
        JOIN Accounts a ON t.account_id = a.id
        WHERE a.user_id=?
    """, (session["user_id"],))
    data = cursor.fetchall()
    conn.close()
    return render_template("transactions.html", transactions=data)

# ------------------- LOGOUT ------------------- #
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ------------------- ADMIN DASHBOARD ------------------- #
@app.route("/admin")
def admin_dashboard():
    if "user_id" not in session or not session.get("is_admin"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. General Stats
    cursor.execute("SELECT COUNT(*) FROM Users")
    total_users = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(balance) FROM Accounts")
    total_balance = cursor.fetchone()[0] or 0

    # 2. Asset Distribution (For Doughnut Chart)
    cursor.execute("SELECT account_type, SUM(balance) FROM Accounts GROUP BY account_type")
    asset_data = dict(cursor.fetchall())

    # 3. User Table Data
    cursor.execute("SELECT id, username, email, status FROM Users")
    users = cursor.fetchall()

    # 4. Account Table Data (Joined with Users)
    cursor.execute("""
        SELECT a.id, u.username, a.account_type, a.balance, a.status 
        FROM Accounts a
        JOIN Users u ON a.user_id = u.id
    """)
    all_accounts = cursor.fetchall()

    # 5. Pending Transactions
    cursor.execute("""
        SELECT t.id, u.username, t.amount 
        FROM Transactions t
        JOIN Accounts a ON t.account_id = a.id
        JOIN Users u ON a.user_id = u.id
        WHERE t.status = 'pending'
    """)
    pending_transactions = cursor.fetchall()

    # 6. Dynamic Volume Data (Last 7 Days for Line Chart)
    chart_labels = []
    chart_data = []
    
    for i in range(6, -1, -1):
        target_date = date.today() - timedelta(days=i)
        
        chart_labels.append(target_date.strftime('%a'))
        db_date = target_date.strftime('%Y-%m-%d')
        
        cursor.execute("SELECT SUM(amount) FROM Transactions WHERE DATE(timestamp) = ?", (db_date,))
        daily_sum = cursor.fetchone()[0] or 0
        chart_data.append(float(daily_sum))

    conn.close()
    
    return render_template("admin.html", 
                           users=users, 
                           accounts=all_accounts,
                           pending_transactions=pending_transactions,
                           total_users=total_users, 
                           total_balance=total_balance,
                           savings_sum=asset_data.get('Savings', 0),
                           current_sum=asset_data.get('Current', 0),
                           fixed_sum=asset_data.get('Fixed Deposit', 0),
                           chart_labels=chart_labels,
                           chart_data=chart_data)

@app.route("/admin/distribute_interest", methods=["POST"])
def distribute_interest():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Define interest rates
    rates = {
        'Savings': 0.05,  # 5%
        'Fixed': 0.10,    # 10%
        'Current': 0.00   # 0%
    }
    
    for acc_type, rate in rates.items():
        # Update balance: new_balance = old_balance + (old_balance * rate)
        cursor.execute("""
            UPDATE Accounts 
            SET balance = balance + (balance * ?) 
            WHERE account_type = ? AND status = 'active'
        """, (rate, acc_type))
    
    conn.commit()
    conn.close()
    flash("Interest has been successfully distributed to all active accounts!", "success")
    return redirect(url_for("admin_dashboard"))

# ------------------- APPROVE TRANSACTION ------------------- #
@app.route("/admin/approve_transaction/<int:tx_id>", methods=["POST"])
def approve_transaction(tx_id):
    if "user_id" not in session or not session.get("is_admin"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    
    # Fetch the pending transaction
    cursor.execute("SELECT * FROM Transactions WHERE id=?", (tx_id,))
    tx = cursor.fetchone()
    
    if tx and tx["status"] == "pending":
        account_id = tx["account_id"]
        amount = tx["amount"]
        tx_type = tx["type"] if "type" in tx.keys() else tx["transaction_type"]

        try:
            if tx_type == "Deposit":
                cursor.execute("UPDATE Accounts SET balance = balance + ? WHERE id=?", (amount, account_id))
            
            elif tx_type == "Withdraw":
                cursor.execute("UPDATE Accounts SET balance = balance - ? WHERE id=?", (amount, account_id))
            
            elif tx_type == "Transfer":
                receiver_id = tx["receiver_id"] if "receiver_id" in tx.keys() else tx.get("receiver_account")
                if receiver_id:
                    cursor.execute("UPDATE Accounts SET balance = balance - ? WHERE id=?", (amount, account_id))
                    cursor.execute("UPDATE Accounts SET balance = balance + ? WHERE id=?", (amount, receiver_id))
                else:
                    flash("Error: Receiver account not found for this transfer.", "danger")
                    conn.close()
                    return redirect(url_for("admin_dashboard"))

            # Finally, mark as approved
            cursor.execute("UPDATE Transactions SET status='approved' WHERE id=?", (tx_id,))
            conn.commit()
            flash(f"Transaction #{tx_id} ({tx_type}) approved. Balances updated.", "success")
            
        except Exception as e:
            conn.rollback()
            flash(f"Error processing approval: {str(e)}", "danger")

    conn.close()
    return redirect(url_for("admin_dashboard"))

# ------------------- REJECT TRANSACTION ------------------- #
@app.route("/admin/reject_transaction/<int:tx_id>", methods=["POST"])
def reject_transaction(tx_id):
    if "user_id" not in session or not session.get("is_admin"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE Transactions SET status='rejected' WHERE id=?", (tx_id,))
    conn.commit()
    conn.close()
    
    flash(f"Transaction #{tx_id} has been rejected. No funds were moved.", "info")
    return redirect(url_for("admin_dashboard"))

# ------------------- USER MANAGEMENT ------------------- #
@app.route("/admin/toggle_user_freeze/<int:user_id>", methods=["POST"])
def toggle_user_freeze(user_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    user = conn.execute("SELECT status FROM Users WHERE id=?", (user_id,)).fetchone()
    if user:
        new_status = "frozen" if user["status"] == "active" else "active"
        conn.execute("UPDATE Users SET status=? WHERE id=?", (new_status, user_id))
        conn.commit()
    conn.close()
    flash("User access status updated.")
    return redirect(url_for("admin_dashboard"))

# --- TOGGLE ACCOUNT (Blocks specific Account) ---
@app.route("/admin/toggle_account_freeze/<int:acc_id>", methods=["POST"])
def toggle_account_freeze(acc_id):
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    acc = conn.execute("SELECT status FROM Accounts WHERE id=?", (acc_id,)).fetchone()
    if acc:
        new_status = "frozen" if acc["status"] == "active" else "active"
        conn.execute("UPDATE Accounts SET status=? WHERE id=?", (new_status, acc_id))
        conn.commit()
    conn.close()
    flash("Specific account status updated.")
    return redirect(url_for("admin_dashboard"))

# --- DELETE ACCOUNT ---
@app.route("/admin/delete_account/<int:account_id>", methods=["POST"])
def delete_account(account_id):
    if "user_id" not in session or not session.get("is_admin"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("UPDATE Transactions SET account_id = NULL WHERE account_id = ? AND transaction_type = 'Transfer'", (account_id,))
        cursor.execute("UPDATE Transactions SET receiver_account = NULL WHERE receiver_account = ?", (account_id,))

        cursor.execute("DELETE FROM Transactions WHERE account_id = ? AND transaction_type != 'Transfer'", (account_id,))
        cursor.execute("DELETE FROM Accounts WHERE id = ?", (account_id,))

        conn.commit()
        flash("Account deleted. Transfer history preserved for recipients.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for("admin_dashboard"))

# --- DELETE USER ---
@app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if "user_id" not in session or not session.get("is_admin"):
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # 1. Get all accounts for this user
        cursor.execute("SELECT id FROM Accounts WHERE user_id = ?", (user_id,))
        accounts = [row[0] for row in cursor.fetchall()]

        for acc_id in accounts:
            cursor.execute("UPDATE Transactions SET account_id = NULL WHERE account_id = ? AND transaction_type = 'Transfer'", (acc_id,))
            cursor.execute("UPDATE Transactions SET receiver_account = NULL WHERE receiver_account = ?", (acc_id,))
            
            # 3. Delete Private Transactions
            cursor.execute("DELETE FROM Transactions WHERE account_id = ? AND transaction_type != 'Transfer'", (acc_id,))

        # 4. Delete all Accounts
        cursor.execute("DELETE FROM Accounts WHERE user_id = ?", (user_id,))

        # 5. Delete the User
        cursor.execute("DELETE FROM Users WHERE id = ?", (user_id,))

        conn.commit()
        flash("User and all associated accounts deleted successfully.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for("admin_dashboard"))

# ------------------- RUN APP ------------------- #
if __name__ == "__main__":
    # 1. Get the PORT from Render (defaults to 5000 if running locally)
    port = int(os.environ.get("PORT", 5000))

    app.run(host='0.0.0.0', port=port, debug=False)

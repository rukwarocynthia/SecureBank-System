import sqlite3
from werkzeug.security import generate_password_hash

def fix_passwords():
    # 1. Connect to your database
    conn = sqlite3.connect('bank.db') # Change this to your actual db filename
    cursor = conn.cursor()

    # 2. Fetch all users
    cursor.execute("SELECT id, password FROM Users")
    users = cursor.fetchall()

    for user_id, password in users:
        # 3. Check if the password is ALREADY hashed
        # Werkzeug hashes usually start with 'scrypt' or 'pbkdf2'
        if not (password.startswith('scrypt:') or password.startswith('pbkdf2:')):
            print(f"Hashing plain-text password for User ID: {user_id}")
            
            # 4. Hash the plain text
            hashed_pw = generate_password_hash(password)
            
            # 5. Update the database
            cursor.execute("UPDATE Users SET password = ? WHERE id = ?", (hashed_pw, user_id))

    conn.commit()
    conn.close()
    print("✅ All passwords have been successfully hashed!")

if __name__ == "__main__":
    fix_passwords()
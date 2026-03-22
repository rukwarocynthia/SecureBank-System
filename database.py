import sqlite3

def create_tables():
    conn = sqlite3.connect('bank.db')
    cursor = conn.cursor()

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            is_admin INTEGER DEFAULT 0
        )
    ''')

    # Accounts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            account_type TEXT NOT NULL,
            balance REAL DEFAULT 0,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (user_id) REFERENCES Users(id)
        )
    ''')

    # Transactions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            transaction_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES Accounts(id)
        )
    ''')

    conn.commit()
    conn.close()
    print("Tables created successfully.")


if __name__ == "__main__":
    create_tables()
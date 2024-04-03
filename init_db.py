import os
import psycopg2

def create_tables(conn):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            dateposted TEXT NOT NULL,
            seller TEXT NOT NULL
        );
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            sender TEXT NOT NULL,
            receiver TEXT NOT NULL,
            message TEXT NOT NULL,
            datesent TEXT NOT NULL
        );
    """)
    conn.commit()

if __name__ == '__main__':
    DATABASE_URL = "postgres://ub5bhk45itrk7h:p5eb1310f940313c18443a5534e5c2534b2cd75df260e142c542ada59d762cd5f@c7gljno857ucsl.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/d4166am3efc5qc"
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    create_tables(conn)
    conn.close()

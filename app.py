from flask import Flask, request, jsonify
import boto3
import random
import string
import time
import pymysql
import os
from datetime import datetime

app = Flask(__name__)

# DynamoDB Setup
dynamodb = boto3.resource('dynamodb', region_name="eu-north-1")
table_name = os.getenv("DYNAMODB_TABLE", "guacamole_users")
table = dynamodb.Table(table_name)

# MySQL Guacamole Setup
DB_HOST = os.getenv("MYSQL_HOST")
DB_USER = os.getenv("MYSQL_USER")
DB_PASS = os.getenv("MYSQL_PASS")
DB_NAME = os.getenv("MYSQL_DB", "guacamole_db")

def generate_password(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def insert_user_mysql(username, password):
    conn = pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASS, database=DB_NAME
    )
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO guacamole_user (username, password_hash, password_salt, password_date, disabled, expired)
        VALUES (%s, UNHEX(SHA2(%s, 256)), '', NOW(), 0, 0)
    """, (username, password))

    conn.commit()
    cursor.close()
    conn.close()

def store_user_dynamodb(username, password):
    timestamp = int(time.time())
    table.put_item(Item={
        'username': username,
        'password': password,
        'created_at': timestamp
    })

@app.route("/create-user", methods=["POST"])
def create_user():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"error": "Missing email"}), 400

    username = email.replace("@", "_").replace(".", "_")
    password = generate_password()

    try:
        insert_user_mysql(username, password)
        store_user_dynamodb(username, password)
        return jsonify({
            "username": username,
            "created": True
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run()

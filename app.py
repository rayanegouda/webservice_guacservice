from flask import Flask, request, jsonify
import boto3
import random
import string
import time
import pymysql
import os
import json
from datetime import datetime
from botocore.config import Config

app = Flask(__name__)

aws_config = Config(
    max_pool_connections=100,
    retries={'max_attempts': 3}
)


# DynamoDB Setup
dynamodb = boto3.resource('dynamodb', region_name="eu-north-1")
table_name = os.getenv("DYNAMODB_TABLE", "guacamole_users")
table = dynamodb.Table(table_name)



def generate_password(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

aws_config = Config(
    max_pool_connections=100,
    retries={'max_attempts': 3}
)


def get_secret_value(secret_id: str):
    region_name = os.environ.get("AWS_REGION_NAME")
    if not region_name:
        raise RuntimeError("Missing AWS_REGION_NAME environment variable")

    client = boto3.client(
        "secretsmanager",
        config=aws_config,
        region_name=region_name,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )
    response = client.get_secret_value(SecretId=secret_id)
    return json.loads(response["SecretString"])


def get_db_credentials():
    secret_ids = {
        "host": "rds-db-credentials/cluster-3MGGV2VUZDWQSJFDD6TQ4744HQ/admin/1748251685700",
        "username": "rds!cluster-27e3f900-f4c4-44bc-a1e0-19cc44356684",
        "password": "rds!cluster-27e3f900-f4c4-44bc-a1e0-19cc44356684",
    }

    return {
        "host": get_secret_value(secret_ids["host"])["host"],
        "port": 3306,
        "user": get_secret_value(secret_ids["username"])["username"],
        "password": get_secret_value(secret_ids["password"])["password"],
        "dbname": "guacamole_db"
    }

creds = get_db_credentials()

# MySQL Guacamole Setup
DB_HOST = creds['host']
DB_USER = creds['user']
DB_PASS = creds['password']
DB_NAME = creds['dbname']

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

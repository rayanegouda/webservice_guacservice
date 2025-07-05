from flask import Flask, request, jsonify
import boto3
import random
import time
import pymysql
import os
import json
from datetime import datetime
from botocore.config import Config
import random
import string
import pymysql
import logging
import hashlib

# Configuration
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

aws_config = Config(
	max_pool_connections=100,
	retries={'max_attempts': 3}
)

# DynamoDB Setup
dynamodb = boto3.resource('dynamodb', region_name="eu-north-1")
table_name = os.getenv("DYNAMODB_TABLE", "guacamole_users")
table = dynamodb.Table(table_name)


def generate_random_username(base: str, length: int = 6):
	suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
	return f"{base}_{suffix}"


def delete_dynamo_users_with_prefix(table, prefix):
	scan = table.scan()
	for item in scan.get("Items", []):
		if item["username"].startswith(f"{prefix}_"):
			table.delete_item(Key={"username": item["username"]})


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

def delete_users_with_prefix(prefix):
    try:
        conn = pymysql.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASS, database=DB_NAME
        )
        cursor = conn.cursor()

        logging.info(f"🔍 Recherche des users avec prefix : {prefix}_%")

        # Étape 1 : récupérer les entity_id associés
        cursor.execute("""
            SELECT entity_id FROM guacamole_entity
            WHERE name LIKE %s
        """, (f"{prefix}_%",))
        entity_ids = cursor.fetchall()

        logging.info(f"🧹 Utilisateurs trouvés à supprimer : {len(entity_ids)}")

        # Étape 2 : suppression
        for (eid,) in entity_ids:
            cursor.execute("DELETE FROM guacamole_user WHERE entity_id = %s", (eid,))
            cursor.execute("DELETE FROM guacamole_entity WHERE entity_id = %s", (eid,))
            logging.info(f"✅ Supprimé entity_id : {eid}")

        conn.commit()

    except Exception as e:
        logging.error(f"❌ Erreur lors de la suppression des utilisateurs : {str(e)}")
    finally:
        cursor.close()
        conn.close()

def insert_user_mysql(username, password):
	conn = pymysql.connect(
		host=DB_HOST, user=DB_USER, password=DB_PASS, database=DB_NAME
	)
	cursor = conn.cursor()

	# Étape 1 : insérer dans guacamole_entity
	cursor.execute("INSERT INTO guacamole_entity (name, type) VALUES (%s, 'USER')", (username,))

	# Étape 2 : récupérer l'entity_id
	cursor.execute("SELECT entity_id FROM guacamole_entity WHERE name = %s", (username,))
	entity_id = cursor.fetchone()[0]

	# Étape 3 : insérer dans guacamole_user
	cursor.execute("""
	    INSERT INTO guacamole_user (entity_id, password_hash, password_salt, password_date, disabled, expired)
	    VALUES (%s, UNHEX(SHA2(%s, 256)), NULL, NOW(), 0, 0)
	""", (entity_id, password))

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
	username_prefix = username  # ou récupéré dynamiquement
	username = generate_random_username(username_prefix)

	try:
		# Supprimer anciens comptes MySQL
		delete_users_with_prefix(username_prefix)
		# Supprimer anciens comptes DynamoDB
		delete_dynamo_users_with_prefix(table, username_prefix)
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

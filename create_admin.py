import bcrypt

username = "admin"
password = "1234"
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

print("請把下面 SQL 貼到 MySQL 執行：")
print(f"INSERT INTO admin_users (username, password) VALUES ('{username}', '{hashed}');")

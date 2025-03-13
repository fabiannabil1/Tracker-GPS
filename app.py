import psycopg2
from flask import Flask, render_template, jsonify
from flask import Flask, render_template, jsonify, request, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash
import paho.mqtt.client as mqtt
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = '@Pi3,1415926'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username


DB_CONFIG = {
    'dbname': '',
    'user': '',
    'password': '',
    'host': '',
    'port': 
}

DB_CONFIG_POSTGIS = {
    'dbname': '',
    'user': '',
    'password': '',
    'host': '',
    'port': 
}

# Konfigurasi MQTT
MQTT_BROKER = ""
MQTT_PORT = 1883
MQTT_USER = ""
MQTT_PASSWORD = ""
MQTT_TOPIC = ""

@app.route('/add_to_postgis', methods=['POST'])
@login_required
def add_gps():
    conn = psycopg2.connect(**DB_CONFIG_POSTGIS)
    cursor = conn.cursor()
    data = request.json
    device_id = data['device_id']
    coordinates = data['coordinates']  # Expecting a list of [lon, lat] pairs

    if not coordinates:
        return {"message": "No coordinates provided"}, 400

    linestring = ", ".join([f"{lon} {lat}" for lon, lat in coordinates])
    query = """
        INSERT INTO gps_tracks (device_id, geom)
        VALUES (%s, ST_GeomFromText(%s, 4326))
    """
    linestring_wkt = f"LINESTRING({linestring})"
    
    cursor.execute(query, (device_id, linestring_wkt))
    conn.commit()

    cursor.close()
    conn.close()

    return {"message": "GPS LineString added"}, 200


@login_required
def read_gps_data():
    data = []
    try:
        # Koneksi ke database PostgreSQL
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Query untuk mengambil semua data dari tabel gps_data
        cursor.execute("""
            SELECT waktu_gps, longitude, latitude, altitude, speed, satellite, server_time, date, bat_status
            FROM gps_data
        """)
        
        # Ambil semua data
        rows = cursor.fetchall()

        # Jika tidak ada data
        if not rows:
            return []  # Mengembalikan list kosong jika tidak ada data

        for row in rows:
            waktu_gps, longitude, latitude, altitude, speed, satellite, server_time, date ,bat_status= row
            data.append({
                'waktu_gps': waktu_gps,  # Gunakan waktu_gps
                'longitude': longitude,
                'latitude': latitude,
                'altitude': altitude,
                'speed': speed,
                'satellite': satellite,
                'server_time': server_time,
                'date': date,
                'bat_status' : bat_status
            })

        # Menutup koneksi database
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")
    return data

@login_manager.user_loader
def load_user(user_id):
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username FROM users WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    cursor.close()
    conn.close()
    if user_data:
        return User(id=user_data[0], username=user_data[1])
    return None

def get_user_by_username(username):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password FROM users WHERE username = %s", (username,))
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        return user_data
    except Exception as e:
        print(f"Error: {e}")
        return None


# Routes untuk login dan logout
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user_data = get_user_by_username(username)
        if user_data and check_password_hash(user_data[2], password):
            user = User(id=user_data[0], username=user_data[1])
            login_user(user)
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# Modifikasi route utama untuk menggunakan dashboard
@app.route('/')
@login_required
def dashboard():
    return render_template('index.html')

# app.py (perubahan pada route /data)
@app.route('/data')
@login_required
def get_data():
    gps_data = read_gps_data()
    
    # Ubah struktur data untuk match dengan frontend
    formatted_data = []
    for data in gps_data:
        formatted_data.append({
            'time': data['waktu_gps'].strftime("%Y-%m-%d %H:%M:%S"),
            'lat': data['latitude'],
            'lng': data['longitude'],
            'altitude': data['altitude'],
            'speed': data['speed'],
            'satellite': data['satellite'],
            'server_time': data['server_time'].strftime("%Y-%m-%d %H:%M:%S"),
            'date': data['date'].strftime("%Y-%m-%d"),
            'bat_status' : data['bat_status']
        })
    
    return jsonify(formatted_data)

# Fungsi untuk menyimpan data GPS ke dalam database
def save_gps_data(gps_data):
    try:
        # Koneksi ke database PostgreSQL
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Mendapatkan waktu server
        server_time = datetime.now()

        # Jika waktu GPS ada di payload, konversi waktu menjadi format yang cocok
        try:
            # Format Waktu GPS dari payload yang diterima dari MQTT
            gps_date = gps_data['date']
            gps_time = gps_data['waktu_gps']

            # Gabungkan tanggal dan waktu
            gps_datetime_str = f"{gps_date} {gps_time}"

            # Konversi ke objek datetime
            gps_datetime = datetime.strptime(gps_datetime_str, "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            gps_datetime = server_time  # Gunakan waktu server jika ada masalah dengan format

        # Query untuk memasukkan data ke dalam tabel gps_data
        cursor.execute(""" 
            INSERT INTO gps_data (waktu_gps, longitude, latitude, altitude, speed, satellite, server_time, date, bat_status) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) 
        """,( 
            gps_datetime,  # Gunakan waktu GPS (atau waktu server jika tidak ada) 
            gps_data['longitude'],  # Menggunakan longitude yang benar 
            gps_data['latitude'],  # Menggunakan latitude yang benar 
            gps_data['altitude'],  
            gps_data['speed'],  
            gps_data['satellite'],  
            server_time,  # Waktu server untuk menandai kapan data diterima 
            server_time.date(),  # Tanggal server untuk penyimpanan 
            gps_data['bat']  # Kunci bat harus dalam tanda kurung siku dan kutip
        ))

        # Commit perubahan dan menutup koneksi
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")



# Fungsi untuk menangani pesan yang diterima dari MQTT
def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        gps_data = json.loads(payload)

        # Simpan data GPS ke database
        save_gps_data(gps_data)
        print(f"Data GPS diterima: {gps_data}")
    except Exception as e:
        print(f"Error receiving message: {e}")

# Fungsi untuk mengonfigurasi MQTT client dan koneksi
def start_mqtt():
    client = mqtt.Client()

    # Mengatur username dan password untuk autentikasi
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)

    # Menetapkan callback untuk pesan masuk
    client.on_message = on_message

    # Menghubungkan ke broker MQTT
    client.connect(MQTT_BROKER, MQTT_PORT, 60)

    # Berlangganan ke topik
    client.subscribe(MQTT_TOPIC)

    # Memulai loop untuk mendengarkan pesan
    client.loop_start()

# Mulai MQTT client
start_mqtt()

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)

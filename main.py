#!/usr/bin/env python3
import sqlite3
import threading
import time
import json
import random
import base64

from flask import Flask, render_template_string, render_template, jsonify
from paho.mqtt import client as mqtt_client

app = Flask(__name__)

# MQTT broker settings using a public test broker, also possible bokers like HiveMQ or CloudMQTT: 
broker = 'lorawan.newsroom.local'
port = 1883
topic = "#"
#topic = "v3/testapplication/"
#topic = "robodog/location"

#broker = 'test.mosquitto.org'
#port = 1883
#topic = "robodog/location"
client_id = f'python-mqtt-{random.randint(0, 1000)}'

auth = {
         'username':"application01",
        'password': ""
}

# Database Configuration
DB_NAME = 'gps_data.db'

def create_db_table():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS coordinates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            latitude REAL,
            longitude REAL
        )
    ''')
    cursor.execute('DELETE FROM coordinates')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            message VARCHAR(1000)
            )
        ''')
    cursor.execute('DELETE FROM messages')
    conn.commit()
    conn.close()

create_db_table()

#  MQTT Client and Message Handling 
def on_connect(client, userdata, flags, rc, properties=auth):
#def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("Connected to MQTT Broker!")
        client.subscribe(topic)
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    try:
        # Decode the payload 
        payload = msg.payload.decode()
        #print(f"Received message: '{payload}'")

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            print('JSONDecodeError while msg.payload.decode()')
            # If JSON decoding fails, assume it's a template string and render it.
            # The LoRa App always sends valid JSON data though.
            with app.app_context():
                rendered_payload = render_template_string(payload)
            data = {"latitude": "SSTI Vulnerability", "longitude": rendered_payload}

        # Process and store raw message for logging and debugging

        frm_payload = data['uplink_message']['frm_payload']
        b64d_payload = base64.b64decode(frm_payload)
        message_string = b64d_payload.decode()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (timestamp, message) VALUES (?,?)",
            (time.time(), message_string)
            )
        conn.commit()
        conn.close()
        
        # Process positioning data
        lat_part = int.from_bytes(bytearray(b64d_payload[:4]))
        lon_part = int.from_bytes(bytearray(b64d_payload[4:8]))
        
        # These checks and magic numbers are derived from the documentation
        # of the LoRaWAN GPS Tracker and how it encodes its data

        if not (lat_part & 0x80000000):
            latitude = lat_part / 1000000.0
            if abs(latitude) > 90:
                raise ValueError('Tracker sent bad latitude')

        else:
            raise ValueError('Tracker sent frame missing latitude')

        if (lon_part & 0x80000000):
            longitude = (lon_part - 0x100000000) / 1000000.0
            if abs(longitude) > 180:
                raise ValueError('Tracker sent bad longitude')

        else:
            raise ValueError('Tracker sent frame missing longitude')

        print('latitude: ', latitude)
        print('longitude: ', longitude)

        # Store data in the database
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO coordinates (timestamp, latitude, longitude) VALUES (?, ?, ?)",
            #(time.time(), data['latitude'], data['longitude'])
            (time.time(), latitude, longitude)
        )
        conn.commit()
        conn.close()

    except Exception as e:
        print(f"Error processing message: {e}")

def connect_mqtt():
    client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2, client_id,auth)
    client.username_pw_set(auth['username'],auth['password'])
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(broker, port)
    return client

# Mock Data Generation (Robot Simulator) 
def publish_mock_data(client):
    # arbitrary start coordinates
    lat = 48.2082
    lon = 16.3738

    #  linear movement vector 
    direction_lat = 0.0001
    direction_lon = 0.00015

    # Counter to change direction periodically
    direction_change_counter = 0

    while True:
        direction_change_counter += 1
        if direction_change_counter >= 10:
            # change direction randomly every 10 iterations
            direction_lat = random.uniform(-0.0002, 0.0002)
            direction_lon = random.uniform(-0.0002, 0.0002)
            direction_change_counter = 0 # Reset the counter

        # Apply linear movement
        lat += direction_lat
        lon += direction_lon

        # here one could also send malicious payload
        # payload = f"{{{{ 7*7 }}}}"
        payload = json.dumps({"latitude": lat, "longitude": lon, "timestamp": time.time()})

        result = client.publish(topic, payload)
        status = result[0]
        if status != 0:
            print(f"Failed to send message to topic {topic}")

        # Publish every 3 seconds
        time.sleep(3)

@app.route('/')
def index():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT latitude, longitude FROM coordinates ORDER BY timestamp DESC LIMIT 1")
    last_coords = cursor.fetchone()

    # Fetch raw message
    cursor.execute("SELECT message FROM messages ORDER BY timestamp DESC LIMIT 1")
    messages = cursor.fetchone()
    #try:
    #    t = templates[0]
    #    print('type(t): ', type(t))
    #except:
    #    return jsonify(data)

    conn.close()

    if last_coords:
        current_lat = last_coords[0]
        current_lon = last_coords[1]
    else:
        current_lat = "No data yet"
        current_lon = "No data yet"

    if messages:
        current_msg =  messages[0]
    else:
        current_msg = "No data yet"


    #############################
    # SSTI vulnerability        #
    debug_kernel_str = '{{ os.popen("uname -a").read() }}'
    msg = '''
    Raw message: {} 
    Debug: {}
    '''.format(current_msg, debug_kernel_str)
    current_msg = render_template_string(msg,os=os)
    #############################

    return render_template("robodog.html", current_lat=current_lat, current_lon=current_lon, current_msg=current_msg)

@app.route('/data')
def get_data():
    """Endpoint for fetching the last 100 coordinates as JSON."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    #cursor.execute("SELECT latitude, longitude FROM coordinates ORDER BY timestamp ASC LIMIT 100")
    cursor.execute("SELECT message, timestamp FROM messages ORDER BY timestamp DESC LIMIT 100")
    #messages = cursor.fetchone()
    data = [{"message": row[0], "timestamp": row[1]} for row in cursor.fetchall()]
    conn.close()
    return jsonify(data)

@app.route('/camera')
def camera_feed():
    """Mock endpoint to serve a video feed."""
    # placeholder 
    return '<h1>Mock Camera Feed</h1><p>Placeholder for the live video stream.</p>'

# --- Main Execution ---
if __name__ == '__main__':

    # Set up the MQTT client and connect
    mqtt_client = connect_mqtt()
    mqtt_client.loop_start()

    # Start the mock data publishing thread
    #mock_thread = threading.Thread(target=publish_mock_data, args=(mqtt_client,))
    #mock_thread.daemon = True
    #mock_thread.start()
    
    # Run the Flask web server
    app.run(host='0.0.0.0', debug=True, use_reloader=False)

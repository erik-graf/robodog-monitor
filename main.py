#!/usr/bin/env python3

import os
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

#topic = "#"
sub_topic = 'v3/application01/devices/tracker01/up'
push_topic = 'v3/application01/devices/tracker01/down/push'
#topic = "v3/testapplication/"
#topic = "robodog/location"

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
        client.subscribe(sub_topic)
    else:
        print(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    try:
        # Decode the payload 
        #print("MQTT message topic", msg.topic)
        payload = msg.payload
        decoded = payload.decode()
        print(f"Received payload: '{payload}'")
        print(f"Received payload.hex(): '{payload.hex()}'")
        print(f"Received payload decoded: '{decoded}'")
        payload = decoded

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

        try:
            frm_payload = data['uplink_message']['frm_payload']
            b64d_payload = base64.b64decode(frm_payload)
            #message_string = b64d_payload.decode()
            message_string = b64d_payload
            print('b64d_payload: ', b64d_payload)

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
        except KeyError:
            print("Key Error while trying to decode MQTT data. Data not in json format/from GPS tracker?")
            # Mock data format
            latitude = data['latitude']
            longitude = data['longitude']

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
def publish_mock_data(client, fake=False):
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
        if fake:
            # Store data in the database
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
            "INSERT INTO coordinates (timestamp, latitude, longitude) VALUES (?, ?, ?)",
            #(time.time(), data['latitude'], data['longitude'])
            (time.time(), lat, lon)
            )
            conn.commit()
            conn.close()

        else:
            result = client.publish(push_topic, payload)
            status = result[0]
            if status != 0:
                print(f"Failed to send message to topic {topic}")

        # Publish every 3 seconds
        time.sleep(3)

# Structured lap data for rectangle patrol with periodic deviation
def publish_dog_lap_data(client, fake=False):
    # Rectangle corners: SW → NW → NE → SE (SW is the starting point)
    sw = (48.2075, 16.3728)
    nw = (48.2112, 16.3728)
    ne = (48.2112, 16.3778)
    se = (48.2075, 16.3778)
    rect = [sw, nw, ne, se]

    # Camera 5 - deviation point outside the rectangle (west side)
    deviation_point = (48.2094, 16.3715)

    def walk(start, end, steps):
        """Yield `steps` evenly spaced points from start to end (exclusive of start, inclusive of end)."""
        for i in range(1, steps + 1):
            lat = start[0] + (end[0] - start[0]) * i / steps
            lon = start[1] + (end[1] - start[1]) * i / steps
            yield (lat, lon)

    def publish_point(point):
        payload = json.dumps({"latitude": point[0], "longitude": point[1], "timestamp": time.time()})
        if fake:
            # Store data in the database
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
            "INSERT INTO coordinates (timestamp, latitude, longitude) VALUES (?, ?, ?)",
            #(time.time(), data['latitude'], data['longitude'])
            (time.time(), point[0], point[1])
                          )
            conn.commit()
            conn.close()
  
        else:
            result = client.publish(push_topic, payload)
            if result[0] != 0:
                print(f"Failed to send message to topic {topic}")
        time.sleep(1)

    lap = 0
    while True:
        lap += 1

        if lap % 3 == 0:
            # Deviation lap: 1→5→2, then continue normally 2→3→4→1
            for point in walk(sw, deviation_point, 8):
                publish_point(point)
            for point in walk(deviation_point, nw, 8):
                publish_point(point)
            for point in walk(nw, ne, 16):
                publish_point(point)
            for point in walk(ne, se, 8):
                publish_point(point)
            for point in walk(se, sw, 16):
                publish_point(point)
        else:
            # Normal lap: 1→2→3→4→1
            # SW→NW and NE→SE are the short NS sides (8 steps)
            # NW→NE and SE→SW are the long EW sides (16 steps)
            for point in walk(sw, nw, 8):
                publish_point(point)
            for point in walk(nw, ne, 16):
                publish_point(point)
            for point in walk(ne, se, 8):
                publish_point(point)
            for point in walk(se, sw, 16):
                publish_point(point)

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
    cursor.execute("SELECT latitude, longitude FROM coordinates ORDER BY timestamp DESC LIMIT 10")
    # cursor.execute("SELECT message, timestamp FROM messages ORDER BY timestamp DESC LIMIT 100")
    # data = [{"message": row[0], "timestamp": row[1]} for row in cursor.fetchall()]
    rows = cursor.fetchall()
    rows.reverse()

    data = [{"latitude": row[0], "longitude": row[1]} for row in rows]
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
    #mqtt_client = connect_mqtt()
    #mqtt_client.loop_start()

    mqtt_client = []

    # Start the lap data publishing thread
    # if fake is True: don't publish to MQTT, but write directly into the SQL db
    fake = True
    mock_thread = threading.Thread(target=publish_dog_lap_data, args=(mqtt_client,fake))
    mock_thread.daemon = True
    mock_thread.start()

    
    # Run the Flask web server
    app.run(host='0.0.0.0', debug=True, use_reloader=False)

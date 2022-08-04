import time
import json
import os
from os.path import join, dirname
from datetime import datetime, timedelta
from dotenv import load_dotenv
from gpiozero import CPUTemperature
import paho.mqtt.client as mqtt
import bme280_sensor
import ds18b20_therm

dotenv_path = join(dirname(__file__), '.env')
load_dotenv(dotenv_path)

# Load .env variables
MQTT_USER = os.environ.get('MQTT_USER')
MQTT_PASSWORD = os.environ.get('MQTT_PASSWORD')
MQTT_HOST = os.environ.get('MQTT_HOST')
MQTT_PORT = int(os.environ.get('MQTT_PORT'))

# Global variable definition
flag_connected = 0      # Loop flag for waiting to connect to MQTT broker

# Constant variable definition
MQTT_STATUS_TOPIC = os.environ.get('MQQT_STATUS_TOPIC', "raspberry/ws/status")
MQTT_SENSORS_TOPIC = os.environ.get('MQTT_SENSORS_TOPIC', "raspberry/ws/sensors")
READ_INTERVAL = int(os.environ.get('READ_INTERVAL', 5))

# Initialize ground temp probe
temp_probe = ds18b20_therm.DS18B20()

# Define variables
interval = timedelta(seconds=READ_INTERVAL)  # Data collection interval in secs. 5 mins = 5 * 60 = 300


# MQTT
def on_connect(client, userdata, flags, rc) -> None:
    print("Connected with flags [%s] rtn code [%d]" % (flags, rc))
    global flag_connected
    flag_connected = 1


def on_disconnect(client, userdata, rc) -> None:
    print("disconnected with rtn code [%d]" % (rc))
    global flag_connected
    flag_connected = 0


print(f"Attemping MQTT: {MQTT_USER} @ {MQTT_HOST}:{MQTT_PORT}")
client = mqtt.Client("WX")
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
client.connect(MQTT_HOST, MQTT_PORT)


# System Uptime
def uptime() -> str:
    t = os.popen('uptime -p').read()[:-1]
    uptime = t.replace('up ', '')
    return uptime


# Convert C to F
def celsius_to_f(temp_c: float) -> float:
    f = (temp_c * 9/5.0) + 32
    return f


# Read CPU temp for future fan logic
cpu = CPUTemperature()

# Main loop
if __name__ == '__main__':
    client.loop_start()

    # Wait to receive the connected callback for MQTT
    while flag_connected == 0:
        print("Not connected. Waiting 1 second.")
        time.sleep(1)

    while True:
        # Record current date and time for message timestamp
        loop_start = datetime.now()

        outside_temp = temp_probe.read_temp()
        humidity, pressure, garage_temp = bme280_sensor.read_all()

        # Round wind_direction, humidity, pressure, ambient_temp, outside_temp, and rainfall to 1 decimals
        # and convert C readings to F
        humidity = round(humidity, 1)
        pressure = round(pressure, 1)
        garage_temp_f = round(celsius_to_f(garage_temp), 1)
        outside_temp_f = round(celsius_to_f(outside_temp), 1)

        cpu_temp = celsius_to_f(round(cpu.temperature, 1))

        # Format message timestamp to mm/dd/YY H:M:S
        last_message = loop_start.strftime("%m/%d/%Y %H:%M:%S")

        # Get current system uptime
        sys_uptime = uptime()

        # Create JSON dict for MQTT transmission
        send_msg = {
            'garage_humidity': humidity,
            'pressure': pressure,
            'garage_temp': garage_temp_f,
            'outside_temp': outside_temp_f,
            'last_message': last_message,
            'cpu_temp': cpu_temp,
            'system_uptime': sys_uptime
        }

        print(f"Got message: {send_msg}")
        # Convert message to json
        payload_sensors = json.dumps(send_msg)

        try:
            client.publish(MQTT_STATUS_TOPIC, "Online", qos=0)
            # Publish sensor data to mqtt
            client.publish(MQTT_SENSORS_TOPIC, payload_sensors, qos=0)
        except Exception as e:
            print(f"Error publishing to MQTT: {e}")

        after_write = datetime.now()
        to_sleep = (interval - (after_write - loop_start)).total_seconds()
        if to_sleep > 0:
            time.sleep(to_sleep)

    client.loop_stop()
    print("Loop Stopped.")
    client.disconnect()
    print("MQTT Disconnected.")

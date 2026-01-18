import sys
import uuid
import re
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
from time import sleep
import logging
import datetime
import argparse

from pathlib import Path
# 1. Enable Python Logging
# logging.basicConfig(level=logging.DEBUG) 

def on_log(client, userdata, level, buf):
    print(f"📋 LOG: {datetime.datetime.now()} , {buf}")


# --- CONFIGURATION ---

argparser = argparse.ArgumentParser(description="MQTT WebSocket Client")
argparser.add_argument("--broker", type=str, default="localhost", help="MQTT Broker Host")
argparser.add_argument("--port", type=int, default=8000, help="MQTT Broker Port")
argparser.add_argument("--lts", action="store_true", help="Use LTS (TLS) Connection")
argparser.add_argument("--rate", type=float, default=0.00001, help="Publish Rate (seconds)")
argparser.add_argument("--path", type=str, default="/mqtt_opt", help="WebSocket Path")

# load from cf.log
argparser.add_argument("--cf", action="store_true", help="Use Cloudflare Public Broker")
args = argparser.parse_args()
print(f"🚀 Starting MQTT WebSocket Client with args: {args}")

MQTT_WS_PATH = args.path

BROKER_HOST = args.broker
BROKER_PORT = args.port
BROKER_LTS = args.lts
if args.cf:
    cf_log_file = Path(__file__).parent.parent /"cf.log"
    if cf_log_file.exists():
        print("🌐 Detected Cloudflare Environment - Using Public Broker")
        with open(cf_log_file, "r") as f:
            pattern = r"[a-z\-]+\.trycloudflare.com"
            all_matches = re.findall(pattern, f.read())
            BROKER_HOST = all_matches[-1]
            print(f"🌍 Cloudflare Hostname: {BROKER_HOST}")
        BROKER_PORT = 443
        BROKER_LTS = True

MESSAGE_LOG_COUNT = 10000
PUBLISH_RATE=args.rate  # seconds

# Optional: Enable Paho Logging to see handshake errors
# logging.basicConfig(level=logging.DEBUG)
# 1. Disable logging to console for every message (Printing is slow!)
def on_message(client, userdata, msg):
    # Only print every 100th message to save CPU
    if int(msg.payload.decode().split()[-1]) % MESSAGE_LOG_COUNT == 0:
        print(f"📩 Recieve [{msg.topic}]: {msg.payload.decode()}")

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"✅ Connected to Broker! (RC: {reason_code})")
        client.subscribe("iot") 
    else:
        print(f"❌ Failed to connect (RC: {reason_code})")

def on_disconnect(client, userdata, flags, reason_code, properties):
    print(f"⚠️ Disconnected (RC: {reason_code}).")

# def on_message(client, userdata, msg):
#     print(f"📩 Recieve [{msg.topic}]: {msg.payload.decode()}")


def main():
    # Generate ID
    client_id = f"py-ws-{uuid.uuid4().hex[:4]}"
    
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=client_id,
        transport="websockets",
        protocol=mqtt.MQTTv311,
    )
    if BROKER_LTS:
        client.tls_set()  # Enable TLS for secure connection

    client.ws_set_options(path=MQTT_WS_PATH, headers={"Sec-WebSocket-Protocol": "mqtt"})
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect


    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.reconnect_delay_set(min_delay=1, max_delay=5)
    client.loop_start()
    # client.loop_forever(retry_first_connection=True)

    counter = 0
    try:
        while True:
            if client.is_connected():
                counter += 1
                msg = f"Data {counter}"
                client.publish("iot", msg)
                
                if counter % MESSAGE_LOG_COUNT == 0:
                    print(f"→ Sent {counter} messages...")
            
            # 0.01 is fast, but the optimized broker can now handle it.
            sleep(PUBLISH_RATE) 

    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
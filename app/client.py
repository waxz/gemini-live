import uuid
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
from time import sleep
import logging
import datetime

# 1. Enable Python Logging
# logging.basicConfig(level=logging.DEBUG) 

def on_log(client, userdata, level, buf):
    print(f"📋 LOG: {datetime.datetime.now()} , {buf}")


# --- CONFIGURATION ---
BROKER_HOST = "localhost"
BROKER_PORT = 8000
MQTT_WS_PATH = "/mqtt_opt"
BROKER_LTS = False

# BROKER_HOST ="jungle-beneath-noticed-matching.trycloudflare.com"
# BROKER_PORT = 443
# BROKER_LTS = True


MESSAGE_LOG_COUNT = 10000
PUBLISH_RATE=0.00001

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
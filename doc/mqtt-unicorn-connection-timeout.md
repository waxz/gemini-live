Here is a comprehensive technical article summarizing our debugging session. It covers the architecture, the investigation process using `tcpdump`, the root causes identified, and the final high-performance solution.

---

# Tuning High-Throughput WebSocket MQTT Proxies: A Debugging Case Study

## 1. Introduction & Architecture
In modern IoT architectures, it is common to proxy MQTT traffic over WebSockets (port 80/443) to bypass firewall restrictions before forwarding it to an internal TCP Broker (port 1883).

**The Stack:**
*   **Client:** Python Paho MQTT (Transport: WebSockets).
*   **Proxy:** FastAPI + Uvicorn + asyncio (Bridging WS <-> TCP).
*   **Broker:** Internal Mosquitto/IoT Core (TCP).

**The Problem:**
We encountered a scenario where the client would connect successfully but disconnect exactly every 20 seconds, or fail to reconnect immediately after a disconnect ("Zombie Connections"), or choke under high-frequency publishing (100 messages/sec).

---

## 2. Investigation Tools & Methodology

To diagnose "black box" connection drops, relying on application logs is often insufficient. We utilized `tcpdump` to inspect the packet flags at the OS level.

### The "Connection Killer" Command
This command filters traffic on the loopback interface, showing only connection establishment (SYN), termination (FIN), and crashes (RST).

```bash
# Linux/macOS
sudo tcpdump -i lo -n -tttt "port 1883 and (tcp[tcpflags] & (tcp-syn|tcp-fin|tcp-rst) != 0)"
```

### Key Findings form Logs
1.  **The "20-Second" Drop:**
    *   *Log:* `Flags [F.]` (FIN) sent from Proxy to Broker exactly 20.0s after connection start.
    *   *Meaning:* The disconnect was intentional (Clean Close), not a crash. Uvicorn's default WebSocket heartbeat was timing out because the high traffic volume delayed "Pong" responses.
2.  **The "Zombie" Rejection:**
    *   *Log:* `Flags [F.]` sent by Broker to *Old Port* immediately after `Flags [S]` (SYN) received from *New Port*.
    *   *Meaning:* The Client reconnected faster than the Proxy closed the old socket. The Broker detected a Duplicate Client ID and kicked the old connection, causing instability.

---

## 3. Root Causes & Technical Solutions

### Issue A: The "Stop-and-Wait" Bottleneck
**Symptoms:** High latency, buffer overflows, eventual disconnects under load.
**Cause:** Calling `await writer.drain()` after every single packet write pauses the event loop, waiting for the OS to flush the buffer.
**Solution:** **Smart Batching.**
*   Buffer data in memory.
*   Only `drain()` when the buffer exceeds a threshold (e.g., 64KB) *OR* when the packet is very small (latency-critical MQTT ACKs).

### Issue B: Protocol Conflict (Uvicorn vs. MQTT)
**Symptoms:** Disconnects every ~20 seconds.
**Cause:** Uvicorn sends WebSocket Pings. Paho sends MQTT Pings. When the pipe is full of data, Uvicorn's Pings get queued. If the client doesn't answer the WebSocket Ping in time, Uvicorn kills the connection.
**Solution:** **Disable Uvicorn Pings.**
Since MQTT handles its own application-layer Keepalive, the Transport-layer (WebSocket) Keepalive is redundant and harmful.

### Issue C: Zombie Connections
**Symptoms:** `Connection Refused` or Broker logs showing "Client ID already connected".
**Cause:** The Proxy's `finally` block was too slow to close the TCP socket.
**Solution:** **Aggressive Cancellation.**
Use `asyncio.wait(return_when=FIRST_COMPLETED)`. If the WebSocket drops, cancel the TCP task and forcefully close the socket immediately.

---

## 4. Final Implementation

### 4.1. The Optimized Proxy (`run_broker.py`)

This script runs the FastAPI app programmatically to explicitly disable WebSocket heartbeats (`None`) and enables `uvloop` for C-level performance.

```python
# run_broker.py
import uvicorn
import asyncio

# 1. Performance: Use uvloop (C-based event loop)
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("🚀 uvloop enabled")
except ImportError:
    print("⚠️ uvloop not installed (pip install uvloop)")

if __name__ == "__main__":
    # 2. Config: Disable WS Pings to prevent timeouts under load
    uvicorn.run(
        "broker_app:app",
        host="127.0.0.1",
        port=8000,
        ws_ping_interval=None,  # Critical for high throughput
        ws_ping_timeout=None,
        log_level="info"
    )
```

### 4.2. The Broker Logic (`broker_app.py`)

```python
# broker_app.py
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager

# Configuration
BROKER_HOST = '127.0.0.1'
BROKER_PORT = 1883
BUFFER_SIZE = 65536     # Read Buffer
FLUSH_THRESHOLD = 131072 # Write Buffer (128KB)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # (Optional) Start Internal Broker logic here
    yield

app = FastAPI(lifespan=lifespan)

async def ws_to_tcp(ws: WebSocket, writer: asyncio.StreamWriter):
    """
    Optimized Forwarder: 
    - Batches large writes for Bandwidth.
    - Flushes small writes (<100b) for Latency (ACKs/PINGs).
    """
    pending_bytes = 0
    try:
        async for data in ws.iter_bytes():
            if data:
                writer.write(data)
                n = len(data)
                pending_bytes += n
                
                # Smart Flush Logic
                if pending_bytes > FLUSH_THRESHOLD or n < 100:
                    await writer.drain()
                    pending_bytes = 0
        
        if pending_bytes > 0:
            await writer.drain()
    except Exception:
        pass

async def tcp_to_ws(reader: asyncio.StreamReader, ws: WebSocket):
    """ Reads from TCP in large chunks """
    try:
        while True:
            data = await reader.read(BUFFER_SIZE)
            if not data: break
            await ws.send_bytes(data)
    except Exception:
        pass

@app.websocket("/mqtt")
async def mqtt_websocket_proxy(client_ws: WebSocket):
    try:
        reader, writer = await asyncio.open_connection(BROKER_HOST, BROKER_PORT)
    except Exception:
        await client_ws.close(code=1011)
        return

    await client_ws.accept(subprotocol="mqtt")

    # Bidirectional Pipeline
    task_ws = asyncio.create_task(ws_to_tcp(client_ws, writer))
    task_tcp = asyncio.create_task(tcp_to_ws(reader, client_ws))

    # 3. Stability: Wait for FIRST failure, then kill everything
    await asyncio.wait([task_ws, task_tcp], return_when=asyncio.FIRST_COMPLETED)

    # 4. Cleanup: Aggressive socket closure to prevent Zombies
    for task in [task_ws, task_tcp]:
        task.cancel()
    
    writer.close()
    try:
        await writer.wait_closed()
    except:
        pass
```

### 4.3. The High-Speed Client (`client.py`)

```python
# client.py
import uuid
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion
from time import sleep

BROKER_HOST = "localhost"
BROKER_PORT = 8000
MQTT_WS_PATH = "/mqtt"

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("✅ Connected")
        client.subscribe("iot") # Echo test

def main():
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=f"bench-{uuid.uuid4().hex[:4]}",
        transport="websockets",
        protocol=mqtt.MQTTv311,
    )
    client.ws_set_options(path=MQTT_WS_PATH, headers={"Sec-WebSocket-Protocol": "mqtt"})
    client.on_connect = on_connect
    
    # MQTT Application Keepalive
    client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
    client.loop_start()

    counter = 0
    try:
        while True:
            if client.is_connected():
                counter += 1
                # High Throughput: 100 msg/sec
                client.publish("iot", f"Payload {counter}") 
                if counter % 100 == 0:
                    print(f"→ Sent {counter}")
            sleep(0.01) 
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()

if __name__ == "__main__":
    main()
```

---

## 5. Deployment Instructions

### 1. Prerequisites
Install the required libraries, including `uvloop` for C++ level performance on the event loop.

```bash
pip install fastapi uvicorn[standard] uvloop paho-mqtt
```

### 2. Monitoring (Tcpdump)
Open a separate terminal to watch the "heartbeat" of the connection.

```bash
sudo tcpdump -i lo -n -tttt "port 1883 and (tcp[tcpflags] & (tcp-syn|tcp-fin|tcp-rst) != 0)"
```

### 3. Execution
Start the Broker Proxy first, then the Client.

```bash
# Terminal 1
python run_broker.py

# Terminal 2
python client.py
```

## 6. References
*   **MQTT over WebSockets:** Paho Client Documentation on Transport options.
*   **FastAPI/Starlette WebSockets:** Handling `WebSocketDisconnect` exceptions.
*   **Uvicorn Settings:** `ws_ping_interval` configuration for streaming applications.
*   **TCP Flow Control:** Understanding Nagle's Algorithm and the cost of `drain()`.

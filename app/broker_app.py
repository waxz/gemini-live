import asyncio
from datetime import datetime

# 1. IMPORT THE COMPILED CYTHON MODULE
try:
    from proxy_core import optimized_ws_to_tcp, optimized_tcp_to_ws
    print("🚀 Running with CYTHON optimizations")
except ImportError:
    print("⚠️ Cython module not found. Run 'python setup.py build_ext --inplace'")
    # Fallback to Python definitions if compilation failed
    async def optimized_ws_to_tcp(ws, writer): pass 
    async def optimized_tcp_to_ws(reader, ws): pass



from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager

# Assuming 'iotcore' is your custom library or wrapper around an MQTT broker
from iotcore import IotCore 

# --- CRITICAL: Install and use uvloop for high performance ---
# pip install uvloop
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("🚀 High-Performance uvloop enabled")
except ImportError:
    print("⚠️ uvloop not found. Falling back to standard asyncio (Slower)")




# --- MOCKING IotCore for the fix demonstration (Uncomment your import above) ---
# class IotCore:
#     def background_loop_forever(self): pass
#     def subscribe(self, topic, cb): pass
#     def publish(self, topic, payload): pass
#     def accept(self, topic):
#         def decorator(func): return func
#         return decorator
iot = IotCore()
# ---------------------------------------------------------------------------
import logging
logging.basicConfig(level=logging.DEBUG) # This will show Broker logs too

BROKER_PORT = 1883
BROKER_HOST = '127.0.0.1'
CHUNK_SIZE = 65536  # 64KB Read Buffer
BUFFER_SIZE = 65536
MESSAGE_LOG_COUNT = 10000
MESSAGE_COUNT=0
MESSAGE_START_TIME = None
def on_message(msg):
    # Only print every 100th message to save CPU
    COUNT = int(msg.split()[-1])
    global MESSAGE_COUNT, MESSAGE_START_TIME
    if MESSAGE_START_TIME is None:
        MESSAGE_START_TIME = datetime.now()
    MESSAGE_COUNT += 1

    if MESSAGE_COUNT % MESSAGE_LOG_COUNT == 0:
        print(f"📩 Recieve [{msg}]")
        elapsed = (datetime.now() - MESSAGE_START_TIME).total_seconds()
        
        mps = float(MESSAGE_COUNT) / float(elapsed) 
        print(f"📊 Processed {MESSAGE_COUNT} messages in {elapsed:.2f} sec,  {mps:.2f} m/sec") 
        
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting IoT Broker...")
    iot.background_loop_forever()
    
    # Quick connectivity check
    try:
        _, w = await asyncio.open_connection(BROKER_HOST, BROKER_PORT)
        w.close()
        await w.wait_closed()
        print("✅ Internal Broker UP")
    except:
        pass

    iot.subscribe("iot", on_message)
    yield
    print("🛑 Broker stopping...")


app = FastAPI(lifespan=lifespan)


async def ws_to_tcp(ws: WebSocket, writer: asyncio.StreamWriter):
    pending_bytes = 0
    # Increase buffer to 128KB to handle the flood better
    FLUSH_THRESHOLD = 131072 

    try:
        async for data in ws.iter_bytes():
            if data:
                writer.write(data)
                n = len(data)
                pending_bytes += n
                
                # LOGIC CHANGE:
                # If the packet is tiny (< 100 bytes), it is likely an MQTT ACK or PINGREQ.
                # Flush IMMEDIATELY to keep latency low.
                # If it is big (payload), buffer it to keep bandwidth high.
                if n < 100 or pending_bytes > FLUSH_THRESHOLD:
                    await writer.drain()
                    pending_bytes = 0
        
        if pending_bytes > 0:
            await writer.drain()

    except (WebSocketDisconnect, ConnectionResetError):
        pass 
    except Exception as e:
        print(f"⚠️ WS->TCP Error: {e}")

async def tcp_to_ws(reader: asyncio.StreamReader, ws: WebSocket):
    """
    Optimized Reader: Reads large chunks.
    """
    try:
        while True:
            data = await reader.read(BUFFER_SIZE)
            if not data:
                break # EOF from Broker
            await ws.send_bytes(data)
    except (RuntimeError, ConnectionResetError):
        pass # WS closed
    except Exception as e:
        print(f"⚠️ TCP->WS Error: {e}")


@app.websocket("/mqtt_opt")
async def mqtt_websocket_proxy_opt(client_ws: WebSocket):
    try:
        reader, writer = await asyncio.open_connection(BROKER_HOST, BROKER_PORT)
    except Exception:
        await client_ws.close(code=1011)
        return

    await client_ws.accept(subprotocol="mqtt")

    # 2. USE THE CYTHON FUNCTIONS
    task_ws = asyncio.create_task(optimized_ws_to_tcp(client_ws, writer))
    task_tcp = asyncio.create_task(optimized_tcp_to_ws(reader, client_ws))

    await asyncio.wait([task_ws, task_tcp], return_when=asyncio.FIRST_COMPLETED)

    for task in [task_ws, task_tcp]:
        task.cancel()
    
    writer.close()
    try:
        await writer.wait_closed()
    except:
        pass

@app.websocket("/mqtt")
async def mqtt_websocket_proxy(client_ws: WebSocket):
    # 1. Connect to Internal Broker
    try:
        reader, writer = await asyncio.open_connection(BROKER_HOST, BROKER_PORT)
    except Exception:
        await client_ws.close(code=1011)
        return

    # 2. Handshake
    await client_ws.accept(subprotocol="mqtt")

    # 3. Create Tasks
    task_ws_to_tcp = asyncio.create_task(ws_to_tcp(client_ws, writer))
    task_tcp_to_ws = asyncio.create_task(tcp_to_ws(reader, client_ws))

    # 4. CRITICAL: Wait for FIRST_COMPLETED
    # If WebSocket dies, we MUST kill the TCP task immediately.
    # If TCP dies, we MUST kill the WebSocket task immediately.
    done, pending = await asyncio.wait(
        [task_ws_to_tcp, task_tcp_to_ws],
        return_when=asyncio.FIRST_COMPLETED
    )

    # 5. AGGRESSIVE CLEANUP (Fixes the "Zombie" connection issue)
    for task in pending:
        task.cancel()
    
    # Close TCP socket immediately so Broker releases the Client ID
    writer.close()
    try:
        await writer.wait_closed()
    except:
        pass
    
    # print("🔌 Clean Disconnect")

# def main():
#     import uvicorn
#     # ws_ping_interval=None  -> Disables sending Pings (Prevents 20s disconnect)
#     # ws_ping_timeout=None   -> Disables waiting for Pongs (Prevents timeouts)
#     uvicorn.run(
#         "broker:app", 
#         host="127.0.0.1", 
#         port=8000, 
#         loop="uvloop",
#         ws_ping_interval=None, 
#         ws_ping_timeout=None,
#         log_level="info"
#     )

# if __name__ == "__main__":
#     main()
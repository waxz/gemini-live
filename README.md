# gemini-live

- https://github.com/GoogleCloudPlatform/generative-ai/blob/main/gemini/multimodal-live-api/intro_live_api_native_audio.ipynb
- https://github.com/GoogleCloudPlatform/generative-ai/blob/main/gemini/multimodal-live-api/intro_multimodal_live_api.ipynb
- https://www.emqx.com/en/blog/connect-to-mqtt-broker-with-websocket



## cloudflared tunnel

```bash
./cloudflared tunnel --url localhost:8000 --logfile ./cf.log

```

## frontend

```bash
cd web && npm i && npm run build
```

## backend

```bash
source .venv/bin/activate
uv pip install -r requirements.txt -U --reinstall --no-cache

python3 ./app/pyx/setup.py build_ext -b ./app/

# uvicorn app.main:app --reload --port 8000
python3 ./app/run_main.py
```

## mqtt broker

```bash
# uvicorn app.broker:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 60 --ws-ping-interval 20 --ws-ping-timeout 20
# uvicorn app.broker:app --host 127.0.0.1 --port 8000 --loop uvloop --ws-ping-interval 20
python3 ./app/run_broker.py

python3 ./app/client.py --cf
python3 ./app/client.py --cf
```

## cython test
```bash
python3 -c "import app.math; print(app.math.add(1,4))"
python3 -c "import app.math; import numpy as np; a = np.array([1.1],dtype=np.float32); b= np.array([2.3],dtype=np.float32); print(app.math.average_arrays_1(a,b))"
```

## tcpdump test
```bash
sudo tcpdump -i lo -n -tttt "port 1883 and (tcp[tcpflags] & (tcp-syn|tcp-fin|tcp-rst) != 0)"
```

Increase OS Buffers (Linux/Mac)
Your OS might be limiting the loopback throughput for fairness. Increase the allowed memory for TCP buffers.

```bash
# Increase max OS write buffer to 16MB
sudo sysctl -w net.core.wmem_max=16777216
sudo sysctl -w net.core.rmem_max=16777216
```
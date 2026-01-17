# gemini-live

https://github.com/GoogleCloudPlatform/generative-ai/blob/main/gemini/multimodal-live-api/intro_live_api_native_audio.ipynb
https://github.com/GoogleCloudPlatform/generative-ai/blob/main/gemini/multimodal-live-api/intro_multimodal_live_api.ipynb


```bash
source .venv/bin/activate
uv pip install -r requirements.txt -U --reinstall --no-cache

./cloudflared tunnel --url localhost:8000

cd web && npm i && npm run build && cd ..
uvicorn app.main:app --reload --port 8000
```


# broker
```bash
uvicorn app.broker:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 60 --ws-ping-interval 20 --ws-ping-timeout 20
uvicorn app.broker:app --host 127.0.0.1 --port 8000 --loop uvloop --ws-ping-interval 20
python3 ./app/run_broker.py
```


# tcpdump
```bash
sudo tcpdump -i lo -n -tttt "port 1883 and (tcp[tcpflags] & (tcp-syn|tcp-fin|tcp-rst) != 0)"
```

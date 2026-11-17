# Offline chat (llama3.2:3b)

Local chat page that talks only to Ollama on this PC.

The browser opens `http://127.0.0.1:8765`. That page is served from the `static` folder by `chat_server.py`. Each question is streamed to Llama 3.2 at `http://127.0.0.1:11434`. Nothing is sent to a cloud API, and there is no API key.

The installed model name is `llama3.2:latest`. That tag is the 3B model.

## Run

1. Start the Ollama app.
2. From this folder, run:

```powershell
python chat_server.py
```

3. Open http://127.0.0.1:8765 if the browser does not open on its own.
4. Type a question and press Send. Leave the terminal open. Press Ctrl+C to stop.

`python chat.py` starts the same server.

## Terminal chat

```powershell
python chat_server.py --cli
python chat_server.py --once "What is 2 + 2?"
```

## Files

- `chat_server.py` serves the page and proxies the stream to local Ollama.
- `static/index.html`, `static/style.css`, and `static/app.js` are the chat page.

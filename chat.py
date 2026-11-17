"""Start the offline chat. The server lives in chat_server.py."""

from chat_server import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(0)

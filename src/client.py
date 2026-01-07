import socket
import sys
import os
from dotenv import load_dotenv

# Load env just to get socket path if custom, though checking default is fine
load_dotenv()
SOCKET_PATH = os.getenv("SOCKET_PATH", "/tmp/notion_agent.sock")

def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <query>")
        sys.exit(1)
        
    query = sys.argv[1]
    
    if not os.path.exists(SOCKET_PATH):
        print("Error: Notion Agent daemon is not running (socket not found).")
        sys.exit(1)
        
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(SOCKET_PATH)
        
        client.sendall(query.encode("utf-8"))
        
        # Determine buffer size or loop, but response is relatively short text.
        # 4096 bytes is plenty for a spoken response.
        response = client.recv(4096)
        print(response.decode("utf-8"))
        
        client.close()
    except Exception as e:
        print(f"Error communicating with agent: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

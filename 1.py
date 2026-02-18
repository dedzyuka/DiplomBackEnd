import asyncio
import websockets
asyncio.run(websockets.connect("ws://localhost:8000/ws/chat/alice"))
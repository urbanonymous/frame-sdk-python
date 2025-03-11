import asyncio
from typing import Optional, Callable, Dict, Any, Tuple
from enum import Enum
from .websocket import WebSocketBridge, FrameDataTypePrefixes

class BluetoothTCP(WebSocketBridge):
    """
    A compatibility layer that maintains the Bluetooth API but uses WebSocket connection.
    This allows existing code to continue working without changes.
    """

    def __init__(self, host: str = "localhost", port: int = 5555):
        """
        Initialize a WebSocket-based Bluetooth TCP bridge.
        
        Args:
            host (str): The hostname or IP address of the WebSocket server. Defaults to "localhost".
            port (int): The port number of the WebSocket server. Defaults to 5555.
        """
        super().__init__(host, port)
        
    async def start_keep_alive(self, interval: float = 30.0) -> asyncio.Task:
        """
        Start a keep-alive task to maintain the connection.
        
        Args:
            interval (float): The interval in seconds between keep-alive pings.
            
        Returns:
            asyncio.Task: The keep-alive task.
        """
        return await super().start_keep_alive(interval)

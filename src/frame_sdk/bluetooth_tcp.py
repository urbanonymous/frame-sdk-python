import asyncio
from typing import Optional, Callable, Dict
from enum import Enum

_FRAME_DATA_PREFIX = 1


class FrameDataTypePrefixes(Enum):
    LONG_DATA = 0x01
    LONG_DATA_END = 0x02
    WAKE = 0x03
    TAP = 0x04
    MIC_DATA = 0x05
    DEBUG_PRINT = 0x06
    LONG_TEXT = 0x0A
    LONG_TEXT_END = 0x0B

    @property
    def value_as_hex(self):
        return f"{self.value:02x}"


class BluetoothTCP:
    """
    Frame Bluetooth over TCP class for communicating with a Frame device via a TCP bridge.
    
    This class provides a TCP-based alternative to direct Bluetooth connectivity, 
    allowing communication with a Frame device through a TCP bridge application
    (such as the bt-tcp bridge app for Android). This is useful for development 
    environments where direct Bluetooth access is challenging, like within tmux sessions.
    
    The API is intentionally similar to the Bluetooth class to make it easy to switch
    between direct Bluetooth and TCP-bridged connectivity.
    """
    
    def __init__(self, host: str, port: int):
        """Initialize the BluetoothTCP connection.
        
        Args:
            host (str): The hostname or IP address of the TCP bridge
            port (int): The port number of the TCP bridge
        """
        self.host = host
        self.port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False
        self._user_disconnect_handler: Callable[[], None] = lambda: None
        self._max_receive_buffer = 10 * 1024 * 1024
        self._print_debugging = False
        self._default_timeout = 10.0
        self._last_print_response = ""
        self._ongoing_print_response: Optional[bytearray] = None
        self._ongoing_print_response_chunk_count: Optional[int] = None
        self._print_response_event = asyncio.Event()
        self._user_print_response_handler: Callable[[str], None] = lambda _: None
        self._last_data_response = bytes()
        self._ongoing_data_response: Optional[bytearray] = None
        self._ongoing_data_response_chunk_count: Optional[int] = None
        self._data_response_event = asyncio.Event()
        self._user_data_response_handlers: Dict[
            FrameDataTypePrefixes, Callable[[bytes], None]
        ] = {}
        self._max_payload_size = 512  # Configurable, no strict MTU in TCP
        self._auto_reconnect = True
        self._last_activity_time = 0

    async def connect(
        self, print_debugging: bool = False, default_timeout: float = 10.0
    ):
        """Connect to the TCP bridge.
        
        Args:
            print_debugging (bool): Whether to print debugging information
            default_timeout (float): Default timeout for operations in seconds
        
        Raises:
            Exception: If connection fails
        """
        self._print_debugging = print_debugging
        self._default_timeout = default_timeout
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self.host, self.port
            )
            self._connected = True
            self._last_activity_time = asyncio.get_event_loop().time()
            asyncio.create_task(self._read_loop())
            if self._print_debugging:
                print(f"Connected to {self.host}:{self.port}")
        except Exception as e:
            raise Exception(f"Failed to connect to {self.host}:{self.port}: {e}")

    @property
    def auto_reconnect(self) -> bool:
        """Get whether auto reconnection is enabled."""
        return self._auto_reconnect
        
    @auto_reconnect.setter
    def auto_reconnect(self, value: bool):
        """Set whether to automatically reconnect when connection is lost.
        
        Args:
            value (bool): Whether to automatically reconnect
        """
        self._auto_reconnect = value

    async def ping(self) -> bool:
        """Ping the Frame device to check if it's responsive.
        
        Returns:
            bool: True if the device responded, False otherwise
        """
        if not self.is_connected():
            return False
            
        try:
            # Send a simple command that should always produce a response
            response = await self.send_lua("print('ping')", await_print=True, timeout=2.0)
            return response == "ping"
        except Exception:
            return False
            
    async def keep_alive(self, interval: float = 30.0):
        """Start a background task to keep the connection alive by sending periodic pings.
        
        Args:
            interval (float): The interval in seconds between pings
        """
        while self.is_connected():
            current_time = asyncio.get_event_loop().time()
            if current_time - self._last_activity_time > interval:
                if self._print_debugging:
                    print("Sending keep-alive ping")
                try:
                    await self.ping()
                except Exception as e:
                    if self._print_debugging:
                        print(f"Keep-alive ping failed: {e}")
            await asyncio.sleep(interval)

    async def disconnect(self):
        """Disconnect from the device."""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        self._connected = False
        self._user_disconnect_handler()
        # Don't reinitialize on manual disconnect
        
    def is_connected(self) -> bool:
        """Check if connected to the device.
        
        Returns:
            bool: True if connected, False otherwise
        """
        return self._connected

    def set_disconnect_handler(self, handler: Callable[[], None]):
        """Set a handler to be called when the connection is lost.

        Args:
            handler (Callable[[], None]): The handler function to call when disconnected.
        """
        self._user_disconnect_handler = handler if handler else lambda: None

    async def reconnect(self):
        """Attempt to reconnect to the device if the connection is lost."""
        if self._connected:
            return
            
        try:
            print(f"Attempting to reconnect to {self.host}:{self.port}...")
            self._reader, self._writer = await asyncio.open_connection(
                self.host, self.port
            )
            self._connected = True
            asyncio.create_task(self._read_loop())
            print(f"Successfully reconnected to {self.host}:{self.port}")
        except Exception as e:
            print(f"Failed to reconnect to {self.host}:{self.port}: {e}")
            # Schedule another reconnect attempt
            asyncio.create_task(self._delayed_reconnect())
            
    async def _delayed_reconnect(self, delay: float = 5.0):
        """Wait for a delay and then attempt to reconnect.
        
        Args:
            delay (float): Time in seconds to wait before reconnecting.
        """
        await asyncio.sleep(delay)
        await self.reconnect()

    async def _read_loop(self):
        """Background task that reads data from the TCP connection."""
        while self._connected:
            try:
                # Assuming length-prefixed data (2-byte length); adjust if bridge uses different framing
                length_bytes = await self._reader.readexactly(2)
                length = int.from_bytes(length_bytes, "big")
                data = await self._reader.readexactly(length)
                # Update activity timestamp on successful read
                self._last_activity_time = asyncio.get_event_loop().time()
                await self._notification_handler(data)
            except (asyncio.IncompleteReadError, ConnectionError):
                self._connected = False
                self._user_disconnect_handler()
                if self._auto_reconnect:
                    asyncio.create_task(self._delayed_reconnect())
                break
            except Exception as e:
                print(f"Read loop error: {e}")
                if self._auto_reconnect and self._connected:
                    # Only attempt to reconnect if still marked as connected
                    self._connected = False
                    self._user_disconnect_handler()
                    asyncio.create_task(self._delayed_reconnect())
                break

    async def _notification_handler(self, data: bytearray):
        if data[0] == FrameDataTypePrefixes.LONG_TEXT.value:
            if (
                self._ongoing_print_response is None
                or self._ongoing_print_response_chunk_count is None
            ):
                self._ongoing_print_response = bytearray()
                self._ongoing_print_response_chunk_count = 0
                if self._print_debugging:
                    print("Starting receiving new long printed string")
            self._ongoing_print_response += data[1:]
            self._ongoing_print_response_chunk_count += 1
            if self._print_debugging:
                print(
                    f"Received chunk #{self._ongoing_print_response_chunk_count}: {data[1:].decode()}"
                )
            if len(self._ongoing_print_response) > self._max_receive_buffer:
                raise Exception(
                    f"Buffered long printed string exceeds {self._max_receive_buffer} bytes"
                )

        elif data[0] == FrameDataTypePrefixes.LONG_TEXT_END.value:
            total_expected_chunk_count = int(data[1:].decode()) if data[1:] else 0
            if self._print_debugging:
                print(
                    f"Received final string chunk count: {total_expected_chunk_count}"
                )
            if self._ongoing_print_response_chunk_count != total_expected_chunk_count:
                raise Exception(
                    f"Chunk count mismatch: expected {total_expected_chunk_count}, got {self._ongoing_print_response_chunk_count}"
                )
            self._last_print_response = self._ongoing_print_response.decode()
            self._print_response_event.set()
            self._ongoing_print_response = None
            self._ongoing_print_response_chunk_count = None
            if self._print_debugging:
                print(
                    f"Finished receiving long printed string: {self._last_print_response}"
                )
            self._user_print_response_handler(self._last_print_response)

        elif (
            data[0] == _FRAME_DATA_PREFIX
            and data[1] == FrameDataTypePrefixes.LONG_DATA.value
        ):
            if (
                self._ongoing_data_response is None
                or self._ongoing_data_response_chunk_count is None
            ):
                self._ongoing_data_response = bytearray()
                self._ongoing_data_response_chunk_count = 0
                self._last_data_response = bytes()
                if self._print_debugging:
                    print("Starting receiving new long raw data")
            self._ongoing_data_response += data[2:]
            self._ongoing_data_response_chunk_count += 1
            if self._print_debugging:
                print(
                    f"Received data chunk #{self._ongoing_data_response_chunk_count}: {len(data[2:])} bytes"
                )
            if len(self._ongoing_data_response) > self._max_receive_buffer:
                raise Exception(
                    f"Buffered long raw data exceeds {self._max_receive_buffer} bytes"
                )

        elif (
            data[0] == _FRAME_DATA_PREFIX
            and data[1] == FrameDataTypePrefixes.LONG_DATA_END.value
        ):
            total_expected_chunk_count = int(data[2:].decode()) if data[2:] else 0
            if self._print_debugging:
                print(f"Received final data chunk count: {total_expected_chunk_count}")
            if self._ongoing_data_response_chunk_count != total_expected_chunk_count:
                raise Exception(
                    f"Chunk count mismatch: expected {total_expected_chunk_count}, got {self._ongoing_data_response_chunk_count}"
                )
            self._last_data_response = bytes(self._ongoing_data_response)
            self._data_response_event.set()
            self._ongoing_data_response = None
            self._ongoing_data_response_chunk_count = None
            if self._print_debugging:
                print(
                    f"Finished receiving long raw data: {len(self._last_data_response)} bytes"
                )
            self.call_data_response_handlers(self._last_data_response)

        elif data[0] == _FRAME_DATA_PREFIX:
            if self._print_debugging:
                print(f"Received data: {len(data[1:])} bytes")
            self._last_data_response = data[1:]
            self._data_response_event.set()
            self.call_data_response_handlers(data[1:])

        else:
            self._last_print_response = data.decode()
            if self._print_debugging:
                print(f"Received printed string: {self._last_print_response}")
            self._print_response_event.set()
            self._user_print_response_handler(data.decode())

    async def _transmit(self, data: bytearray):
        """Send data to the device with proper error handling and reconnection logic.
        
        Args:
            data (bytearray): The data to send
            
        Raises:
            Exception: If not connected or the payload is too large
        """
        if self._print_debugging:
            print(f"Sending {len(data)} bytes: {data[:10]}{'...' if len(data) > 10 else ''}")
            
        if not self._connected:
            raise Exception("Not connected")
            
        if len(data) > self._max_payload_size:
            raise Exception(
                f"Payload too large: {len(data)} > {self._max_payload_size}. Use send_chunked_data for large payloads."
            )
            
        try:
            length_bytes = len(data).to_bytes(2, "big")
            self._writer.write(length_bytes + data)
            await self._writer.drain()
            # Update activity timestamp on successful write
            self._last_activity_time = asyncio.get_event_loop().time()
        except ConnectionError as e:
            self._connected = False
            self._user_disconnect_handler()
            raise Exception(f"Connection lost during transmission: {e}")
        except Exception as e:
            print(f"Transmission error: {e}")
            raise Exception(f"Failed to transmit data: {e}")

    def register_data_response_handler(
        self,
        prefix: FrameDataTypePrefixes = None,
        handler: Callable[[bytes], None] = None,
    ):
        if handler is None:
            self._user_data_response_handlers.pop(prefix, None)
        else:
            self._user_data_response_handlers[prefix] = (
                handler if handler.__code__.co_argcount > 0 else lambda _: handler()
            )

    def call_data_response_handlers(self, data: bytes):
        for prefix, handler in self._user_data_response_handlers.items():
            if prefix is None or (len(data) > 0 and data[0] == prefix.value):
                handler(data[1:])

    @property
    def print_response_handler(self) -> Callable[[str], None]:
        return self._user_print_response_handler

    @print_response_handler.setter
    def print_response_handler(self, handler: Callable[[str], None]):
        self._user_print_response_handler = handler if handler else lambda _: None

    def max_lua_payload(self) -> int:
        return self._max_payload_size

    def max_data_payload(self) -> int:
        return self._max_payload_size - 1  # Account for 0x01 prefix

    def set_max_payload_size(self, size: int):
        """Configure the maximum payload size for TCP transfers.
        
        TCP doesn't have the same restrictions as Bluetooth, so this can be 
        adjusted based on the bridge application capabilities.
        
        Args:
            size (int): The maximum payload size in bytes
        """
        if size < 20:  # Minimum reasonable size
            raise ValueError("Payload size must be at least 20 bytes")
        self._max_payload_size = size
        if self._print_debugging:
            print(f"Max payload size set to {size} bytes")

    @property
    def default_timeout(self) -> float:
        return self._default_timeout

    @default_timeout.setter
    def default_timeout(self, value: float):
        if value < 0:
            raise ValueError("default_timeout must be non-negative")
        self._default_timeout = value

    @property
    def print_debugging(self) -> bool:
        return self._print_debugging

    @print_debugging.setter
    def print_debugging(self, value: bool):
        self._print_debugging = value

    async def send_lua(
        self, string: str, await_print: bool = False, timeout: Optional[float] = None
    ) -> Optional[str]:
        if not self.is_connected():
            try:
                await self.reconnect()
            except Exception as e:
                raise Exception(f"Not connected and failed to reconnect: {e}")
                
        if await_print:
            self._print_response_event.clear()
        await self._transmit(string.encode())
        if await_print:
            return await self.wait_for_print(timeout)
        return None

    async def wait_for_print(self, timeout: Optional[float] = None) -> str:
        timeout = timeout if timeout is not None else self._default_timeout
        try:
            await asyncio.wait_for(self._print_response_event.wait(), timeout)
        except asyncio.TimeoutError:
            raise Exception(f"No print response within {timeout} seconds")
        self._print_response_event.clear()
        return self._last_print_response

    def start_keep_alive(self, interval: float = 30.0):
        """Start a keep-alive task in the background.
        
        This creates an asyncio task that continuously pings the device
        to maintain the connection.
        
        Args:
            interval (float): Interval between pings in seconds
        
        Returns:
            asyncio.Task: The keep-alive task
        """
        task = asyncio.create_task(self.keep_alive(interval))
        if self._print_debugging:
            print(f"Started keep-alive task with {interval}s interval")
        return task

    async def wait_for_data(self, timeout: Optional[float] = None) -> bytes:
        timeout = timeout if timeout is not None else self._default_timeout
        try:
            await asyncio.wait_for(self._data_response_event.wait(), timeout)
        except asyncio.TimeoutError:
            raise Exception(f"No data response within {timeout} seconds")
        self._data_response_event.clear()
        return self._last_data_response

    async def send_data(
        self, data: bytearray, await_data: bool = False, timeout: Optional[float] = None
    ) -> Optional[bytes]:
        if not self.is_connected():
            try:
                await self.reconnect()
            except Exception as e:
                raise Exception(f"Not connected and failed to reconnect: {e}")
                
        if await_data:
            self._data_response_event.clear()
        await self._transmit(bytearray(b"\x01") + data)
        if await_data:
            return await self.wait_for_data(timeout)
        return None

    async def send_chunked_data(self, data: bytearray, chunk_size: Optional[int] = None) -> None:
        """Send large data in chunks to the device.
        
        This method breaks up large data into manageable chunks for transmission.
        
        Args:
            data (bytearray): The data to send
            chunk_size (Optional[int]): The size of each chunk. If None, uses max_data_payload()
        """
        if not self.is_connected():
            try:
                await self.reconnect()
            except Exception as e:
                raise Exception(f"Not connected and failed to reconnect: {e}")
                
        chunk_size = chunk_size or self.max_data_payload()
        if chunk_size <= 0:
            raise ValueError("Chunk size must be positive")
            
        if len(data) <= chunk_size:
            # Small enough to send in one go
            await self.send_data(data)
            return
            
        # Break into chunks
        chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
        chunk_count = len(chunks)
        
        if self._print_debugging:
            print(f"Sending {len(data)} bytes in {chunk_count} chunks")
            
        # Send each chunk with the LONG_DATA prefix
        for i, chunk in enumerate(chunks):
            if self._print_debugging:
                print(f"Sending chunk {i+1}/{chunk_count}, {len(chunk)} bytes")
                
            # First byte is data prefix, second is LONG_DATA type
            prefix = bytearray([_FRAME_DATA_PREFIX, FrameDataTypePrefixes.LONG_DATA.value])
            await self._transmit(prefix + chunk)
            
            # Brief pause to prevent overwhelming the device
            await asyncio.sleep(0.01)
            
        # Send the end marker with chunk count
        end_prefix = bytearray([_FRAME_DATA_PREFIX, FrameDataTypePrefixes.LONG_DATA_END.value])
        await self._transmit(end_prefix + str(chunk_count).encode())
        
        if self._print_debugging:
            print(f"Finished sending chunked data")

    async def send_reset_signal(self):
        if not self.is_connected():
            await self.reconnect()
        await self._transmit(bytearray(b"\x04"))

    async def send_break_signal(self):
        if not self.is_connected():
            await self.reconnect()
        await self._transmit(bytearray(b"\x03"))

import asyncio
import websockets
from typing import Optional, Callable, List, Tuple, Dict, Any
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
        return f'{self.value:02x}'


class WebSocketBridge:
    """
    Frame WebSocket bridge class for managing a connection and transferring data to and
    from the device via a WebSocket connection.
    """

    def __init__(self, host: str = "localhost", port: int = 5555):
        """Initialize the WebSocket bridge.
        
        Args:
            host (str): The hostname or IP address of the WebSocket server. Defaults to "localhost".
            port (int): The port number of the WebSocket server. Defaults to 5555.
        """
        self._ws_connection: Optional[websockets.WebSocketClientProtocol] = None
        self._uri = f"ws://{host}:{port}"
        self._user_disconnect_handler: Callable[[], None] = lambda: None
        
        self._max_receive_buffer: int = 10 * 1024 * 1024
        self._print_debugging: bool = False
        self._default_timeout: float = 10.0
        
        self._last_print_response: str = ""
        self._ongoing_print_response: Optional[bytearray] = None
        self._ongoing_print_response_chunk_count: Optional[int] = None
        self._print_response_event: asyncio.Event = asyncio.Event()
        self._user_print_response_handler: Callable[[str], None] = lambda _: None
        
        self._last_data_response: bytes = bytes()
        self._ongoing_data_response: Optional[bytearray] = None
        self._ongoing_data_response_chunk_count: Optional[int] = None
        self._data_response_event: asyncio.Event = asyncio.Event()
        self._user_data_response_handlers: Dict[FrameDataTypePrefixes, Callable[[bytes], None]] = {}
        
        # For keeping track of MTU size (will be set by the server)
        self._mtu_size: int = 185  # Default value, will be updated on connection
        
        # Task for receiving messages
        self._receiver_task: Optional[asyncio.Task] = None
        self._keep_alive_task: Optional[asyncio.Task] = None
    
    def _disconnect_handler(self, _: Any) -> None:
        """Called internally when the websocket connection is lost.
        
        To add your own handler, supply a `disconnect_handler` when connecting.
        """
        self._user_disconnect_handler()
        self.__init__()

    async def _notification_handler(self, data: bytearray) -> None:
        """Called internally when a notification is received from the device.
        
        To add your own handlers, call `register_data_response_handler()` and/or 
        `register_print_response_handler()` when connecting.

        Args:
            data (bytearray): The data received from the device as raw bytes
        """
        if data[0] == FrameDataTypePrefixes.LONG_TEXT.value:
            # start of long printed data from prntLng() function
            if self._ongoing_print_response is None or self._ongoing_print_response_chunk_count is None:
                self._ongoing_print_response = bytearray()
                self._ongoing_print_response_chunk_count = 0
                if self._print_debugging:
                    print("Starting receiving new long printed string")
            self._ongoing_print_response += data[1:]
            self._ongoing_print_response_chunk_count += 1
            if self._print_debugging:
                print(f"Received chunk #{self._ongoing_print_response_chunk_count}: "+data[1:].decode())
            if len(self._ongoing_print_response) > self._max_receive_buffer:
                raise Exception(f"Buffered received long printed string is more than {self._max_receive_buffer} bytes")
            
        elif data[0] == FrameDataTypePrefixes.LONG_TEXT_END.value:
            # end of long printed data from prntLng() function
            total_expected_chunk_count_as_string: str = data[1:].decode()
            if len(total_expected_chunk_count_as_string) > 0:
                total_expected_chunk_count: int = int(total_expected_chunk_count_as_string)
                if self._print_debugging:
                    print(f"Received final string chunk count: {total_expected_chunk_count}")
                if self._ongoing_print_response_chunk_count != total_expected_chunk_count:
                    raise Exception(f"Chunk count mismatch in long received string (expected {total_expected_chunk_count}, got {self._ongoing_print_response_chunk_count})")
            self._last_print_response = self._ongoing_print_response.decode()
            self._print_response_event.set()
            self._ongoing_print_response = None
            self._ongoing_print_response_chunk_count = None
            if self._print_debugging:
                print("Finished receiving long printed string: "+self._last_print_response)
            self._user_print_response_handler(self._last_print_response)
            
        elif data[0] == _FRAME_DATA_PREFIX and data[1] == FrameDataTypePrefixes.LONG_DATA.value:
            # start of long raw data from frame.bluetooth.send("\001"..data)
            if self._ongoing_data_response is None or self._ongoing_data_response_chunk_count is None:
                self._ongoing_data_response = bytearray()
                self._ongoing_data_response_chunk_count = 0
                self._last_data_response = None
                if self._print_debugging:
                    print("Starting receiving new long raw data")
            self._ongoing_data_response += data[2:]
            self._ongoing_data_response_chunk_count += 1
            if self._print_debugging:
                print(f"Received data chunk #{self._ongoing_data_response_chunk_count}: {len(data[2:])} bytes")
            if len(self._ongoing_data_response) > self._max_receive_buffer:
                raise Exception(f"Buffered received long raw data is more than {self._max_receive_buffer} bytes")
            
        elif data[0] == _FRAME_DATA_PREFIX and data[1] == FrameDataTypePrefixes.LONG_DATA_END.value:
            # end of long raw data from frame.bluetooth.send("\002"..chunkCount)
            total_expected_chunk_count_as_string: str = data[2:].decode()
            if len(total_expected_chunk_count_as_string) > 0:
                total_expected_chunk_count: int = int(total_expected_chunk_count_as_string)
                if self._print_debugging:
                    print(f"Received final data chunk count: {total_expected_chunk_count}")
                if self._ongoing_data_response_chunk_count != total_expected_chunk_count:
                    raise Exception(f"Chunk count mismatch in long received data (expected {total_expected_chunk_count}, got {self._ongoing_data_response_chunk_count})")
            self._last_data_response = bytes(self._ongoing_data_response)
            self._data_response_event.set()
            self._ongoing_data_response = None
            self._ongoing_data_response_chunk_count = None
            if self._print_debugging:
                if self._last_data_response is None:
                    print("Finished receiving long raw data: No data")
                else:
                    print(f"Finished receiving long raw data: {len(self._last_data_response)} bytes")
            self.call_data_response_handlers(self._last_data_response)
            
        elif data[0] == _FRAME_DATA_PREFIX:
            # received single chunk raw data from frame.bluetooth.send(data)
            if self._print_debugging:
                print(f"Received data: {len(data[1:])} bytes")
            self._last_data_response = data[1:]
            self._data_response_event.set()
            self.call_data_response_handlers(data[1:])
            
        else:
            # received single chunk printed text from print()
            self._last_print_response = data.decode()
            if self._print_debugging:
                print(f"Received printed string: {self._last_print_response}")
            self._print_response_event.set()
            self._user_print_response_handler(data.decode())

    async def _message_receiver(self):
        """Background task that receives messages from the WebSocket connection."""
        try:
            async for message in self._ws_connection:
                if isinstance(message, bytes):
                    await self._notification_handler(bytearray(message))
                else:
                    # Handle text messages (could be control messages)
                    if message.startswith('MTU:'):
                        self._mtu_size = int(message.split(':')[1])
                        if self._print_debugging:
                            print(f"MTU size updated: {self._mtu_size}")
        except websockets.exceptions.ConnectionClosed:
            if self._print_debugging:
                print("WebSocket connection closed")
            self._disconnect_handler(None)
        except Exception as e:
            if self._print_debugging:
                print(f"Error in message receiver: {str(e)}")
            self._disconnect_handler(None)

    def register_data_response_handler(self, prefix: FrameDataTypePrefixes = None, handler: Callable[[bytes], None] = None) -> None:
        """Registers a data response handler which will be called when data is received from the device that starts with the specified prefix."""
        if handler is None:
            self._user_data_response_handlers.pop(prefix, None)
        else:
            if handler.__code__.co_argcount == 0:
                self._user_data_response_handlers[prefix] = lambda _: handler()
            else:
                self._user_data_response_handlers[prefix] = handler
            
    def call_data_response_handlers(self, data: bytes) -> None:
        """Calls all data response handlers which match the received data."""
        for prefix, handler in self._user_data_response_handlers.items():
            if prefix is None or (len(data) > 0 and data[0] == prefix.value):
                if handler is not None:
                    handler(data[1:])

    @property
    def print_response_handler(self) -> Callable[[str], None]:
        """Gets the print response handler which would be called when a print response is received."""
        return self._user_print_response_handler

    @print_response_handler.setter
    def print_response_handler(self, handler: Callable[[str], None]) -> None:
        """Sets the print response handler which will be called when a print response is received.
        
        This is an alternative to using `wait_for_print()`, to support asynchronous print handling.

        Args:
            handler (Callable[[str], None]): The handler function to be called when a print response is received.
        """
        if handler is None:
            self._user_print_response_handler = lambda _: None
        else:
            self._user_print_response_handler = handler

    async def connect(
        self,
        print_debugging: bool = False,
        default_timeout: float = 10.0,
    ) -> None:
        """
        Connects to the WebSocket server that bridges to the Frame device.
        
        `print_debugging` will output the raw bytes that are sent and received from Frame if set to True.
        `default_timeout` is the default timeout for waiting for a response from Frame, in seconds. Defaults to 10 seconds.
        """
        self._print_debugging = print_debugging
        self._default_timeout = default_timeout

        try:
            self._ws_connection = await websockets.connect(self._uri)
            
            # Start the message receiver task
            self._receiver_task = asyncio.create_task(self._message_receiver())
            
            if self._print_debugging:
                print(f"Connected to WebSocket server at {self._uri}")
                
        except Exception as e:
            raise Exception(f"Could not connect to WebSocket server: {str(e)}")

    async def disconnect(self) -> None:
        """
        Disconnects from the WebSocket server.
        """
        if self._ws_connection is not None and not self._ws_connection.closed:
            await self._ws_connection.close()
            
        if self._receiver_task is not None:
            self._receiver_task.cancel()
            try:
                await self._receiver_task
            except asyncio.CancelledError:
                pass
            self._receiver_task = None
            
        if self._keep_alive_task is not None:
            self._keep_alive_task.cancel()
            try:
                await self._keep_alive_task
            except asyncio.CancelledError:
                pass
            self._keep_alive_task = None
            
        self._disconnect_handler(None)

    def is_connected(self) -> bool:
        """
        Returns `True` if the device is connected. `False` otherwise.
        """
        return self._ws_connection is not None and not self._ws_connection.closed

    def max_lua_payload(self) -> int:
        """
        Returns the maximum length of a Lua string which may be transmitted.  This is equal to the MTU - 3.
        """
        return self._mtu_size - 3

    def max_data_payload(self) -> int:
        """
        Returns the maximum length of a raw bytearray which may be transmitted. This is equal to the MTU - 4 
        (since data is prefixed with a 1 byte header).
        """
        return self._mtu_size - 4
    
    @property
    def default_timeout(self) -> float:
        """
        Gets the default timeout value in seconds
        """
        return self._default_timeout

    @default_timeout.setter
    def default_timeout(self, value: float) -> None:
        """
        Sets the default timeout value in seconds. When waiting for print or data without 
        specifying a timeout, this value will be used as the default timeout.

        Args:
            value (float): The timeout value in seconds. Must be non-negative.
        """
        if value < 0:
            raise ValueError("default_timeout must be a non-negative float")
        self._default_timeout = value
    
    @property
    def print_debugging(self) -> bool:
        """
        Gets whether to print debugging information when sending and receiving data.
        """
        return self._print_debugging

    @print_debugging.setter
    def print_debugging(self, value: bool) -> None:
        """
        Sets whether to print debugging information when sending and receiving data.

        Args:
            value (bool): Whether to print debugging information.
        """
        self._print_debugging = value

    async def start_keep_alive(self, interval: float = 30.0) -> asyncio.Task:
        """Start a keep-alive task to maintain the connection.
        
        Args:
            interval (float): The interval in seconds between keep-alive pings.
            
        Returns:
            asyncio.Task: The keep-alive task.
        """
        async def keep_alive_loop():
            while True:
                try:
                    if self.is_connected():
                        # Send a ping message
                        await self._ws_connection.ping()
                    await asyncio.sleep(interval)
                except Exception:
                    # If an error occurs, just wait and try again
                    await asyncio.sleep(interval)
        
        self._keep_alive_task = asyncio.create_task(keep_alive_loop())
        return self._keep_alive_task

    async def _transmit(self, data: bytearray) -> None:
        """Internal function for sending raw data to the device.
        
        Instead of using this, use `send_lua()` or `send_data()`

        Args:
            data (bytearray): The data to send to the device as raw bytes

        Raises:
            Exception: If the payload length is too large or if the connection is closed
        """
        if self._print_debugging:
            print(f"Transmitting: {data}")

        if len(data) > self._mtu_size - 3:
            raise Exception(f"Payload length is too large: {len(data)} > {self._mtu_size - 3}")

        if not self.is_connected():
            raise Exception("Not connected to WebSocket server")
            
        await self._ws_connection.send(bytes(data))

    async def send_lua(self, string: str, await_print: bool = False, timeout: Optional[float] = None) -> Optional[str]:
        """
        Sends a Lua string to the device. The string length must be less than or
        equal to `max_lua_payload()`.
        
        In general, you'd be better off using Frame.run_lua(), which handles sending an receiving values 
        longer that the MTU limit. This is the lower-level function to send an individual Lua string.
        
        If `await_print=True`, the function will block until a Lua print()
        occurs, or a timeout.

        Args:
            string (str): The Lua string to send.
            await_print (bool): Whether to block while waiting for a print response.
            timeout (Optional[float]): The timeout for waiting for a print response. If not provided, 
                the default timeout will be used.

        Returns:
            Optional[str]: The print response if `await_print` is True, otherwise None.
        """
        if await_print:
            self._print_response_event.clear()
            
        await self._transmit(string.encode())

        if await_print:
            return await self.wait_for_print(timeout)
        
    async def wait_for_print(self, timeout: Optional[float] = None) -> str:
        """
        Waits until a Lua print() occurs, with a max timeout in seconds. If `timeout` is not provided, 
        the default timeout will be used, rather than no timeout at all.

        Args:
            timeout (Optional[float]): The timeout for waiting for a print response. If not provided, 
                the default timeout will be used.

        Returns:
            str: The last print response received.
        """
        if timeout is None:
            timeout = self._default_timeout

        try:
            await asyncio.wait_for(self._print_response_event.wait(), timeout)
        except asyncio.TimeoutError:
            raise Exception(f"Frame didn't respond with printed data (from print() or prntLng()) within {timeout} seconds")

        self._print_response_event.clear()

        return self._last_print_response
    
    async def wait_for_data(self, timeout: Optional[float] = None) -> bytes:
        """
        Waits until data has been received from the device, with a max timeout in seconds. 
        If `timeout` is not provided, the default timeout will be used, rather than no timeout at all.

        Args:
            timeout (Optional[float]): The timeout for waiting for a data response. If not provided, 
                the default timeout will be used.

        Returns:
            bytes: The last data response received.
        """
        if timeout is None:
            timeout = self._default_timeout

        try:
            await asyncio.wait_for(self._data_response_event.wait(), timeout)
        except asyncio.TimeoutError:
            raise Exception(f"Frame didn't respond with data (from frame.bluetooth.send(data)) within {timeout} seconds")
        
        self._data_response_event.clear()

        return self._last_data_response

    async def send_data(self, data: bytearray, await_data: bool = False) -> Optional[bytes]:
        """
        Sends raw data to the device. The payload length must be less than or
        equal to `max_data_payload()`.
        
        If `await_data=True`, the function will block until a data response
        occurs, or a timeout.

        Args:
            data (bytearray): The raw data to send.
            await_data (bool): Whether to block while waiting for a data response.

        Returns:
            Optional[bytes]: The data response if `await_data` is True, otherwise None.
        """
        if await_data:
            self._data_response_event.clear()

        await self._transmit(bytearray(b"\x01") + data)

        if await_data:
            return await self.wait_for_data()

    async def send_reset_signal(self) -> None:
        """
        Sends a reset signal to the device which will reset the Lua virtual
        machine.
        """
        if not self.is_connected():
            await self.connect()
        await self._transmit(bytearray(b"\x04"))

    async def send_break_signal(self) -> None:
        """
        Sends a break signal to the device which will break any currently
        executing Lua script.
        """
        if not self.is_connected():
            await self.connect()
        await self._transmit(bytearray(b"\x03")) 
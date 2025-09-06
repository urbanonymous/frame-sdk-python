#!/usr/bin/env python3
import asyncio
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.frame_sdk.bluetooth_fake import Bluetooth, FrameDataTypePrefixes

async def main():
    """
    Example showing how to use the fake Bluetooth implementation.
    
    This demonstrates:
    1. Connecting to a fake device
    2. Sending data and Lua code
    3. Simulating responses from the device
    4. Using data response handlers
    """
    # Create a Bluetooth instance
    bt = Bluetooth()
    
    # Enable debugging to see all data transfers
    await bt.connect(print_debugging=True)
    print("Connected to fake device")
    
    # Register a callback for data responses with a specific prefix
    def on_tap_data(data: bytes):
        print(f"Tap data received: {data.hex()}")
    
    bt.register_data_response_handler(FrameDataTypePrefixes.TAP, on_tap_data)
    
    # Also register a callback for general print responses
    bt.print_response_handler = lambda text: print(f"Print handler received: {text}")
    
    # Send some Lua code
    print("\nSending Lua code...")
    await bt.send_lua('print("Hello from Lua")')
    
    # Simulate a response from the device
    print("\nSimulating device print response...")
    await bt.simulate_receive(bytearray(b"Hello from device"))
    
    # Send data and simulate a response
    print("\nSending data and awaiting response...")
    await bt.send_data(bytearray(b"test data"), await_data=True)
    
    # Simulate a TAP event from the device
    print("\nSimulating a TAP event...")
    tap_data = bytearray([FrameDataTypePrefixes.TAP.value, 1, 2, 3, 4])
    await bt.simulate_receive(tap_data)
    
    # Simulate a long text message that comes in chunks
    print("\nSimulating a long text message...")
    # Start chunk
    await bt.simulate_receive(bytearray([FrameDataTypePrefixes.LONG_TEXT.value]) + bytearray(b"First chunk of a "))
    # Middle chunk
    await bt.simulate_receive(bytearray([FrameDataTypePrefixes.LONG_TEXT.value]) + bytearray(b"long message that "))
    # Final chunk + end marker with chunk count
    await bt.simulate_receive(bytearray([FrameDataTypePrefixes.LONG_TEXT.value]) + bytearray(b"spans multiple chunks"))
    await bt.simulate_receive(bytearray([FrameDataTypePrefixes.LONG_TEXT_END.value]) + bytearray(b"3"))
    
    # Simulate a long data message
    print("\nSimulating a long data message...")
    # Start chunk with Frame data prefix
    await bt.simulate_receive(bytearray([1, FrameDataTypePrefixes.LONG_DATA.value]) + bytearray(b"\x01\x02\x03\x04"))
    # Second chunk
    await bt.simulate_receive(bytearray([1, FrameDataTypePrefixes.LONG_DATA.value]) + bytearray(b"\x05\x06\x07\x08"))
    # End marker with chunk count
    await bt.simulate_receive(bytearray([1, FrameDataTypePrefixes.LONG_DATA_END.value]) + bytearray(b"2"))
    
    # Wait for print with explicit timeout
    print("\nWaiting for print with timeout...")
    try:
        # This would timeout if no print happens
        asyncio.create_task(bt.wait_for_print(timeout=1.0))
        # Simulate print response before timeout
        await asyncio.sleep(0.5)
        await bt.simulate_receive(bytearray(b"Print before timeout"))
    except Exception as e:
        print(f"Timeout error: {e}")
    
    # Disconnect
    print("\nDisconnecting...")
    await bt.disconnect()
    print("Disconnected from fake device")

if __name__ == "__main__":
    asyncio.run(main()) 
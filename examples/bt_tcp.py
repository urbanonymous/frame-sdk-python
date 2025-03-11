#!/usr/bin/env python3
import asyncio
import logging
import time

from frame_sdk.frame import Frame

async def main():
    """Connect to a Frame device via Bluetooth TCP and run a simple test.
    
    This example uses a conservative MTU size of 20 bytes for better
    compatibility with all Frame devices. It sends a minimal Lua script
    that should work even with the smallest MTU sizes.
    """
    print("Connecting to Frame device via Bluetooth TCP...")
    print("Using conservative MTU size of 20 bytes for better compatibility")
    
    try:
        # Connect to the Frame with a small MTU size
        async with Frame(host="localhost", port=8011, log_level=logging.INFO, mtu_size=20) as frame:
            # Output negotiated MTU size
            print(f"Connected to Frame. Negotiated MTU: {frame.get_mtu_size()} bytes")
            
            # Try smallest possible Lua script (just "1+1")
            print("\nSending tiny Lua script: 1+1")
            response = await frame.send_lua("print(1+1)", wait_for_print=True)
            print(f"Print response: {response}")
            
            # Wait a moment
            print("\nConnection test completed successfully!")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())

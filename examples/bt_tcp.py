import asyncio
import sys
import os
import logging

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.frame_sdk import Frame

async def main():
    # Configure logging (optional)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # For more detailed logging, uncomment the line below
    # logging.getLogger('frame_sdk').setLevel(logging.DEBUG)
    
    print("Connecting to Frame device via Bluetooth TCP...")
    print("Using explicit MTU size of 185 bytes for better performance")
    
    # Connect to a Frame device over Bluetooth TCP at localhost:5555
    # Use log_level=logging.DEBUG for more verbose logs
    # Set MTU size to 185 bytes (optimal for Frame devices)
    async with Frame(host="localhost", port=5555, log_level=logging.INFO, mtu_size=185) as frame:

        print("Connected to Frame device! -- Running example code...")
        print(f"Using MTU size: {frame.bluetooth._detected_mtu} bytes")
        print(f"Max payload size: {frame.bluetooth._max_payload_size} bytes")
        
        # Get the battery level
        battery_level = await frame.get_battery_level()
        print(f"Battery level: {battery_level}%")
        
        # Run a simple Lua script
        print("Running a test Lua script...")
        result = await frame.run_lua('return "Hello from Frame!"', await_print=True)
        print(f"Result: {result}")
        
        # Example of using the display
        print("Displaying a simple message...")
        await frame.run_lua('''
        display.clear()
        display.setCursor(0, 0)
        display.setFont(FONT_LARGE)
        display.print("Hello World!")
        display.flush()
        ''')
        
        # Send some data to demonstrate data logging
        print("Sending some binary data...")
        test_data = bytearray([0x01, 0x02, 0x03, 0x04, 0x05] * 20)  # 100 bytes
        await frame.bluetooth.send_data(test_data)
        
        print("Example completed successfully!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program interrupted by user.")
    except Exception as e:
        print(f"Error: {e}")

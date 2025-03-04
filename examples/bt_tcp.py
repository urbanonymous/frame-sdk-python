import asyncio
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.frame_sdk import Frame

async def main():
    # Connect to a Frame device over Bluetooth TCP at localhost:5555
    async with Frame(host="localhost", port=5555) as frame:
        print("Connected to Frame device!")
        
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
        
        # Wait a moment
        print("Waiting for 2 seconds...")
        await frame.delay(2)
        
        print("Example completed!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program interrupted by user.")
    except Exception as e:
        print(f"Error: {e}")

import asyncio
import sys
import os
import logging

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.frame_sdk import Frame
from src.frame_sdk.display import PaletteColors

async def main():

    print("Connecting to Frame device via Bluetooth TCP...")
    print("Using explicit MTU size of 185 bytes for better performance")
    
    # Connect to a Frame device over Bluetooth TCP at localhost:5555
    # Use log_level=logging.DEBUG for more verbose logs
    # Set MTU size to 185 bytes (optimal for Frame devices)
    async with Frame(host="localhost", port=5555, log_level=logging.INFO, mtu_size=20) as frame:

        await frame.bluetooth.send_break_signal()

        await frame.run_lua("spinning_my_wheels = 0;while true do;spinning_my_wheels=spinning_my_wheels+1;end", checked=False)
        print("Frame is currently spinning its wheels, but python keeps going")

        await frame.bluetooth.send_break_signal()
        print("Now Frame has been broken out of its loop and we can talk to it again")

        print(await frame.evaluate("'I\\m back!'"))
        # prints I'm back!



        # basic usage
        await frame.run_lua("frame.display.text('Hello world', 50, 100);frame.display.show()")

        # draws a white rectangle 200x200 pixels in the center of the screen
        await frame.display.draw_rect(220, 100, 200, 200, PaletteColors.WHITE)

        # draws a red rectangle 16x16 pixels in the center of the screen
        await frame.display.draw_rect(320-8, 200-8, 16, 16, PaletteColors.RED)

        # show both rectangles
        await frame.display.show()

        # return data via print()
        time_since_reboot = await frame.run_lua("print(frame.time.utc() .. \" seconds\")", await_print = True)
        print(f"Frame has been on for {time_since_reboot}.")

        # both the lua code you send and any replies sent back via print() can be of any length
        print(await frame.run_lua("text = 'Look ma, no MTU limit! ';text=text..text;text=text..text;text=text..text;text=text..text;print(text)", await_print = True))

        # let long running commands run in parallel
        await frame.run_lua("spinning_my_wheels = 0;while true do;spinning_my_wheels=spinning_my_wheels+1;end", checked=False)
        print("Frame is currently spinning its wheels, but python keeps going")

        # raises a timeout exception after 10 seconds
        await frame.run_lua("spinning_my_wheels = 0;while true do;spinning_my_wheels=spinning_my_wheels+1;end", checked=True, timeout=10)

        # raises an exception with the Lua syntax error
        await frame.run_lua("Syntax?:Who$needs!syntax?", checked=True)

        
        print("Example completed successfully!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program interrupted by user.")
    except Exception as e:
        print(f"Error: {e}")

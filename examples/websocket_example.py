import asyncio
from frame_sdk import Frame
from frame_sdk.display import PaletteColors, Alignment

async def main():
    """Example of using the WebSocket-based Frame implementation."""
    
    # Connect to the WebSocket server on port 5555
    async with Frame(host="localhost", port=5555) as frame:
        print("Connected to Frame via WebSocket!")
        

        # Get the battery level
        battery_level = await frame.get_battery_level()
        print(f"Battery level: {battery_level}%")
        
        # Run a simple Lua script
        print("Running a test Lua script...")
        result = await frame.run_lua('return "Hello from Frame!"', await_print=True)
        print(f"Result: {result}")

        breakpoint()
        # Display a message
        await frame.display.clear()
        await frame.display.show_text(
            "Connected via WebSocket!",
            align=Alignment.MIDDLE_CENTER,
            color=PaletteColors.GREEN
        )
        
        # Get battery level
        battery = await frame.get_battery_level()
        print(f"Battery level: {battery}%")
        
        # Take a photo
        print("Taking a photo...")
        photo = await frame.camera.take_photo()
        
        # Save the photo locally
        with open("websocket_test_photo.jpg", "wb") as f:
            f.write(photo)
        print(f"Photo saved to websocket_test_photo.jpg ({len(photo)} bytes)")
        
        # Sleep for a bit
        await asyncio.sleep(2)
        
        # Show goodbye message
        await frame.display.show_text(
            "WebSocket Test Complete!",
            align=Alignment.MIDDLE_CENTER,
            color=PaletteColors.SKYBLUE
        )

if __name__ == "__main__":
    asyncio.run(main()) 
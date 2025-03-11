import asyncio
import sys
import os
import logging
import argparse

# Add the src directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.frame_sdk import Frame

async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Frame SDK Logging Demo')
    parser.add_argument('--host', default="localhost", help='Host address for Frame device')
    parser.add_argument('--port', type=int, default=5555, help='Port number for Frame device')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--log-file', help='Log to file instead of console')
    parser.add_argument('--mtu', type=int, default=185, help='MTU size to negotiate (default: 185)')
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    
    # Setup logging configuration
    log_handlers = []
    
    # Add console handler
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    log_handlers.append(console_handler)
    
    # Add file handler if specified
    if args.log_file:
        file_handler = logging.FileHandler(args.log_file)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        log_handlers.append(file_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        handlers=log_handlers,
        force=True  # Overwrite any existing configuration
    )
    
    logger = logging.getLogger('frame_sdk_demo')
    logger.info(f"Starting Frame SDK Logging Demo - connecting to {args.host}:{args.port}")
    logger.info(f"Using MTU size: {args.mtu} bytes (0x{args.mtu:04X}, little-endian: 0x{args.mtu & 0xFF:02X} 0x{(args.mtu >> 8) & 0xFF:02X})")
    
    # Connect to Frame device
    frame = None
    try:
        logger.info("Initializing Frame connection...")
        frame = Frame(host=args.host, port=args.port, log_level=log_level, mtu_size=args.mtu)
        
        logger.info("Connecting to Frame device...")
        async with frame:
            logger.info("Connected to Frame device")
            logger.info(f"MTU size: {frame.bluetooth._detected_mtu} bytes")
            logger.info(f"Max payload size: {frame.bluetooth._max_payload_size} bytes")
            
            # Test sending a simple lua script
            logger.info("Sending a small Lua script...")
            result = await frame.run_lua('return "Hello from Frame!"', await_print=True)
            logger.info(f"Result from small script: {result}")
            
            # Test sending a larger Lua script (demonstrates chunking)
            logger.info("Sending a larger Lua script (will use chunking if MTU is small)...")
            large_script = """
            local result = "This is a much larger Lua script to test chunking functionality."
            for i = 1, 5 do
                result = result .. " Line " .. i .. " adds more content to ensure we exceed smaller MTU sizes."
            end
            return result
            """
            result = await frame.run_lua(large_script, await_print=True)
            logger.info(f"Result from large script: {result}")
            
            # Test sending binary data
            logger.info("Sending binary data...")
            test_data = bytearray([0x01, 0x02, 0x03, 0x04, 0x05] * 30)  # 150 bytes
            await frame.bluetooth.send_data(test_data)
            
            # Display MTU information
            logger.info(f"Detected MTU size: {frame.bluetooth._detected_mtu}")
            logger.info(f"Current max payload size: {frame.bluetooth._max_payload_size}")
            
            logger.info("Changing log level dynamically (INFO → DEBUG)")
            frame.set_log_level(logging.DEBUG)
            
            # Send another message with debug logging enabled
            logger.info("Sending another message with DEBUG log level...")
            await frame.run_lua('print("Testing with DEBUG log level")', await_print=True)
            
            # Change back to INFO level
            logger.info("Changing log level back to INFO")
            frame.set_log_level(logging.INFO)
            
            logger.info("Demo completed successfully!")
    
    except Exception as e:
        logger.error(f"Error in demo: {e}", exc_info=True)
    finally:
        if frame and frame.bluetooth.is_connected():
            logger.info("Disconnecting from Frame device...")
            await frame.bluetooth.disconnect()
    
    logger.info("Demo finished")

if __name__ == "__main__":
    asyncio.run(main()) 
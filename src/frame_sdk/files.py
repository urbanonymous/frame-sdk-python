from __future__ import annotations
import asyncio
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .frame import Frame

class Files:
    """Helpers for accessing the Frame filesystem."""
    
    frame: "Frame" = None
    
    def __init__(self, frame: "Frame"):
        """
        Initialize the Files helper with a Frame instance.

        Args:
            frame (Frame): The Frame instance to use for filesystem operations.
        """
        self.frame = frame
    
    async def write_file(self, path: str, data: bytes, checked: bool = False) -> None:
        """
        Write a file to the device.

        Args:
            path (str): The full filename to write on the Frame.
            data (bytes): The data to write to the file as bytes.  You can use .encode() to get bytes from a string.
            checked (bool, optional): If True, each step of writing will wait for acknowledgement from the Frame before continuing. Defaults to False.
        
        Raises:
            Exception: If the file cannot be opened, written to, or closed.
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self.frame.bluetooth.send_lua(
                    f"w=frame.file.open(\"{path}\",\"write\")" +
                    (";print(\"o\")" if checked else ""), await_print=checked)
                if checked and response != "o":
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        raise Exception(f"Couldn't open file \"{path}\" for writing: {response}")
                
                response = await self.frame.bluetooth.send_lua(
                    f"frame.bluetooth.receive_callback((function(d)w:write(d)end))" +
                    (";print(\"c\")" if checked else ""), await_print=checked)
                if checked and response != "c":
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        raise Exception(f"Couldn't register callback for writing to file \"{path}\": {response}")
                
                # Use a smaller chunk size to accommodate small MTU
                # For MTU of 20, we need a max_chunk of around 16 bytes
                max_chunk_size = 16
                
                # Track the number of chunks for the final LONG_DATA_END message
                current_index = 0
                chunk_count = 0
                
                while current_index < len(data):
                    next_chunk_length = min(len(data) - current_index, max_chunk_size)
                    if next_chunk_length == 0:
                        break
                    
                    chunk = data[current_index:current_index+next_chunk_length]
                    # Send data with LONG_DATA prefix (0x01)
                    await self.frame.bluetooth.send_data(bytes([1]) + chunk)
                    # Add a small delay between chunks to avoid overwhelming the device
                    await asyncio.sleep(0.05)
                    current_index += next_chunk_length
                    chunk_count += 1
                
                # Send LONG_DATA_END marker (0x02) with the chunk count
                if chunk_count > 0:
                    await self.frame.bluetooth.send_data(bytes([2]) + str(chunk_count).encode())
                
                response = await self.frame.bluetooth.send_lua(
                    "w:close()" + (";print(\"+\")" if checked else ""),
                    await_print=checked)
                if checked and response != "+":
                    if attempt < max_retries - 1:
                        await asyncio.sleep(0.5)
                        continue
                    else:
                        raise Exception(f"Couldn't close file \"{path}\": {response}")
                
                # If we get here, we've successfully written the file
                break
                
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"Error writing file \"{path}\" (attempt {attempt+1}/{max_retries}): {str(e)}. Retrying...")
                    await asyncio.sleep(0.5)
                else:
                    print(f"Failed to write file \"{path}\" after {max_retries} attempts: {str(e)}")
                    raise
        
    async def file_exists(self, path: str) -> bool:
        """
        Check if a file exists on the device.

        Args:
            path (str): The full path to the file to check.

        Returns:
            bool: True if the file exists, False otherwise.
        """
        response_from_opening = await self.frame.bluetooth.send_lua(
            f"r=frame.file.open(\"{path}\",\"read\");print(\"o\");r:close()", await_print=True)
        return response_from_opening == "o"
    
    async def delete_file(self, path: str) -> bool:
        """
        Delete a file on the device.

        Args:
            path (str): The full path to the file to delete.

        Returns:
            bool: True if the file was deleted, False if it didn't exist or failed to delete.
        """
        response = await self.frame.bluetooth.send_lua(f"frame.file.remove(\"{path}\");print(\"d\")", await_print=True)
        return response == "d"
    
    async def read_file(self, path: str) -> bytes:
        """
        Read a file from the device.

        Args:
            path (str): The full filename to read on the Frame.

        Returns:
            bytes: The content of the file as bytes.  You can use .decode() to get a string.
        
        Raises:
            Exception: If the file does not exist.
        """
        await self.frame.run_lua(f"printCompleteFile(\"{path}\")")
        result: bytes = await self.frame.bluetooth.wait_for_data()
        return result.strip()
import asyncio
from typing import Any, Callable, Dict, Optional, Set
from dataclasses import dataclass


@dataclass
class FakeGattCharacteristic:
    """Fake GATT characteristic for simulating Bluetooth characteristics."""
    uuid: str
    service_uuid: str
    handle: int = 0


@dataclass
class FakeGattService:
    """Fake GATT service for simulating Bluetooth services."""
    uuid: str
    characteristics: Dict[str, FakeGattCharacteristic]
    
    def get_characteristic(self, uuid: str) -> FakeGattCharacteristic:
        """Get a characteristic by UUID."""
        return self.characteristics.get(uuid)


class FakeBleakClient:
    """
    A fake implementation of BleakClient that uses queues for communication instead
    of actual Bluetooth communication.
    """
    
    def __init__(self, address, disconnected_callback=None):
        self.address = address
        self.disconnected_callback = disconnected_callback
        self._is_connected = False
        self.mtu_size = 517  # Default MTU size
        
        # Queues for simulating data transfer
        self.rx_queue = asyncio.Queue()  # Device -> Host
        self.tx_queue = asyncio.Queue()  # Host -> Device
        
        # Notification callbacks
        self._notification_callbacks: Dict[str, Callable] = {}
        
        # Services
        self._services: Dict[str, FakeGattService] = {}
        
        # Background task for notification dispatcher
        self._notification_task = None
    
    async def connect(self) -> bool:
        """Connect to the fake device."""
        self._is_connected = True
        # Start the notification dispatcher task
        self._notification_task = asyncio.create_task(self._notification_dispatcher())
        return True
    
    async def disconnect(self) -> bool:
        """Disconnect from the fake device."""
        if self._notification_task:
            self._notification_task.cancel()
            try:
                await self._notification_task
            except asyncio.CancelledError:
                pass
        
        self._is_connected = False
        if self.disconnected_callback:
            self.disconnected_callback(self)
        return True
    
    async def _notification_dispatcher(self):
        """Background task to dispatch notifications from rx_queue to callbacks."""
        while True:
            try:
                # Wait for messages to arrive in the rx_queue
                uuid, data = await self.rx_queue.get()
                callback = self._notification_callbacks.get(uuid)
                if callback:
                    # Call the notification callback with the sender and data
                    await callback(self, data)
                self.rx_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in notification dispatcher: {e}")
    
    async def write_gatt_char(self, characteristic, data, response=True) -> None:
        """Write data to a characteristic, which puts it in the tx_queue."""
        if not self._is_connected:
            raise Exception("Not connected")
        
        # Store the data in the tx_queue
        await self.tx_queue.put((characteristic.uuid, data))
    
    async def start_notify(self, uuid, callback) -> None:
        """Register a callback for notifications from a characteristic."""
        self._notification_callbacks[uuid] = callback
    
    async def stop_notify(self, uuid) -> None:
        """Remove a notification callback."""
        self._notification_callbacks.pop(uuid, None)
    
    def add_service(self, service_uuid: str, characteristics: Dict[str, str]) -> None:
        """Add a service with characteristics to the fake device."""
        char_objects = {}
        for uuid, _ in characteristics.items():
            char_objects[uuid] = FakeGattCharacteristic(uuid=uuid, service_uuid=service_uuid)
        
        self._services[service_uuid] = FakeGattService(
            uuid=service_uuid,
            characteristics=char_objects
        )
    
    def get_service(self, uuid: str) -> Optional[FakeGattService]:
        """Get a service by UUID."""
        return self._services.get(uuid)
    
    @property
    def services(self):
        """Return a service collection object that mimics Bleak's service collection."""
        return ServiceCollection(self._services)
    
    @property
    def is_connected(self) -> bool:
        """Return connection status."""
        return self._is_connected
    
    async def simulate_receive(self, characteristic_uuid: str, data: bytearray) -> None:
        """
        Simulate receiving data from the device.
        This method allows tests to push data into the rx_queue as if it came from the device.
        """
        await self.rx_queue.put((characteristic_uuid, data))
    
    async def _acquire_mtu(self) -> None:
        """Simulate acquiring MTU size."""
        # This is a no-op in the fake implementation
        pass


class ServiceCollection:
    """Mock for BleakClient's services collection."""
    
    def __init__(self, services: Dict[str, FakeGattService]):
        self._services = services
    
    def get_service(self, uuid: str) -> Optional[FakeGattService]:
        """Get a service by UUID."""
        return self._services.get(uuid) 
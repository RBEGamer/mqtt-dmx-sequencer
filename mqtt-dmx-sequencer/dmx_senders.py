#!/usr/bin/env python3
import threading
import time
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from pyartnet import ArtNetNode
import sacn


class DMXSender(ABC):
    """Abstract base class for DMX senders"""
    
    def __init__(self, universe_id: int = 1, test_mode: bool = False):
        self.universe_id = universe_id
        self.lock = threading.Lock()
        self.universe_data = [0] * 512
        self._active = False
        self.test_mode = test_mode
    
    @abstractmethod
    def start(self):
        """Start the DMX sender"""
        pass
    
    @abstractmethod
    def stop(self):
        """Stop the DMX sender"""
        pass
    
    @abstractmethod
    def send(self):
        """Send the current universe data"""
        pass
    
    def set_channel(self, channel: int, value: int):
        """Set a specific channel value"""
        # Convert string values to integers if needed
        try:
            if isinstance(channel, str):
                channel = int(channel)
            if isinstance(value, str):
                value = int(value)
        except (ValueError, TypeError):
            print(f"Invalid channel ({channel}) or value ({value})")
            return
        
        with self.lock:
            if 1 <= channel <= 512 and 0 <= value <= 255:
                self.universe_data[channel - 1] = value
    
    def set_channels(self, channels: Dict[int, int]):
        """Set multiple channels at once"""
        with self.lock:
            for channel, value in channels.items():
                # Convert string values to integers if needed
                try:
                    if isinstance(channel, str):
                        channel = int(channel)
                    if isinstance(value, str):
                        value = int(value)
                except (ValueError, TypeError):
                    print(f"Invalid channel ({channel}) or value ({value})")
                    continue
                
                if 1 <= channel <= 512 and 0 <= value <= 255:
                    self.universe_data[channel - 1] = value
                else:
                    print(f"Channel {channel} or value {value} out of range (1-512, 0-255)")
    
    def blackout(self):
        """Set all channels to 0"""
        with self.lock:
            self.universe_data = [0] * 512
        self.send()
    
    def get_universe_data(self) -> List[int]:
        """Get current universe data"""
        with self.lock:
            return self.universe_data.copy()
    
    @property
    def active(self) -> bool:
        return self._active


class ArtNetSender(DMXSender):
    """Art-Net DMX sender implementation"""
    
    def __init__(self, target_ip: str = '255.255.255.255', port: int = 6454, universe_id: int = 1):
        super().__init__(universe_id)
        self.target_ip = target_ip
        self.port = port
        self.node = None
        self.universe = None
        self.channel = None
    
    def start(self):
        """Start the Art-Net node"""
        try:
            self.node = ArtNetNode(self.target_ip, self.port, refresh_every=0.1)
            self.universe = self.node.add_universe(self.universe_id)
            self.channel = self.universe.add_channel(start=1, width=512)
            self.node.start()
            self._active = True
            print(f"Art-Net sender started - Target: {self.target_ip}:{self.port}, Universe: {self.universe_id}")
        except Exception as e:
            print(f"Failed to start Art-Net sender: {e}")
            self._active = False
    
    def stop(self):
        """Stop the Art-Net node"""
        if self.node:
            try:
                self.node.stop()
                self._active = False
                print(f"Art-Net sender stopped - Universe: {self.universe_id}")
            except Exception as e:
                print(f"Error stopping Art-Net sender: {e}")
    
    def send(self):
        """Send current universe data via Art-Net"""
        if self._active and self.channel:
            with self.lock:
                try:
                    print(f"Art-Net sending universe {self.universe_id} data: {self.universe_data[:10]}... (first 10 channels)")
                    self.channel.add_fade(self.universe_data, 0)  # 0ms fade
                except Exception as e:
                    print(f"Error sending Art-Net data: {e}")
        else:
            print(f"Art-Net sender not active or not initialized. Active: {self._active}, Channel: {self.channel is not None}")


class TestSender(DMXSender):
    """Test DMX sender that just prints data (for debugging)"""
    
    def __init__(self, universe_id: int = 1):
        super().__init__(universe_id, test_mode=True)
        self._active = True
        print(f"Test DMX sender started - Universe: {universe_id}")
    
    def start(self):
        """Test sender is always active"""
        self._active = True
        print(f"Test DMX sender started - Universe: {self.universe_id}")
    
    def stop(self):
        """Stop the test sender"""
        self._active = False
        print(f"Test DMX sender stopped - Universe: {self.universe_id}")
    
    def send(self):
        """Print current universe data"""
        if self._active:
            with self.lock:
                # Find non-zero channels
                active_channels = {i+1: val for i, val in enumerate(self.universe_data) if val > 0}
                if active_channels:
                    print(f"TEST DMX - Universe {self.universe_id} - Active channels: {active_channels}")
                else:
                    print(f"TEST DMX - Universe {self.universe_id} - All channels at 0")


class E131Sender(DMXSender):
    """E1.31 (sACN) DMX sender implementation"""
    
    def __init__(self, target_ip: str = '255.255.255.255', universe_id: int = 1, fps: int = 40):
        super().__init__(universe_id)
        self.target_ip = target_ip
        self.fps = fps
        self.sender = None
    
    def start(self):
        """Start the E1.31 sender"""
        try:
            # Try to stop any existing sender first
            if hasattr(self, 'sender') and self.sender:
                try:
                    self.sender.stop()
                except:
                    pass
            
            # Try different ports if the default one is in use
            for attempt in range(3):
                try:
                    self.sender = sacn.sACNsender(fps=self.fps)
                    self.sender.start()
                    self.sender.activate_output(self.universe_id)
                    self.sender[self.universe_id].multicast = True
                    self.sender[self.universe_id].destination = self.target_ip
                    self._active = True
                    print(f"E1.31 sender started - Target: {self.target_ip}, Universe: {self.universe_id}, FPS: {self.fps}")
                    break
                except OSError as e:
                    if "Address already in use" in str(e) and attempt < 2:
                        print(f"Port conflict, retrying... (attempt {attempt + 1})")
                        time.sleep(1)
                        continue
                    else:
                        raise e
        except Exception as e:
            print(f"Failed to start E1.31 sender: {e}")
            self._active = False
    
    def stop(self):
        """Stop the E1.31 sender"""
        if self.sender:
            try:
                self.sender.stop()
                self._active = False
                print(f"E1.31 sender stopped - Universe: {self.universe_id}")
            except Exception as e:
                print(f"Error stopping E1.31 sender: {e}")
    
    def send(self):
        """Send current universe data via E1.31"""
        if self._active and self.sender:
            with self.lock:
                try:
                    print(f"E1.31 sending universe {self.universe_id} data: {self.universe_data[:10]}... (first 10 channels)")
                    self.sender[self.universe_id].dmx_data = self.universe_data
                except Exception as e:
                    print(f"Error sending E1.31 data: {e}")
        else:
            print(f"E1.31 sender not active or not initialized. Active: {self._active}, Sender: {self.sender is not None}")


class DMXManager:
    """Manager for multiple DMX senders"""
    
    def __init__(self):
        self.senders: Dict[str, DMXSender] = {}
        self.lock = threading.Lock()
    
    def add_sender(self, name: str, sender: DMXSender) -> bool:
        """Add a DMX sender with a unique name"""
        with self.lock:
            if name in self.senders:
                print(f"Sender '{name}' already exists")
                return False
            
            self.senders[name] = sender
            sender.start()
            
            # Check if the sender is actually active after starting
            if not sender.active:
                print(f"Warning: Sender '{name}' failed to start properly")
                return False
                
            return True
    
    def remove_sender(self, name: str) -> bool:
        """Remove a DMX sender by name"""
        with self.lock:
            if name not in self.senders:
                print(f"Sender '{name}' not found")
                return False
            
            sender = self.senders[name]
            sender.stop()
            del self.senders[name]
            return True
    
    def get_sender(self, name: str) -> DMXSender:
        """Get a DMX sender by name"""
        with self.lock:
            return self.senders.get(name)
    
    def list_senders(self) -> List[str]:
        """List all sender names"""
        with self.lock:
            return list(self.senders.keys())
    
    def set_channel(self, channel: int, value: int, sender_name: str = None):
        """Set a channel on specific sender or all senders"""
        # Convert string values to integers if needed
        try:
            if isinstance(channel, str):
                channel = int(channel)
            if isinstance(value, str):
                value = int(value)
        except (ValueError, TypeError):
            print(f"Invalid channel ({channel}) or value ({value})")
            return
        
        with self.lock:
            if sender_name:
                if sender_name in self.senders:
                    self.senders[sender_name].set_channel(channel, value)
                else:
                    print(f"Sender '{sender_name}' not found")
            else:
                # Set on all active senders
                for sender in self.senders.values():
                    if sender.active:
                        sender.set_channel(channel, value)
    
    def set_channels(self, channels: Dict[int, int], sender_name: str = None):
        """Set multiple channels on specific sender or all senders"""
        # Convert string keys to integers if needed
        dmx_channels = {}
        for channel_key, value in channels.items():
            try:
                if isinstance(channel_key, str):
                    channel = int(channel_key)
                else:
                    channel = channel_key
                dmx_channels[channel] = value
            except (ValueError, TypeError):
                print(f"Invalid channel number: {channel_key}")
                continue
        
        with self.lock:
            if sender_name:
                if sender_name in self.senders:
                    self.senders[sender_name].set_channels(dmx_channels)
                else:
                    print(f"Sender '{sender_name}' not found")
            else:
                # Set on all active senders
                for sender in self.senders.values():
                    if sender.active:
                        sender.set_channels(dmx_channels)
    
    def send(self, sender_name: str = None):
        """Send data on specific sender or all senders"""
        with self.lock:
            if sender_name:
                if sender_name in self.senders:
                    print(f"Sending DMX data via sender: {sender_name}")
                    self.senders[sender_name].send()
                else:
                    print(f"Sender '{sender_name}' not found")
            else:
                # Send on all active senders
                active_senders = [name for name, sender in self.senders.items() if sender.active]
                print(f"Sending DMX data via {len(active_senders)} active senders: {active_senders}")
                for sender in self.senders.values():
                    if sender.active:
                        sender.send()
    
    def blackout(self, sender_name: str = None):
        """Blackout specific sender or all senders"""
        with self.lock:
            if sender_name:
                if sender_name in self.senders:
                    self.senders[sender_name].blackout()
                else:
                    print(f"Sender '{sender_name}' not found")
            else:
                # Blackout all active senders
                for sender in self.senders.values():
                    if sender.active:
                        sender.blackout()
    
    def stop_all(self):
        """Stop all senders"""
        with self.lock:
            for name, sender in self.senders.items():
                sender.stop()
            self.senders.clear()
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all senders"""
        with self.lock:
            status = {}
            for name, sender in self.senders.items():
                status[name] = {
                    'active': sender.active,
                    'universe': sender.universe_id,
                    'type': sender.__class__.__name__
                }
            return status 
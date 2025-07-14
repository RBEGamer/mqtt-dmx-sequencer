#!/usr/bin/env python3
import argparse
import json
import time
import threading
import paho.mqtt.client as mqtt
import os
from dmx_senders import DMXManager, ArtNetSender, E131Sender
from config_manager import ConfigManager


class MQTTDMXSequencer:
    def __init__(self, config_path, settings_path=None):
        self.config_manager = ConfigManager(settings_path)
        self.config = self.load_config(config_path)
        self.dmx_manager = DMXManager()
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Setup DMX senders from configuration
        self.setup_dmx_senders()
        
        # Connect to MQTT
        self.connect_mqtt()

    def load_config(self, path):
        with open(path, 'r') as f:
            return json.load(f)

    def connect_mqtt(self):
        """Connect to MQTT broker using settings"""
        mqtt_config = self.config_manager.get_mqtt_config()
        
        # Parse MQTT URL
        url = mqtt_config.get('url', 'mqtt://192.168.178.75')
        host, port = self.parse_mqtt_url(url)
        
        # Set MQTT client properties
        client_id = mqtt_config.get('client_id', 'mqtt-dmx-sequencer')
        self.client = mqtt.Client(client_id=client_id)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Set authentication if provided
        username = mqtt_config.get('username')
        password = mqtt_config.get('password')
        if username:
            self.client.username_pw_set(username, password)
        
        # Connect to broker
        try:
            self.client.connect(host, port, keepalive=mqtt_config.get('keepalive', 60))
            print(f"Connecting to MQTT broker: {host}:{port}")
        except Exception as e:
            print(f"Failed to connect to MQTT broker: {e}")

    def parse_mqtt_url(self, url):
        url = url.replace('mqtt://', '')
        parts = url.split(':')
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 1883
        return host, port

    def setup_dmx_senders(self):
        """Setup DMX senders based on configuration"""
        dmx_configs = self.config_manager.get_dmx_configs()
        
        for config in dmx_configs:
            if not self.config_manager.validate_dmx_config(config):
                print(f"Skipping invalid DMX config: {config}")
                continue
            
            sender_type = config.get('type', 'e131')
            name = config.get('name', f"{sender_type}_{config.get('universe', 1)}")
            target_ip = config.get('target', '255.255.255.255')
            universe = config.get('universe', 1)
            
            if sender_type.lower() == 'artnet':
                protocol_config = self.config_manager.get_dmx_protocol_config('artnet')
                port = config.get('port', protocol_config.get('default_port', 6454))
                sender = ArtNetSender(target_ip=target_ip, port=port, universe_id=universe)
            elif sender_type.lower() == 'e131':
                protocol_config = self.config_manager.get_dmx_protocol_config('e131')
                fps = config.get('fps', protocol_config.get('default_fps', 40))
                sender = E131Sender(target_ip=target_ip, universe_id=universe, fps=fps)
            else:
                print(f"Unknown DMX sender type: {sender_type}")
                continue
            
            if self.dmx_manager.add_sender(name, sender):
                print(f"Added DMX sender: {name} ({sender_type})")

    def on_connect(self, client, userdata, flags, rc):
        print("Connected to MQTT broker.")
        
        # Subscribe to sequence topics
        for topic in self.config.get('sequences', {}).keys():
            print(f"Subscribing to topic: {topic}")
            client.subscribe(topic)
        
        # Subscribe to individual channel control topics
        client.subscribe("dmx/set/channel/#")
        print("Subscribed to dmx/set/channel/# for individual channel control")
        
        # Subscribe to scene control topics
        client.subscribe("dmx/scene/#")
        print("Subscribed to dmx/scene/# for scene control")
        
        # Subscribe to DMX sender management topics
        client.subscribe("dmx/sender/#")
        print("Subscribed to dmx/sender/# for sender management")
        
        # Subscribe to configuration management topics
        client.subscribe("dmx/config/#")
        print("Subscribed to dmx/config/# for configuration management")

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        print(f"Received message on topic: {topic} with payload: {payload}")
        
        # Handle individual channel control
        if topic.startswith("dmx/set/channel/"):
            self.handle_channel_control(topic, payload)
        
        # Handle scene control
        elif topic.startswith("dmx/scene/"):
            self.handle_scene_control(topic, payload)
        
        # Handle DMX sender management
        elif topic.startswith("dmx/sender/"):
            self.handle_sender_management(topic, payload)
        
        # Handle configuration management
        elif topic.startswith("dmx/config/"):
            self.handle_config_management(topic, payload)
        
        # Handle sequence playback
        elif topic in self.config.get('sequences', {}):
            self.play_sequence(self.config['sequences'][topic])

    def handle_channel_control(self, topic, payload):
        """Handle individual channel control messages"""
        try:
            # Parse channel number from topic
            channel_str = topic.split("/")[-1]
            channel = int(channel_str)
            value = int(payload)
            
            # Validate channel and value ranges
            if 1 <= channel <= 512 and 0 <= value <= 255:
                self.dmx_manager.set_channel(channel, value)
                self.dmx_manager.send()
                print(f"Set channel {channel} to value {value}")
            else:
                print(f"Invalid channel ({channel}) or value ({value}). Channel must be 1-512, value must be 0-255.")
        except (ValueError, IndexError) as e:
            print(f"Error parsing channel control message: {e}")

    def handle_scene_control(self, topic, payload):
        """Handle scene control messages"""
        try:
            scene_name = topic.split("/")[-1]
            if scene_name in self.config.get('scenes', {}):
                scenes_config = self.config_manager.get_scenes_config()
                default_transition = scenes_config.get('default_transition_time', 0.0)
                transition_time = float(payload) if payload.strip() else default_transition
                self.play_scene(scene_name, transition_time)
            else:
                print(f"Scene '{scene_name}' not found in configuration")
        except (ValueError, IndexError) as e:
            print(f"Error parsing scene control message: {e}")

    def handle_sender_management(self, topic, payload):
        """Handle DMX sender management messages"""
        try:
            parts = topic.split("/")
            if len(parts) < 3:
                return
            
            action = parts[2]
            sender_name = parts[3] if len(parts) > 3 else None
            
            if action == "status":
                status = self.dmx_manager.get_status()
                print(f"DMX Senders Status: {status}")
            
            elif action == "list":
                senders = self.dmx_manager.list_senders()
                print(f"Active DMX Senders: {senders}")
            
            elif action == "blackout":
                self.dmx_manager.blackout(sender_name)
                print(f"Blackout {'all senders' if sender_name is None else f'sender {sender_name}'}")
            
            elif action == "remove" and sender_name:
                if self.dmx_manager.remove_sender(sender_name):
                    print(f"Removed sender: {sender_name}")
                else:
                    print(f"Failed to remove sender: {sender_name}")
            
        except Exception as e:
            print(f"Error handling sender management: {e}")

    def handle_config_management(self, topic, payload):
        """Handle configuration management messages"""
        try:
            parts = topic.split("/")
            if len(parts) < 3:
                return
            
            action = parts[2]
            
            if action == "show":
                self.config_manager.print_current_config()
            
            elif action == "show-full":
                self.config_manager.print_full_config()
            
            elif action == "show-raw":
                self.config_manager.print_raw_config()
            
            elif action == "reload":
                self.config_manager.settings = self.config_manager.load_settings()
                print("Configuration reloaded")
            
            elif action == "save":
                if self.config_manager.save_settings():
                    print("Configuration saved")
                else:
                    print("Failed to save configuration")
            
        except Exception as e:
            print(f"Error handling config management: {e}")

    def play_scene(self, scene_name, transition_time=0.0):
        """Play a scene with optional transition time"""
        if scene_name not in self.config.get('scenes', {}):
            print(f"Scene '{scene_name}' not found")
            return
            
        scene_data = self.config['scenes'][scene_name]
        scenes_config = self.config_manager.get_scenes_config()
        auto_send = scenes_config.get('auto_send', True)
        
        print(f"Playing scene: {scene_name} with transition time: {transition_time}s")
        
        def run():
            # Apply scene data to DMX channels
            channels = {}
            for channel_index, value in enumerate(scene_data):
                if value is not None:  # Skip null values (don't change channel)
                    channel_number = channel_index + 1  # Convert to 1-based channel numbering
                    channels[channel_number] = value
            
            # Set all channels at once
            self.dmx_manager.set_channels(channels)
            if auto_send:
                self.dmx_manager.send()
            print(f"Scene '{scene_name}' applied")
            
        threading.Thread(target=run).start()

    def play_sequence(self, sequence):
        """Play a sequence"""
        sequences_config = self.config_manager.get_sequences_config()
        default_duration = sequences_config.get('default_duration', 1.0)
        auto_play = sequences_config.get('auto_play', True)
        
        def run():
            for step in sequence:
                dmx_data = step.get('dmx', {})
                duration = step.get('duration', default_duration)
                
                # Set channels for this step
                self.dmx_manager.set_channels(dmx_data)
                if auto_play:
                    self.dmx_manager.send()
                
                # Wait for duration
                time.sleep(duration)
            
            print("Sequence finished.")
        
        threading.Thread(target=run).start()

    def run(self):
        """Run the MQTT DMX sequencer"""
        try:
            print("MQTT DMX Sequencer started")
            print(f"Active DMX senders: {self.dmx_manager.list_senders()}")
            self.client.loop_forever()
        except KeyboardInterrupt:
            print("Shutting down...")
            self.dmx_manager.stop_all()
            print("Shutdown complete.")


if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Look for config files in parent directory (project root)
    project_root = os.path.dirname(script_dir)
    
    parser = argparse.ArgumentParser(description='MQTT DMX Sequencer with configuration file support')
    parser.add_argument('--config-dir', help='Directory containing settings.json and config.json files', default=project_root)
    parser.add_argument('--show-config', action='store_true', help='Show current configuration and exit')
    parser.add_argument('--print-config', action='store_true', help='Print full configuration details on startup')
    
    args = parser.parse_args()
    
    # Set up file paths
    settings_path = os.path.join(args.config_dir, 'settings.json')
    config_path = os.path.join(args.config_dir, 'config.json')
    
    # Create config manager with optional printing
    config_manager = ConfigManager(settings_path, print_on_load=args.print_config)
    
    # Show configuration if requested
    if args.show_config:
        config_manager.print_current_config()
        exit(0)
    
    # Create and run sequencer
    sequencer = MQTTDMXSequencer(
        config_path=config_path,
        settings_path=settings_path
    )
    sequencer.run()
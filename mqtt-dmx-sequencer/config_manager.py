#!/usr/bin/env python3
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path


class ConfigManager:
    """Manages application configuration from settings.json"""
    
    def __init__(self, settings_path: str = None, print_on_load: bool = False):
        if settings_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            # Look for settings.json in parent directory (project root)
            project_root = os.path.dirname(script_dir)
            settings_path = os.path.join(project_root, 'settings.json')
        
        self.settings_path = settings_path
        self.print_on_load = print_on_load
        self.settings = self.load_settings()
        
        # Print configuration if requested
        if self.print_on_load:
            self.print_full_config()
    
    def load_settings(self) -> Dict[str, Any]:
        """Load settings from JSON file"""
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, 'r') as f:
                    settings = json.load(f)
                print(f"Loaded settings from {self.settings_path}")
                return settings
            else:
                print(f"Settings file not found at {self.settings_path}, using defaults")
                return self.get_default_settings()
        except Exception as e:
            print(f"Error loading settings: {e}, using defaults")
            return self.get_default_settings()
    
    def save_settings(self) -> bool:
        """Save current settings to JSON file"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
            
            with open(self.settings_path, 'w') as f:
                json.dump(self.settings, f, indent=2)
            print(f"Settings saved to {self.settings_path}")
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False
    
    def get_default_settings(self) -> Dict[str, Any]:
        """Get default settings"""
        return {
            "mqtt": {
                "url": "mqtt://192.168.178.75",
                "port": 1883,
                "username": "",
                "password": "",
                "client_id": "mqtt-dmx-sequencer",
                "keepalive": 60,
                "clean_session": True
            },
            "dmx": {
                "default_configs": [
                    {
                        "type": "e131",
                        "name": "main",
                        "target": "255.255.255.255",
                        "universe": 1,
                        "fps": 40
                    }
                ],
                "artnet": {
                    "default_port": 6454,
                    "refresh_rate": 0.1
                },
                "e131": {
                    "default_fps": 40,
                    "multicast": True
                }
            },
            "logging": {
                "level": "info",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            },
            "scenes": {
                "default_transition_time": 0.0,
                "auto_send": True
            },
            "sequences": {
                "default_duration": 1.0,
                "auto_play": True
            }
        }
    
    def get_mqtt_config(self) -> Dict[str, Any]:
        """Get MQTT configuration"""
        return self.settings.get("mqtt", {})
    
    def get_dmx_configs(self) -> List[Dict[str, Any]]:
        """Get DMX sender configurations"""
        return self.settings.get("dmx", {}).get("default_configs", [])
    
    def get_dmx_protocol_config(self, protocol: str) -> Dict[str, Any]:
        """Get configuration for specific DMX protocol"""
        dmx_settings = self.settings.get("dmx", {})
        if protocol.lower() == "artnet":
            return dmx_settings.get("artnet", {})
        elif protocol.lower() == "e131":
            return dmx_settings.get("e131", {})
        return {}
    
    def get_logging_config(self) -> Dict[str, Any]:
        """Get logging configuration"""
        return self.settings.get("logging", {})
    
    def get_scenes_config(self) -> Dict[str, Any]:
        """Get scenes configuration"""
        return self.settings.get("scenes", {})
    
    def get_sequences_config(self) -> Dict[str, Any]:
        """Get sequences configuration"""
        return self.settings.get("sequences", {})
    
    def update_mqtt_config(self, **kwargs) -> bool:
        """Update MQTT configuration"""
        mqtt_config = self.settings.get("mqtt", {})
        mqtt_config.update(kwargs)
        self.settings["mqtt"] = mqtt_config
        return self.save_settings()
    
    def update_dmx_configs(self, configs: List[Dict[str, Any]]) -> bool:
        """Update DMX sender configurations"""
        dmx_settings = self.settings.get("dmx", {})
        dmx_settings["default_configs"] = configs
        self.settings["dmx"] = dmx_settings
        return self.save_settings()
    
    def add_dmx_config(self, config: Dict[str, Any]) -> bool:
        """Add a new DMX sender configuration"""
        configs = self.get_dmx_configs()
        configs.append(config)
        return self.update_dmx_configs(configs)
    
    def remove_dmx_config(self, name: str) -> bool:
        """Remove a DMX sender configuration by name"""
        configs = self.get_dmx_configs()
        configs = [config for config in configs if config.get("name") != name]
        return self.update_dmx_configs(configs)
    
    def get_dmx_config_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get DMX configuration by name"""
        configs = self.get_dmx_configs()
        for config in configs:
            if config.get("name") == name:
                return config
        return None
    
    def validate_dmx_config(self, config: Dict[str, Any]) -> bool:
        """Validate DMX configuration"""
        required_fields = ["type", "name"]
        for field in required_fields:
            if field not in config:
                print(f"Missing required field: {field}")
                return False
        
        if config["type"] not in ["artnet", "e131"]:
            print(f"Invalid DMX type: {config['type']}")
            return False
        
        if not config.get("name"):
            print("DMX sender name cannot be empty")
            return False
        
        return True
    
    def merge_with_command_line(self, cmd_args: Dict[str, Any]) -> Dict[str, Any]:
        """Merge command line arguments with settings"""
        merged = self.settings.copy()
        
        # Override MQTT settings if provided
        if cmd_args.get("mqtt_url"):
            merged["mqtt"]["url"] = cmd_args["mqtt_url"]
        
        # Override DMX configs if provided
        if cmd_args.get("dmx_configs"):
            merged["dmx"]["default_configs"] = cmd_args["dmx_configs"]
        
        return merged
    
    def print_current_config(self):
        """Print current configuration"""
        print("Current Configuration:")
        print("=" * 50)
        
        # MQTT Configuration
        mqtt_config = self.get_mqtt_config()
        print(f"MQTT URL: {mqtt_config.get('url', 'Not set')}")
        print(f"MQTT Port: {mqtt_config.get('port', 'Not set')}")
        print(f"MQTT Client ID: {mqtt_config.get('client_id', 'Not set')}")
        
        # DMX Configurations
        dmx_configs = self.get_dmx_configs()
        print(f"\nDMX Senders ({len(dmx_configs)}):")
        for i, config in enumerate(dmx_configs, 1):
            print(f"  {i}. {config.get('name', 'Unnamed')} ({config.get('type', 'Unknown')})")
            print(f"     Target: {config.get('target', 'Not set')}")
            print(f"     Universe: {config.get('universe', 'Not set')}")
        
        # Other settings
        logging_config = self.get_logging_config()
        print(f"\nLogging Level: {logging_config.get('level', 'Not set')}")
        
        scenes_config = self.get_scenes_config()
        print(f"Default Transition Time: {scenes_config.get('default_transition_time', 'Not set')}s")
        
        print("=" * 50)
    
    def print_full_config(self):
        """Print the complete loaded configuration in detail"""
        print("Full Configuration Details:")
        print("=" * 60)
        
        # MQTT Configuration
        mqtt_config = self.get_mqtt_config()
        print("MQTT Configuration:")
        print(f"  URL: {mqtt_config.get('url', 'Not set')}")
        print(f"  Port: {mqtt_config.get('port', 'Not set')}")
        print(f"  Username: {mqtt_config.get('username', 'Not set')}")
        print(f"  Password: {'*' * len(mqtt_config.get('password', '')) if mqtt_config.get('password') else 'Not set'}")
        print(f"  Client ID: {mqtt_config.get('client_id', 'Not set')}")
        print(f"  Keepalive: {mqtt_config.get('keepalive', 'Not set')}")
        print(f"  Clean Session: {mqtt_config.get('clean_session', 'Not set')}")
        
        # DMX Configuration
        dmx_configs = self.get_dmx_configs()
        print(f"\nDMX Senders ({len(dmx_configs)}):")
        for i, config in enumerate(dmx_configs, 1):
            print(f"  {i}. {config.get('name', 'Unnamed')} ({config.get('type', 'Unknown')})")
            print(f"     Target: {config.get('target', 'Not set')}")
            print(f"     Universe: {config.get('universe', 'Not set')}")
            if config.get('type') == 'e131':
                print(f"     FPS: {config.get('fps', 'Not set')}")
            elif config.get('type') == 'artnet':
                print(f"     Port: {config.get('port', 'Not set')}")
        
        # DMX Protocol Settings
        dmx_settings = self.settings.get("dmx", {})
        print("\nDMX Protocol Settings:")
        
        artnet_config = dmx_settings.get("artnet", {})
        print("  Art-Net:")
        print(f"    Default Port: {artnet_config.get('default_port', 'Not set')}")
        print(f"    Refresh Rate: {artnet_config.get('refresh_rate', 'Not set')}")
        
        e131_config = dmx_settings.get("e131", {})
        print("  E1.31:")
        print(f"    Default FPS: {e131_config.get('default_fps', 'Not set')}")
        print(f"    Multicast: {e131_config.get('multicast', 'Not set')}")
        
        # Logging Configuration
        logging_config = self.get_logging_config()
        print("\nLogging Configuration:")
        print(f"  Level: {logging_config.get('level', 'Not set')}")
        print(f"  Format: {logging_config.get('format', 'Not set')}")
        
        # Scenes Configuration
        scenes_config = self.get_scenes_config()
        print("\nScenes Configuration:")
        print(f"  Default Transition Time: {scenes_config.get('default_transition_time', 'Not set')}s")
        print(f"  Auto Send: {scenes_config.get('auto_send', 'Not set')}")
        
        # Sequences Configuration
        sequences_config = self.get_sequences_config()
        print("\nSequences Configuration:")
        print(f"  Default Duration: {sequences_config.get('default_duration', 'Not set')}s")
        print(f"  Auto Play: {sequences_config.get('auto_play', 'Not set')}")
        
        print("=" * 60)
    
    def print_raw_config(self):
        """Print the raw JSON configuration"""
        print("Raw Configuration (JSON):")
        print("=" * 40)
        print(json.dumps(self.settings, indent=2))
        print("=" * 40) 
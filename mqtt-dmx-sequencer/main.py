#!/usr/bin/env python3
import argparse
import json
import time
import threading
import paho.mqtt.client as mqtt
import os
from dmx_senders import DMXManager, ArtNetSender, E131Sender
from config_manager import ConfigManager

# Flask imports for web server
try:
    from flask import Flask, request, jsonify, send_from_directory
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    print("Warning: Flask not available. Web server functionality will be disabled.")


class MQTTDMXSequencer:
    def __init__(self, config_path, settings_path=None, enable_web_server=None, web_port=None):
        self.config_manager = ConfigManager(settings_path)
        self.config = self.load_config(config_path)
        self.dmx_manager = DMXManager()
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        # Web server settings from config or command line
        web_config = self.config_manager.get_web_server_config()
        self.enable_web_server = enable_web_server if enable_web_server is not None else web_config.get('enabled', True)
        self.web_port = web_port if web_port is not None else web_config.get('port', 5000)
        self.web_host = web_config.get('host', '0.0.0.0')
        self.web_debug = web_config.get('debug', False)
        
        # Only enable if Flask is available
        self.enable_web_server = self.enable_web_server and FLASK_AVAILABLE
        self.flask_app = None
        self.web_thread = None
        
        # Setup DMX senders from configuration
        self.setup_dmx_senders()
        
        # Connect to MQTT
        self.connect_mqtt()
        
        # Setup web server if enabled
        if self.enable_web_server:
            self.setup_web_server()

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

    def setup_web_server(self):
        """Setup Flask web server"""
        if not FLASK_AVAILABLE:
            print("Flask not available, web server disabled")
            return
            
        self.flask_app = Flask(__name__, static_folder='static')
        self.setup_flask_routes()
        
        def run_flask():
            self.flask_app.run(host=self.web_host, port=self.web_port, debug=self.web_debug, use_reloader=False)
        
        self.web_thread = threading.Thread(target=run_flask, daemon=True)
        self.web_thread.start()
        print(f"Web server started on http://localhost:{self.web_port}")

    def setup_flask_routes(self):
        """Setup Flask routes for the web API"""
        
        @self.flask_app.route('/')
        def index():
            """Serve the main web interface"""
            return send_from_directory('static', 'index.html')

        @self.flask_app.route('/<path:filename>')
        def static_files(filename):
            """Serve static files"""
            return send_from_directory('static', filename)

        @self.flask_app.route('/api/health', methods=['GET'])
        def health_check():
            """Health check endpoint"""
            return jsonify({
                "status": "healthy",
                "service": "mqtt-dmx-sequencer-api",
                "version": "1.0.0"
            })

        @self.flask_app.route('/api/config', methods=['GET'])
        def get_config():
            """Get current configuration"""
            try:
                return jsonify({
                    "success": True,
                    "data": self.config
                })
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/scenes', methods=['GET'])
        def get_scenes():
            """Get all scenes"""
            try:
                scenes = self.config.get('scenes', {})
                # Convert to list format for frontend
                scenes_list = []
                for name, channels in scenes.items():
                    scenes_list.append({
                        'id': name,
                        'name': name,
                        'channels': channels,
                        'description': f"Scene with {len([c for c in channels if c > 0])} active channels"
                    })
                return jsonify(scenes_list)
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/scenes', methods=['POST'])
        def create_scene():
            """Create a new scene"""
            try:
                data = request.get_json()
                
                if not data or 'name' not in data or 'channels' not in data:
                    return jsonify({
                        "success": False,
                        "error": "Missing required fields: name and channels"
                    }), 400
                
                scene_name = data['name']
                channels = data['channels']
                
                # Validate channels
                if not isinstance(channels, list):
                    return jsonify({
                        "success": False,
                        "error": "Channels must be a list"
                    }), 400
                
                # Validate channel values
                for i, value in enumerate(channels):
                    if value is not None and (not isinstance(value, int) or value < 0 or value > 255):
                        return jsonify({
                            "success": False,
                            "error": f"Channel {i+1} value must be null or 0-255, got {value}"
                        }), 400
                
                self.config['scenes'][scene_name] = channels
                self.save_config()
                
                return jsonify({
                    "success": True,
                    "message": f"Scene '{scene_name}' created successfully"
                }), 201
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/scenes/<scene_id>', methods=['PUT'])
        def update_scene(scene_id):
            """Update an existing scene"""
            try:
                data = request.get_json()
                
                if not data or 'channels' not in data:
                    return jsonify({
                        "success": False,
                        "error": "Missing required field: channels"
                    }), 400
                
                channels = data['channels']
                
                # Validate channels
                if not isinstance(channels, list):
                    return jsonify({
                        "success": False,
                        "error": "Channels must be a list"
                    }), 400
                
                # Validate channel values
                for i, value in enumerate(channels):
                    if value is not None and (not isinstance(value, int) or value < 0 or value > 255):
                        return jsonify({
                            "success": False,
                            "error": f"Channel {i+1} value must be null or 0-255, got {value}"
                        }), 400
                
                if scene_id not in self.config.get('scenes', {}):
                    return jsonify({
                        "success": False,
                        "error": f"Scene '{scene_id}' not found"
                    }), 404
                
                self.config['scenes'][scene_id] = channels
                self.save_config()
                
                return jsonify({
                    "success": True,
                    "message": f"Scene '{scene_id}' updated successfully"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/scenes/<scene_id>', methods=['DELETE'])
        def delete_scene(scene_id):
            """Delete a scene"""
            try:
                if scene_id not in self.config.get('scenes', {}):
                    return jsonify({
                        "success": False,
                        "error": f"Scene '{scene_id}' not found"
                    }), 404
                
                del self.config['scenes'][scene_id]
                self.save_config()
                
                return jsonify({
                    "success": True,
                    "message": f"Scene '{scene_id}' deleted successfully"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/scenes/<scene_id>/play', methods=['POST'])
        def play_scene_api(scene_id):
            """Play a scene via API"""
            try:
                if scene_id not in self.config.get('scenes', {}):
                    return jsonify({
                        "success": False,
                        "error": f"Scene '{scene_id}' not found"
                    }), 404
                
                self.play_scene(scene_id)
                
                return jsonify({
                    "success": True,
                    "message": f"Scene '{scene_id}' triggered"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/sequences', methods=['GET'])
        def get_sequences():
            """Get all sequences"""
            try:
                sequences = self.config.get('sequences', {})
                # Convert to list format for frontend
                sequences_list = []
                for name, steps in sequences.items():
                    sequences_list.append({
                        'id': name,
                        'name': name,
                        'steps': steps,
                        'description': f"Sequence with {len(steps)} steps"
                    })
                return jsonify(sequences_list)
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/sequences', methods=['POST'])
        def create_sequence():
            """Create a new sequence"""
            try:
                data = request.get_json()
                
                if not data or 'name' not in data or 'steps' not in data:
                    return jsonify({
                        "success": False,
                        "error": "Missing required fields: name and steps"
                    }), 400
                
                sequence_name = data['name']
                steps = data['steps']
                
                # Validate steps
                if not isinstance(steps, list):
                    return jsonify({
                        "success": False,
                        "error": "Steps must be a list"
                    }), 400
                
                self.config['sequences'][sequence_name] = steps
                self.save_config()
                
                return jsonify({
                    "success": True,
                    "message": f"Sequence '{sequence_name}' created successfully"
                }), 201
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/sequences/<sequence_id>', methods=['PUT'])
        def update_sequence(sequence_id):
            """Update an existing sequence"""
            try:
                data = request.get_json()
                
                if not data or 'steps' not in data:
                    return jsonify({
                        "success": False,
                        "error": "Missing required field: steps"
                    }), 400
                
                steps = data['steps']
                
                # Validate steps
                if not isinstance(steps, list):
                    return jsonify({
                        "success": False,
                        "error": "Steps must be a list"
                    }), 400
                
                if sequence_id not in self.config.get('sequences', {}):
                    return jsonify({
                        "success": False,
                        "error": f"Sequence '{sequence_id}' not found"
                    }), 404
                
                self.config['sequences'][sequence_id] = steps
                self.save_config()
                
                return jsonify({
                    "success": True,
                    "message": f"Sequence '{sequence_id}' updated successfully"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/sequences/<sequence_id>', methods=['DELETE'])
        def delete_sequence(sequence_id):
            """Delete a sequence"""
            try:
                if sequence_id not in self.config.get('sequences', {}):
                    return jsonify({
                        "success": False,
                        "error": f"Sequence '{sequence_id}' not found"
                    }), 404
                
                del self.config['sequences'][sequence_id]
                self.save_config()
                
                return jsonify({
                    "success": True,
                    "message": f"Sequence '{sequence_id}' deleted successfully"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/sequences/<sequence_id>/play', methods=['POST'])
        def play_sequence_api(sequence_id):
            """Play a sequence via API"""
            try:
                if sequence_id not in self.config.get('sequences', {}):
                    return jsonify({
                        "success": False,
                        "error": f"Sequence '{sequence_id}' not found"
                    }), 404
                
                self.play_sequence(self.config['sequences'][sequence_id])
                
                return jsonify({
                    "success": True,
                    "message": f"Sequence '{sequence_id}' triggered"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/dmx/channel/<int:channel>', methods=['POST'])
        def set_channel(channel):
            """Set a single DMX channel"""
            try:
                data = request.get_json()
                
                if not data or 'value' not in data:
                    return jsonify({
                        "success": False,
                        "error": "Missing required field: value"
                    }), 400
                
                value = data['value']
                
                # Validate channel and value
                if not isinstance(channel, int) or channel < 1 or channel > 512:
                    return jsonify({
                        "success": False,
                        "error": "Channel must be 1-512"
                    }), 400
                
                if not isinstance(value, int) or value < 0 or value > 255:
                    return jsonify({
                        "success": False,
                        "error": "Value must be 0-255"
                    }), 400
                
                self.dmx_manager.set_channel(channel, value)
                self.dmx_manager.send()
                
                return jsonify({
                    "success": True,
                    "message": f"Channel {channel} set to {value}"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/dmx/all', methods=['POST'])
        def set_all_channels():
            """Set all DMX channels"""
            try:
                data = request.get_json()
                
                if not data or 'channels' not in data:
                    return jsonify({
                        "success": False,
                        "error": "Missing required field: channels"
                    }), 400
                
                channels = data['channels']
                
                # Validate channels
                if not isinstance(channels, list):
                    return jsonify({
                        "success": False,
                        "error": "Channels must be a list"
                    }), 400
                
                # Set all channels
                for i, value in enumerate(channels):
                    if 0 <= value <= 255:
                        self.dmx_manager.set_channel(i + 1, value)
                
                self.dmx_manager.send()
                
                return jsonify({
                    "success": True,
                    "message": f"Set {len(channels)} channels"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/dmx/blackout', methods=['POST'])
        def blackout():
            """Blackout all DMX channels (set to 0)"""
            try:
                self.dmx_manager.blackout()
                
                return jsonify({
                    "success": True,
                    "message": "Blackout activated - all channels set to 0"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

    def save_config(self):
        """Save current configuration to file"""
        try:
            config_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(config_dir, 'config.json')
            
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False

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
    parser.add_argument('--disable-web-server', action='store_true', help='Disable the Flask web server')
    parser.add_argument('--web-port', type=int, help='Port for the Flask web server (overrides settings.json)')
    
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
        settings_path=settings_path,
        enable_web_server=not args.disable_web_server,
        web_port=args.web_port
    )
    sequencer.run()
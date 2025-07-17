#!/usr/bin/env python3
import argparse
import json
import time
import threading
import paho.mqtt.client as mqtt
import os
import signal
import sys
import math
import re
from dmx_senders import DMXManager, ArtNetSender, E131Sender, TestSender
from config_manager import ConfigManager

# Flask imports for web server
try:
    from flask import Flask, request, jsonify, send_from_directory
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    print("Warning: Flask not available. Web server functionality will be disabled.")

class ProgrammableSceneEvaluator:
    """Safe mathematical expression evaluator for programmable scenes"""
    
    def __init__(self):
        # Define safe mathematical functions and constants
        self.safe_globals = {
            'abs': abs,
            'round': round,
            'min': min,
            'max': max,
            'sin': math.sin,
            'cos': math.cos,
            'tan': math.tan,
            'pi': math.pi,
            'e': math.e,
            'sqrt': math.sqrt,
            'pow': pow,
            'floor': math.floor,
            'ceil': math.ceil,
            'log': math.log,
            'exp': math.exp,
            'mod': lambda x, y: x % y,
            'clamp': lambda x, min_val, max_val: max(min_val, min(max_val, x)),
            'hsv_to_rgb': self.hsv_to_rgb,
            'hsv_to_rgb_r': self.hsv_to_rgb_r,
            'hsv_to_rgb_g': self.hsv_to_rgb_g,
            'hsv_to_rgb_b': self.hsv_to_rgb_b
        }
    
    def hsv_to_rgb(self, h, s, v):
        """Convert HSV to RGB values (0-255)"""
        h = h % 360
        s = max(0, min(1, s))
        v = max(0, min(1, v))
        
        c = v * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = v - c
        
        if 0 <= h < 60:
            r, g, b = c, x, 0
        elif 60 <= h < 120:
            r, g, b = x, c, 0
        elif 120 <= h < 180:
            r, g, b = 0, c, x
        elif 180 <= h < 240:
            r, g, b = 0, x, c
        elif 240 <= h < 300:
            r, g, b = x, 0, c
        else:  # 300 <= h < 360
            r, g, b = c, 0, x
        
        return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))
    
    def hsv_to_rgb_r(self, h, s, v):
        """Convert HSV to RGB red channel value (0-255)"""
        rgb = self.hsv_to_rgb(h, s, v)
        return rgb[0]
    
    def hsv_to_rgb_g(self, h, s, v):
        """Convert HSV to RGB green channel value (0-255)"""
        rgb = self.hsv_to_rgb(h, s, v)
        return rgb[1]
    
    def hsv_to_rgb_b(self, h, s, v):
        """Convert HSV to RGB blue channel value (0-255)"""
        rgb = self.hsv_to_rgb(h, s, v)
        return rgb[2]
    
    def evaluate_expression(self, expression, time_seconds, channel):
        """Evaluate a mathematical expression safely"""
        try:
            import re
            
            # Replace variables using regex to avoid corrupting function names
            expression = re.sub(r'\btime\b', str(time_seconds), expression)
            expression = re.sub(r'\bt\b', str(time_seconds), expression)
            expression = re.sub(r'\bchannel\b', str(channel), expression)
            expression = re.sub(r'\bch\b', str(channel), expression)
            
            # Create local variables
            locals_dict = {
                'time': time_seconds,
                't': time_seconds,
                'channel': channel,
                'ch': channel
            }
            
            # Evaluate the expression
            result = eval(expression, {"__builtins__": {}}, {**self.safe_globals, **locals_dict})
            
            # Handle tuple results (from hsv_to_rgb)
            if isinstance(result, tuple):
                # For RGB channels, return the appropriate component
                if channel == 7:  # Red channel
                    return max(0, min(255, int(round(result[0]))))
                elif channel == 8:  # Green channel
                    return max(0, min(255, int(round(result[1]))))
                elif channel == 9:  # Blue channel
                    return max(0, min(255, int(round(result[2]))))
                else:
                    return 0
            
            # Clamp result to 0-255 range for DMX
            return max(0, min(255, int(round(result))))
            
        except Exception as e:
            print(f"Error evaluating expression '{expression}': {e}")
            return 0

class MQTTDMXSequencer:
    def __init__(self, config_path, settings_path=None, enable_web_server=None, web_port=None):
        self.config_manager = ConfigManager(settings_path)
        self.config = self.load_config(config_path)
        self.dmx_manager = DMXManager()
        
        # MQTT connection state
        self.client = None
        self.mqtt_connected = False
        self.subscriptions_done = False
        self.mqtt_reconnect_attempts = 0
        self.max_mqtt_reconnect_attempts = 3
        self.current_mqtt_subscriptions = set()  # Track current subscriptions
        
        # Enhanced playback state management
        self.current_sequence_playback = None
        self.current_step_index = 0
        self.current_step_data = None
        self.current_scene_playback = None
        self.current_programmable_scene_playback = None
        self.playback_start_time = None
        self.playback_paused = False
        self.playback_pause_time = None
        self.total_pause_time = 0
        
        # MQTT channel update tracking
        self.last_mqtt_channel_update = None
        
        # Autostart management
        self.autostart_config = self.config.get('autostart', {})
        self.current_autostart = None
        self.autostart_timer = None
        
        # Fallback management
        self.fallback_config = self.config.get('fallback', {})
        self.fallback_timer = None
        print(f"Loaded fallback configuration: {self.fallback_config}")
        
        # Programmable scenes
        self.programmable_scenes_config = self.config_manager.settings.get('programmable_scenes', {'enabled': True, 'default_duration': 10.0, 'default_fps': 30})
        self.programmable_scenes = self.config.get('programmable_scenes', {})
        self.programmable_scene_evaluator = ProgrammableSceneEvaluator()
        
        # Web server settings from config or command line
        web_config = self.config_manager.get_web_server_config()
        self.enable_web_server = enable_web_server if enable_web_server is not None else web_config.get('enabled', True)
        self.web_port = web_port if web_port is not None else web_config.get('port', 5001)
        self.web_host = web_config.get('host', '0.0.0.0')
        self.web_debug = web_config.get('debug', False)
        
        # Shutdown flag
        self.shutdown_requested = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Setup DMX senders
        self.setup_dmx_senders()
        
        # Setup MQTT connection
        self.connect_mqtt()
        
        # Setup web server if enabled
        if self.enable_web_server and FLASK_AVAILABLE:
            self.setup_web_server()
        elif self.enable_web_server and not FLASK_AVAILABLE:
            print("Warning: Web server requested but Flask not available")
        
        self.dmx_retransmission_thread = None
        self.dmx_retransmission_stop = threading.Event()
        self.dmx_retransmission_settings = self.config_manager.settings.get('dmx_retransmission', {'enabled': False, 'interval': 5.0})
        if self.dmx_retransmission_settings.get('enabled', False):
            self.start_dmx_retransmission()

        self.dmx_followers_settings = self.config_manager.settings.get('dmx_followers', {'enabled': False, 'mappings': {}})

    def load_config(self, path):
        print(f"Loading config from: {path}")
        with open(path, 'r') as f:
            config = json.load(f)
        print(f"Config loaded successfully from: {path}")
        return config

    def connect_mqtt(self):
        """Connect to MQTT broker using settings"""
        mqtt_config = self.config_manager.get_mqtt_config()
        
        # Parse MQTT URL
        url = mqtt_config.get('url', 'mqtt://192.168.178.75')
        host, port = self.parse_mqtt_url(url)
        
        # Set MQTT client properties
        client_id = mqtt_config.get('client_id', 'mqtt-dmx-sequencer')
        self.client = mqtt.Client(client_id=client_id, clean_session=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        
        # Set authentication if provided
        username = mqtt_config.get('username')
        password = mqtt_config.get('password')
        if username:
            self.client.username_pw_set(username, password)
        
        # Connect to broker
        try:
            print(f"Connecting to MQTT broker: {host}:{port}")
            self.client.connect(host, port, keepalive=mqtt_config.get('keepalive', 60))
            print("MQTT connection established successfully")
        except Exception as e:
            print(f"Failed to connect to MQTT broker: {e}")
            print("Continuing without MQTT functionality")
            self.client = None

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
            elif sender_type.lower() == 'test':
                sender = TestSender(universe_id=universe)
            else:
                print(f"Unknown DMX sender type: {sender_type}")
                continue
            
            # Try to add the sender, fall back to test mode if it fails
            sender_added = False
            if self.dmx_manager.add_sender(name, sender):
                print(f"Added DMX sender: {name} ({sender_type})")
                sender_added = True
            else:
                print(f"Failed to add {sender_type} sender, falling back to test mode")
                test_sender = TestSender(universe_id=universe)
                test_name = f"test_{name}"
                if self.dmx_manager.add_sender(test_name, test_sender):
                    print(f"Added test DMX sender: {test_name}")
                    sender_added = True
        
        # If no senders were added, add a default test sender
        if not self.dmx_manager.list_senders():
            print("No DMX senders configured, adding default test sender")
            test_sender = TestSender(universe_id=1)
            if self.dmx_manager.add_sender("default_test", test_sender):
                print("Added default test DMX sender")

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
                config = self.config.copy() if hasattr(self, 'config') else {}
                # Add frontend_mqtt_passthrough from settings
                passthrough = self.config_manager.settings.get('frontend_mqtt_passthrough', False)
                config['frontend_mqtt_passthrough'] = passthrough
                return jsonify({
                    "success": True,
                    "data": config
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
                
                # Refresh MQTT subscriptions
                self.refresh_mqtt_subscriptions()
                
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
                
                # Refresh MQTT subscriptions
                self.refresh_mqtt_subscriptions()
                
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
                
                # Refresh MQTT subscriptions
                self.refresh_mqtt_subscriptions()
                
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
                for name, sequence_data in sequences.items():
                    # Handle both old format (just steps) and new format (with metadata)
                    if isinstance(sequence_data, list):
                        # Old format - just steps array
                        steps = sequence_data
                        description = f"Sequence with {len(steps)} steps"
                        loop = False
                    else:
                        # New format - with metadata
                        steps = sequence_data.get('steps', [])
                        description = sequence_data.get('description', f"Sequence with {len(steps)} steps")
                        loop = sequence_data.get('loop', False)
                    
                    sequences_list.append({
                        'id': name,
                        'name': name,
                        'steps': steps,
                        'description': description,
                        'loop': loop
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
                description = data.get('description', '')
                loop = data.get('loop', False)
                
                # Validate steps
                if not isinstance(steps, list):
                    return jsonify({
                        "success": False,
                        "error": "Steps must be a list"
                    }), 400
                
                # Store sequence with metadata
                self.config['sequences'][sequence_name] = {
                    'steps': steps,
                    'description': description,
                    'loop': loop
                }
                self.save_config()
                
                # Refresh MQTT subscriptions
                self.refresh_mqtt_subscriptions()
                
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
                description = data.get('description', '')
                loop = data.get('loop', False)
                
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
                
                # Update sequence with metadata
                self.config['sequences'][sequence_id] = {
                    'steps': steps,
                    'description': description,
                    'loop': loop
                }
                self.save_config()
                
                # Refresh MQTT subscriptions
                self.refresh_mqtt_subscriptions()
                
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
                
                # Refresh MQTT subscriptions
                self.refresh_mqtt_subscriptions()
                
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
                
                sequence_data = self.config['sequences'][sequence_id]
                
                # Handle both old format (just steps) and new format (with metadata)
                if isinstance(sequence_data, list):
                    # Old format - just steps array
                    steps = sequence_data
                    loop = False
                else:
                    # New format - with metadata
                    steps = sequence_data.get('steps', [])
                    loop = sequence_data.get('loop', False)
                
                self.play_sequence(steps, loop)
                
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
                
                # Track channel update for frontend sync
                self.last_mqtt_channel_update = {'channel': channel, 'value': value}
                
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
                
                # Track channel updates for frontend sync (track the last non-zero channel)
                for i, value in enumerate(channels):
                    if 0 <= value <= 255 and value > 0:
                        self.last_mqtt_channel_update = {'channel': i + 1, 'value': value}
                
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

        @self.flask_app.route('/api/autostart', methods=['GET'])
        def get_autostart():
            """Get current autostart configuration"""
            try:
                return jsonify({
                    "success": True,
                    "data": {
                        "current": self.current_autostart,
                        "config": self.autostart_config
                    }
                })
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/autostart', methods=['POST'])
        def set_autostart():
            """Set autostart configuration"""
            try:
                data = request.get_json()
                
                if not data or 'type' not in data or 'id' not in data:
                    return jsonify({
                        "success": False,
                        "error": "Missing required fields: type and id"
                    }), 400
                
                autostart_type = data['type']  # 'scene' or 'sequence'
                autostart_id = data['id']
                enabled = data.get('enabled', True)
                
                if enabled:
                    # Disable any existing autostart
                    self.disable_current_autostart()
                    
                    # Set new autostart
                    self.autostart_config = {
                        'type': autostart_type,
                        'id': autostart_id,
                        'enabled': True
                    }
                    self.current_autostart = autostart_id
                    
                    # Start the autostart
                    self.start_autostart()
                else:
                    # Disable autostart
                    self.disable_current_autostart()
                    self.autostart_config = {}
                    self.current_autostart = None
                
                # Save to config
                self.config['autostart'] = self.autostart_config
                self.save_config()
                
                return jsonify({
                    "success": True,
                    "message": f"Autostart {'enabled' if enabled else 'disabled'} for {autostart_type} '{autostart_id}'"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/autostart', methods=['DELETE'])
        def disable_autostart():
            """Disable current autostart"""
            try:
                self.disable_current_autostart()
                self.autostart_config = {}
                self.current_autostart = None
                
                # Save to config
                self.config['autostart'] = self.autostart_config
                self.save_config()
                
                return jsonify({
                    "success": True,
                    "message": "Autostart disabled"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/fallback', methods=['GET'])
        def get_fallback():
            """Get current fallback configuration"""
            try:
                return jsonify({
                    "success": True,
                    "data": {
                        "current": self.current_autostart, # Fallback uses autostart logic
                        "config": self.fallback_config
                    }
                })
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/fallback', methods=['POST'])
        def set_fallback():
            """Set fallback configuration"""
            try:
                data = request.get_json()
                
                # Handle scene fallback configuration
                if 'scene_fallback' in data:
                    scene_fallback_data = data['scene_fallback']
                    enabled = scene_fallback_data.get('enabled', False)
                    scene_id = scene_fallback_data.get('scene_id', 'blackout')
                    delay = scene_fallback_data.get('delay', 1.0)
                    
                    print(f"Setting scene fallback: enabled={enabled}, scene_id={scene_id}, delay={delay}")
                    
                    # Update scene fallback configuration
                    if 'scene_fallback' not in self.fallback_config:
                        self.fallback_config['scene_fallback'] = {}
                    
                    self.fallback_config['scene_fallback'] = {
                        'enabled': enabled,
                        'scene_id': scene_id,
                        'delay': delay
                    }
                    
                    print(f"Updated scene fallback config: {self.fallback_config}")
                    
                    # Save to config
                    self.config['fallback'] = self.fallback_config
                    self.save_config()
                    
                    return jsonify({
                        "success": True,
                        "message": f"Scene fallback {'enabled' if enabled else 'disabled'} for scene '{scene_id}' with {delay}s delay"
                    })
                
                # Handle global scene fallback configuration
                if 'global_scene_fallback' in data:
                    global_data = data['global_scene_fallback']
                    enabled = global_data.get('enabled', False)
                    scene_id = global_data.get('scene_id', 'blackout')
                    delay = global_data.get('delay', 1.0)
                    
                    # Update scene fallback configuration
                    if 'scene_fallback' not in self.fallback_config:
                        self.fallback_config['scene_fallback'] = {}
                    
                    self.fallback_config['scene_fallback'] = {
                        'enabled': enabled,
                        'scene_id': scene_id,
                        'delay': delay
                    }
                    
                    # Save to config
                    self.config['fallback'] = self.fallback_config
                    self.save_config()
                    
                    return jsonify({
                        "success": True,
                        "message": f"Global scene fallback {'enabled' if enabled else 'disabled'} for scene '{scene_id}' with {delay}s delay"
                    })
                
                # Handle sequence fallback configuration
                if 'sequence_fallback' in data:
                    sequence_fallback_data = data['sequence_fallback']
                    enabled = sequence_fallback_data.get('enabled', False)
                    scene_id = sequence_fallback_data.get('scene_id', 'blackout')
                    delay = sequence_fallback_data.get('delay', 1.0)
                    
                    print(f"Setting sequence fallback: enabled={enabled}, scene_id={scene_id}, delay={delay}")
                    
                    # Update sequence fallback configuration
                    if 'sequence_fallback' not in self.fallback_config:
                        self.fallback_config['sequence_fallback'] = {}
                    
                    self.fallback_config['sequence_fallback'] = {
                        'enabled': enabled,
                        'scene_id': scene_id,
                        'delay': delay
                    }
                    
                    print(f"Updated sequence fallback config: {self.fallback_config}")
                    
                    # Save to config
                    self.config['fallback'] = self.fallback_config
                    self.save_config()
                    
                    return jsonify({
                        "success": True,
                        "message": f"Sequence fallback {'enabled' if enabled else 'disabled'} with scene '{scene_id}' and {delay}s delay"
                    })
                
                # Handle sequence fallback configuration (existing logic)
                if not data or 'type' not in data or 'id' not in data:
                    return jsonify({
                        "success": False,
                        "error": "Missing required fields: type and id"
                    }), 400
                
                fallback_type = data['type']  # 'scene' or 'sequence'
                fallback_id = data['id']
                enabled = data.get('enabled', True)
                
                if enabled:
                    # Disable any existing autostart
                    self.disable_current_autostart()
                    
                    # Set new fallback
                    self.fallback_config = {
                        'type': fallback_type,
                        'id': fallback_id,
                        'enabled': True
                    }
                    self.current_autostart = fallback_id # Fallback uses autostart logic
                    
                    # Start the fallback
                    self.start_autostart() # Use the existing autostart logic
                else:
                    # Disable fallback
                    self.disable_current_autostart()
                    self.fallback_config = {}
                    self.current_autostart = None
                
                # Save to config
                self.config['fallback'] = self.fallback_config
                self.save_config()
                
                return jsonify({
                    "success": True,
                    "message": f"Fallback {'enabled' if enabled else 'disabled'} for {fallback_type} '{fallback_id}'"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/fallback', methods=['DELETE'])
        def disable_fallback():
            """Disable current fallback"""
            try:
                self.disable_current_autostart()
                self.fallback_config = {}
                self.current_autostart = None
                
                # Save to config
                self.config['fallback'] = self.fallback_config
                self.save_config()
                
                return jsonify({
                    "success": True,
                    "message": "Fallback disabled"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/playback/status', methods=['GET'])
        def get_playback_status():
            """Get current playback status"""
            try:
                status = {
                    "is_playing": False,
                    "current_scene": None,
                    "current_sequence": None,
                    "current_step": 0,
                    "total_steps": 0,
                    "step_progress": 0,
                    "elapsed_time": 0,
                    "total_duration": 0,
                    "playback_paused": False,
                    "step_data": None
                }
                
                # Calculate elapsed time
                if self.playback_start_time and not self.playback_paused:
                    elapsed_time = time.time() - self.playback_start_time - self.total_pause_time
                elif self.playback_start_time and self.playback_paused:
                    elapsed_time = self.playback_pause_time - self.playback_start_time - self.total_pause_time
                else:
                    elapsed_time = 0
                
                if self.current_sequence_playback:
                    status["is_playing"] = True
                    status["current_sequence"] = self.current_sequence_playback.get('sequence_name', 'Unknown')
                    status["current_step"] = self.current_step_index + 1
                    status["total_steps"] = len(self.current_sequence_playback.get('sequence', []))
                    status["playback_paused"] = self.playback_paused
                    status["elapsed_time"] = elapsed_time
                    
                    if self.current_step_data:
                        status["step_data"] = {
                            "scene_name": self.current_step_data.get('scene_name', 'Unknown'),
                            "duration": self.current_step_data.get('duration', 0),
                            "progress": self.current_step_data.get('progress', 0)
                        }
                        status["step_progress"] = self.current_step_data.get('progress', 0)
                        status["total_duration"] = self.current_step_data.get('total_duration', 0)
                
                elif self.current_scene_playback:
                    status["is_playing"] = True
                    status["current_scene"] = self.current_scene_playback.get('scene_name', 'Unknown')
                    status["playback_paused"] = self.playback_paused
                    status["elapsed_time"] = elapsed_time
                
                elif self.current_programmable_scene_playback:
                    status["is_playing"] = True
                    scene_id = self.current_programmable_scene_playback.get('scene_id', 'Unknown')
                    status["current_programmable_scene"] = scene_id
                    
                    # Get scene name from config
                    scene_name = scene_id
                    if scene_id in self.programmable_scenes:
                        scene_name = self.programmable_scenes[scene_id].get('name', scene_id)
                    status["current_scene"] = scene_name  # Use standard field for consistency
                    
                    status["playback_paused"] = self.playback_paused
                    status["elapsed_time"] = elapsed_time
                    
                    # Calculate progress for programmable scenes
                    duration = self.current_programmable_scene_playback.get('duration', 0)
                    status["scene_duration"] = duration
                    status["total_duration"] = duration
                    status["scene_loop"] = self.current_programmable_scene_playback.get('loop', False)
                    
                    if duration > 0:
                        # Calculate progress within the current loop
                        loop_time = elapsed_time % duration if status["scene_loop"] else elapsed_time
                        progress = min(100.0, (loop_time / duration) * 100) if duration > 0 else 0
                        status["step_progress"] = progress
                        
                        # Add step data for consistency with sequences
                        status["step_data"] = {
                            "scene_name": scene_name,
                            "duration": duration,
                            "progress": progress,
                            "expressions": self.current_programmable_scene_playback.get('expressions', {})
                        }
                
                return jsonify({
                    "success": True,
                    "data": status
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/playback/pause', methods=['POST', 'GET'])
        def pause_playback():
            """Pause the current playback"""
            try:
                if not self.playback_paused and (self.current_sequence_playback or self.current_scene_playback or self.current_programmable_scene_playback):
                    self.playback_paused = True
                    self.playback_pause_time = time.time()
                    return jsonify({
                        "success": True,
                        "message": "Playback paused"
                    })
                else:
                    return jsonify({
                        "success": False,
                        "message": "No active playback to pause or already paused"
                    }), 404
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/playback/resume', methods=['POST', 'GET'])
        def resume_playback():
            """Resume the current playback"""
            try:
                if self.playback_paused and (self.current_sequence_playback or self.current_scene_playback or self.current_programmable_scene_playback):
                    self.playback_paused = False
                    if self.playback_pause_time:
                        self.total_pause_time += time.time() - self.playback_pause_time
                        self.playback_pause_time = None
                    return jsonify({
                        "success": True,
                        "message": "Playback resumed"
                    })
                else:
                    return jsonify({
                        "success": False,
                        "message": "No paused playback to resume"
                    }), 404
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/playback/stop', methods=['POST', 'GET'])
        def stop_playback():
            """Stop the current playback"""
            try:
                stopped = False
                
                # Stop sequence playback
                if self.current_sequence_playback:
                    self.stop_sequence_playback()
                    stopped = True
                
                # Stop programmable scene playback
                if self.current_programmable_scene_playback:
                    self.stop_programmable_scene_playback()
                    stopped = True
                
                # Stop scene playback
                if self.current_scene_playback:
                    self.current_scene_playback = None
                    stopped = True
                
                if stopped:
                    return jsonify({
                        "success": True,
                        "message": "Playback stopped"
                    })
                else:
                    return jsonify({
                        "success": False,
                        "message": "No playback is currently active"
                    }), 404
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/dmx/channel-update', methods=['GET'])
        def get_channel_update():
            """Get the last MQTT channel update for frontend sync"""
            try:
                if self.last_mqtt_channel_update:
                    update = self.last_mqtt_channel_update.copy()
                    self.last_mqtt_channel_update = None  # Clear after sending
                    return jsonify({
                        "success": True,
                        "update": update
                    })
                else:
                    return jsonify({
                        "success": True,
                        "update": None
                    })
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/mqtt/publish', methods=['POST'])
        def mqtt_publish():
            """Publish an MQTT message from the frontend"""
            try:
                data = request.get_json()
                topic = data.get('topic')
                payload = data.get('payload')
                if not topic or payload is None:
                    return jsonify({"success": False, "error": "Missing topic or payload"}), 400
                if self.client and self.mqtt_connected:
                    self.client.publish(topic, str(payload))
                    return jsonify({"success": True})
                else:
                    return jsonify({"success": False, "error": "MQTT not connected"}), 503
            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 500

        @self.flask_app.route('/api/settings/fallback-delay', methods=['POST'])
        def set_fallback_delay():
            """Set the global fallback delay"""
            try:
                data = request.get_json()
                delay = data.get('delay', 1.0)
                
                # Validate delay
                if not isinstance(delay, (int, float)) or delay < 0.1 or delay > 60.0:
                    return jsonify({"success": False, "error": "Delay must be between 0.1 and 60.0 seconds"}), 400
                
                # Update settings
                self.config_manager.settings['fallback_delay'] = delay
                self.config_manager.save_settings()
                
                return jsonify({
                    "success": True,
                    "message": f"Fallback delay set to {delay}s"
                })
            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 500

        @self.flask_app.route('/api/settings/dmx-retransmission', methods=['GET'])
        def get_dmx_retransmission():
            try:
                return jsonify({
                    'success': True,
                    'data': self.dmx_retransmission_settings
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.flask_app.route('/api/settings/dmx-retransmission', methods=['POST'])
        def set_dmx_retransmission():
            try:
                data = request.get_json()
                enabled = bool(data.get('enabled', False))
                interval = float(data.get('interval', 5.0))
                if interval < 0.1 or interval > 60.0:
                    return jsonify({'success': False, 'error': 'Interval must be between 0.1 and 60 seconds'}), 400
                self.update_dmx_retransmission_settings(enabled, interval)
                return jsonify({'success': True, 'data': self.dmx_retransmission_settings})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.flask_app.route('/api/settings/dmx-followers', methods=['GET'])
        def get_dmx_followers():
            try:
                return jsonify({'success': True, 'data': self.dmx_followers_settings})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        @self.flask_app.route('/api/settings/dmx-followers', methods=['POST'])
        def set_dmx_followers():
            try:
                data = request.get_json()
                enabled = bool(data.get('enabled', False))
                mappings = data.get('mappings', {})
                
                # Auto-enable if mappings are provided
                if mappings and any(mappings.values()):
                    enabled = True
                
                self.dmx_followers_settings['enabled'] = enabled
                self.dmx_followers_settings['mappings'] = mappings
                self.config_manager.settings['dmx_followers'] = self.dmx_followers_settings
                self.config_manager.save_settings()
                
                print(f"Updated DMX followers: enabled={enabled}, mappings={mappings}")
                return jsonify({'success': True, 'data': self.dmx_followers_settings})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        # Programmable Scenes API endpoints
        @self.flask_app.route('/api/programmable', methods=['GET'])
        def get_programmable_scenes():
            """Get all programmable scenes"""
            try:
                # Convert to list format for frontend
                scenes_list = []
                for scene_id, scene_data in self.programmable_scenes.items():
                    scenes_list.append({
                        'id': scene_id,
                        'name': scene_data.get('name', scene_id),
                        'description': scene_data.get('description', ''),
                        'duration': scene_data.get('duration', 10000),
                        'loop': scene_data.get('loop', False),
                        'expressions': scene_data.get('expressions', {})
                    })
                return jsonify({
                    "success": True,
                    "data": scenes_list
                })
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/programmable', methods=['POST'])
        def create_programmable_scene():
            """Create a new programmable scene"""
            try:
                data = request.get_json()
                
                if not data or 'name' not in data:
                    return jsonify({
                        "success": False,
                        "error": "Missing required field: name"
                    }), 400
                
                scene_name = data['name'].lower().replace(' ', '_')
                if scene_name in self.programmable_scenes:
                    return jsonify({
                        "success": False,
                        "error": f"Programmable scene '{scene_name}' already exists"
                    }), 400
                
                # Create new programmable scene
                self.programmable_scenes[scene_name] = {
                    'name': data['name'],
                    'description': data.get('description', ''),
                    'duration': data.get('duration', 10000),
                    'loop': data.get('loop', False),
                    'expressions': data.get('expressions', {})
                }
                
                # Save to config
                self.config['programmable_scenes'] = self.programmable_scenes
                self.save_config()
                
                return jsonify({
                    "success": True,
                    "message": f"Programmable scene '{scene_name}' created successfully",
                    "data": self.programmable_scenes[scene_name]
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/programmable/<scene_id>', methods=['PUT'])
        def update_programmable_scene(scene_id):
            """Update a programmable scene"""
            try:
                if scene_id not in self.programmable_scenes:
                    return jsonify({
                        "success": False,
                        "error": f"Programmable scene '{scene_id}' not found"
                    }), 404
                
                data = request.get_json()
                
                # Update scene data
                if 'name' in data:
                    self.programmable_scenes[scene_id]['name'] = data['name']
                if 'description' in data:
                    self.programmable_scenes[scene_id]['description'] = data['description']
                if 'duration' in data:
                    self.programmable_scenes[scene_id]['duration'] = data['duration']
                if 'loop' in data:
                    self.programmable_scenes[scene_id]['loop'] = data['loop']
                if 'expressions' in data:
                    self.programmable_scenes[scene_id]['expressions'] = data['expressions']
                
                # Save to config
                self.config['programmable_scenes'] = self.programmable_scenes
                self.save_config()
                
                return jsonify({
                    "success": True,
                    "message": f"Programmable scene '{scene_id}' updated successfully",
                    "data": self.programmable_scenes[scene_id]
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/programmable/<scene_id>', methods=['DELETE'])
        def delete_programmable_scene(scene_id):
            """Delete a programmable scene"""
            try:
                if scene_id not in self.programmable_scenes:
                    return jsonify({
                        "success": False,
                        "error": f"Programmable scene '{scene_id}' not found"
                    }), 404
                
                # Stop playback if this scene is currently playing
                if (self.current_programmable_scene_playback and 
                    self.current_programmable_scene_playback.get('scene_id') == scene_id):
                    self.stop_programmable_scene_playback()
                
                # Delete the scene
                del self.programmable_scenes[scene_id]
                
                # Save to config
                self.config['programmable_scenes'] = self.programmable_scenes
                self.save_config()
                
                return jsonify({
                    "success": True,
                    "message": f"Programmable scene '{scene_id}' deleted successfully"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

        @self.flask_app.route('/api/programmable/<scene_id>/play', methods=['POST'])
        def play_programmable_scene_api(scene_id):
            """Play a programmable scene"""
            try:
                if scene_id not in self.programmable_scenes:
                    return jsonify({
                        "success": False,
                        "error": f"Programmable scene '{scene_id}' not found"
                    }), 404
                
                # Play the programmable scene
                self.play_programmable_scene(scene_id)
                
                return jsonify({
                    "success": True,
                    "message": f"Programmable scene '{scene_id}' started"
                })
                    
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": str(e)
                }), 500

    def save_config(self):
        """Save current configuration to file"""
        try:
            # Use the same path that was used to load the config
            script_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(script_dir)
            config_path = os.path.join(project_root, 'config.json')
            
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            print(f"Configuration saved to: {config_path}")
            return True
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False

    def start_autostart(self):
        """Start the current autostart"""
        if not self.autostart_config.get('enabled'):
            return
        
        autostart_type = self.autostart_config.get('type')
        autostart_id = self.autostart_config.get('id')
        
        if autostart_type == 'scene' and autostart_id in self.config.get('scenes', {}):
            print(f"Starting autostart scene: {autostart_id}")
            self.play_scene(autostart_id)
        elif autostart_type == 'sequence' and autostart_id in self.config.get('sequences', {}):
            print(f"Starting autostart sequence: {autostart_id}")
            self.play_sequence(self.config['sequences'][autostart_id])

    def disable_current_autostart(self):
        """Disable the current autostart"""
        if self.autostart_timer:
            self.autostart_timer.cancel()
            self.autostart_timer = None
        
        if self.current_autostart:
            print(f"Disabled autostart: {self.current_autostart}")
            self.current_autostart = None

    def trigger_fallback(self):
        """Trigger the fallback scene/sequence (legacy support)"""
        # Check if we have the new fallback configuration structure
        scene_fallback_config = self.fallback_config.get('scene_fallback', {})
        sequence_fallback_config = self.fallback_config.get('sequence_fallback', {})
        
        # If we have new fallback configs, use those instead
        if scene_fallback_config.get('enabled') or sequence_fallback_config.get('enabled'):
            print("Using new fallback configuration structure")
            return  # Let the specific trigger functions handle it
        
        # Legacy fallback support
        if not self.fallback_config.get('enabled'):
            return
            
        fallback_type = self.fallback_config.get('type')
        fallback_id = self.fallback_config.get('id')
        delay = self.fallback_config.get('delay', 0.0)
        
        if not fallback_id:
            return
            
        print(f"Triggering legacy fallback: {fallback_type} '{fallback_id}' after {delay}s delay")
        
        def run_fallback():
            if delay > 0:
                time.sleep(delay)
            
            if fallback_type == 'scene' and fallback_id in self.config.get('scenes', {}):
                print(f"Playing legacy fallback scene: {fallback_id}")
                self.play_scene(fallback_id)
            elif fallback_type == 'sequence' and fallback_id in self.config.get('sequences', {}):
                print(f"Playing legacy fallback sequence: {fallback_id}")
                self.play_sequence(self.config['sequences'][fallback_id])
            else:
                print(f"Legacy fallback {fallback_type} '{fallback_id}' not found")
        
        threading.Thread(target=run_fallback).start()

    def trigger_scene_fallback(self, scene_name):
        """Trigger the scene fallback after a scene is played"""
        print(f"Checking scene fallback for scene: {scene_name}")
        print(f"Current fallback config: {self.fallback_config}")
        
        scene_fallback_config = self.fallback_config.get('scene_fallback', {})
        print(f"Scene fallback config: {scene_fallback_config}")
        
        if not scene_fallback_config.get('enabled'):
            print("Scene fallback not enabled")
            return
            
        fallback_scene_id = scene_fallback_config.get('scene_id')
        # Use global fallback delay from settings
        global_delay = self.config_manager.settings.get('fallback_delay', 1.0)
        delay = scene_fallback_config.get('delay', global_delay)
        
        print(f"Fallback scene ID: {fallback_scene_id}, Delay: {delay}")
        
        if not fallback_scene_id:
            print("No fallback scene ID configured")
            return
            
        print(f"Triggering scene fallback: scene '{fallback_scene_id}' after {delay}s delay")
        
        def run_scene_fallback():
            print(f"Starting scene fallback thread, waiting {delay}s...")
            if delay > 0:
                time.sleep(delay)
            
            if fallback_scene_id in self.config.get('scenes', {}):
                print(f"Playing scene fallback: {fallback_scene_id}")
                self.play_scene(fallback_scene_id)
            else:
                print(f"Scene fallback '{fallback_scene_id}' not found")
        
        threading.Thread(target=run_scene_fallback).start()

    def trigger_sequence_fallback(self):
        """Trigger the sequence fallback after a sequence finishes"""
        print("Checking sequence fallback")
        print(f"Current fallback config: {self.fallback_config}")
        
        sequence_fallback_config = self.fallback_config.get('sequence_fallback', {})
        print(f"Sequence fallback config: {sequence_fallback_config}")
        
        if not sequence_fallback_config.get('enabled'):
            print("Sequence fallback not enabled")
            return
            
        # Use the configured fallback scene from sequence fallback config
        fallback_scene_id = sequence_fallback_config.get('scene_id', 'blackout')
        # Use global fallback delay from settings
        global_delay = self.config_manager.settings.get('fallback_delay', 1.0)
        delay = sequence_fallback_config.get('delay', global_delay)
        
        print(f"Fallback scene ID: {fallback_scene_id}, Delay: {delay}")
        print(f"Triggering sequence fallback: scene '{fallback_scene_id}' after {delay}s delay")
        
        def run_sequence_fallback():
            print(f"Starting sequence fallback thread, waiting {delay}s...")
            if delay > 0:
                time.sleep(delay)
            
            if fallback_scene_id in self.config.get('scenes', {}):
                print(f"Playing sequence fallback: {fallback_scene_id}")
                self.play_scene(fallback_scene_id)
            else:
                print(f"Sequence fallback '{fallback_scene_id}' not found")
        
        threading.Thread(target=run_sequence_fallback).start()

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("Connected to MQTT broker.")
            self.mqtt_connected = True
            
            # Only subscribe once to avoid duplicate subscriptions
            if not self.subscriptions_done:
                # Initialize subscriptions
                self.refresh_mqtt_subscriptions()
                self.subscriptions_done = True
        else:
            print(f"Failed to connect to MQTT broker with return code: {rc}")
            self.mqtt_connected = False

    def on_disconnect(self, client, userdata, rc):
        if rc != 0:
            print(f"Unexpected MQTT disconnection with return code: {rc}")
            self.mqtt_reconnect_attempts += 1
            
            if self.mqtt_reconnect_attempts <= self.max_mqtt_reconnect_attempts:
                # Reset subscription flag to allow resubscription on reconnect
                self.subscriptions_done = False
                # Attempt to reconnect after a delay
                print(f"Attempting to reconnect in 5 seconds... (attempt {self.mqtt_reconnect_attempts}/{self.max_mqtt_reconnect_attempts})")
                time.sleep(5)
                try:
                    client.reconnect()
                except Exception as e:
                    print(f"Reconnection failed: {e}")
                    if self.mqtt_reconnect_attempts >= self.max_mqtt_reconnect_attempts:
                        print("Maximum reconnection attempts reached. Continuing without MQTT functionality.")
                        self.stop_mqtt_reconnection()
            else:
                print("Maximum reconnection attempts reached. Continuing without MQTT functionality.")
                self.stop_mqtt_reconnection()
        else:
            print("MQTT broker disconnected")
        self.mqtt_connected = False

    def signal_handler(self, signum, frame):
        """Handle shutdown signals (SIGINT, SIGTERM)"""
        print(f"\nReceived signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
        self.shutdown()

    def shutdown(self):
        """Perform graceful shutdown of all components"""
        print("Shutting down MQTT DMX Sequencer...")
        
        # Stop sequence playback
        if self.current_sequence_playback:
            print("Stopping sequence playback...")
            self.current_sequence_playback = None
            self.current_step_index = 0
            self.current_step_data = None
        
        # Disable autostart
        self.disable_current_autostart()
        
        # Disconnect MQTT
        if self.client:
            print("Disconnecting MQTT client...")
            try:
                self.client.disconnect()
            except Exception as e:
                print(f"Error disconnecting MQTT: {e}")
            self.client = None
            self.mqtt_connected = False
        
        # Stop DMX senders
        print("Stopping DMX senders...")
        try:
            self.dmx_manager.stop_all()
        except Exception as e:
            print(f"Error stopping DMX senders: {e}")
        
        # Stop web server if running
        if self.flask_app and self.web_thread and self.web_thread.is_alive():
            print("Stopping web server...")
            # Flask doesn't have a built-in shutdown method, but the thread is daemon
            # so it will be terminated when the main process exits
        
        self.stop_dmx_retransmission()
        print("Shutdown complete.")
        sys.exit(0)

    def stop_mqtt_reconnection(self):
        """Stop MQTT reconnection attempts"""
        if self.client:
            self.client.disconnect()
            self.client = None
            self.mqtt_connected = False
            print("MQTT reconnection stopped")

    def refresh_mqtt_subscriptions(self):
        """Refresh MQTT subscriptions based on current configuration"""
        if not self.client or not self.mqtt_connected:
            print("MQTT not connected, skipping subscription refresh")
            return
        
        print("Refreshing MQTT subscriptions...")
        
        # Get current configuration
        current_config = self.load_config(self.config_manager.settings_path.replace('settings.json', 'config.json'))
        
        # Calculate new subscriptions
        new_subscriptions = set()
        
        # Add sequence subscriptions
        for topic in current_config.get('sequences', {}).keys():
            new_subscriptions.add(topic)
        
        # Add standard subscriptions
        standard_topics = [
            "dmx/set/channel/#",
            "dmx/scene/#", 
            "dmx/sender/#",
            "dmx/config/#"
        ]
        for topic in standard_topics:
            new_subscriptions.add(topic)
        
        # Unsubscribe from topics that are no longer needed
        topics_to_unsubscribe = self.current_mqtt_subscriptions - new_subscriptions
        for topic in topics_to_unsubscribe:
            if topic not in standard_topics:  # Don't unsubscribe from standard topics
                print(f"Unsubscribing from topic: {topic}")
                self.client.unsubscribe(topic)
                self.current_mqtt_subscriptions.discard(topic)
        
        # Subscribe to new topics
        topics_to_subscribe = new_subscriptions - self.current_mqtt_subscriptions
        for topic in topics_to_subscribe:
            print(f"Subscribing to topic: {topic}")
            self.client.subscribe(topic)
            self.current_mqtt_subscriptions.add(topic)
        
        print(f"MQTT subscriptions refreshed. Current subscriptions: {len(self.current_mqtt_subscriptions)}")

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode('utf-8')
        print(f"Received message on topic: {topic} with payload: {payload}")
        
        # Handle individual channel control
        if topic.startswith("dmx/set/channel/"):
            self.handle_channel_control(topic, payload)
        
        # Handle scene control
        elif topic.startswith("dmx/scene/"):
            print(f"MQTT: Handling scene control for topic: {topic}")
            self.handle_scene_control(topic, payload)
        
        # Handle DMX sender management
        elif topic.startswith("dmx/sender/"):
            self.handle_sender_management(topic, payload)
        
        # Handle configuration management
        elif topic.startswith("dmx/config/"):
            self.handle_config_management(topic, payload)
        
        # Handle sequence playback
        elif topic in self.config.get('sequences', {}):
            print(f"MQTT: Handling sequence playback for topic: {topic}")
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
                # Notify frontend of the update via a simple flag
                self.last_mqtt_channel_update = {'channel': channel, 'value': value}
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

    def stop_sequence_playback(self):
        """Stop the current sequence playback"""
        if self.current_sequence_playback or self.current_scene_playback:
            self.current_sequence_playback = None
            self.current_scene_playback = None
            self.current_step_index = 0
            self.current_step_data = None
            self.playback_start_time = None
            self.playback_paused = False
            self.playback_pause_time = None
            self.total_pause_time = 0
            print("Playback stopped")
            return True
        return False

    def stop_programmable_scene_playback(self):
        """Stop the current programmable scene playback"""
        if self.current_programmable_scene_playback:
            self.current_programmable_scene_playback = None
            self.playback_start_time = None
            self.playback_paused = False
            self.playback_pause_time = None
            self.total_pause_time = 0
            print("Programmable scene playback stopped")
            return True
        return False

    def play_scene(self, scene_name, transition_time=0.0):
        """Play a scene with optional transition time"""
        # Always stop any running programmable scene
        self.stop_programmable_scene_playback()
        if scene_name not in self.config.get('scenes', {}):
            print(f"Scene '{scene_name}' not found")
            return
            
        scene_data = self.config['scenes'][scene_name]
        scenes_config = self.config_manager.get_scenes_config()
        auto_send = scenes_config.get('auto_send', True)
        
        print(f"Playing scene: {scene_name} with transition time: {transition_time}s")
        
        # Set scene playback state
        self.current_scene_playback = {
            'scene_name': scene_name,
            'scene_data': scene_data,
            'transition_time': transition_time
        }
        self.current_sequence_playback = None  # Clear sequence playback
        self.playback_start_time = time.time()
        self.playback_paused = False
        self.total_pause_time = 0
        
        def run():
            # Apply scene data to DMX channels
            channels = {}
            for channel_index, value in enumerate(scene_data):
                if value is not None:  # Skip null values (don't change channel)
                    channel_number = channel_index + 1  # Convert to 1-based channel numbering
                    channels[channel_number] = value
            
            # Set all channels at once
            self.set_channels_with_followers(channels)
            if auto_send:
                self.dmx_manager.send()
            print(f"Scene '{scene_name}' applied")
            
            # Trigger scene fallback after delay
            self.trigger_scene_fallback(scene_name)
            
        threading.Thread(target=run).start()

    def play_sequence(self, sequence, loop=False):
        """Play a sequence with optional looping"""
        # Always stop any running programmable scene
        self.stop_programmable_scene_playback()
        sequences_config = self.config_manager.get_sequences_config()
        default_duration = sequences_config.get('default_duration', 1.0)
        auto_play = sequences_config.get('auto_play', True)
        
        print(f"Starting sequence playback - Steps: {len(sequence)}, Loop: {loop}, Auto play: {auto_play}")
        print(f"Active DMX senders: {self.dmx_manager.list_senders()}")
        
        # Set current sequence playback state
        self.current_sequence_playback = {
            'sequence': sequence,
            'loop': loop,
            'total_steps': len(sequence),
            'sequence_name': 'Unknown'  # Will be set by API call
        }
        self.current_scene_playback = None  # Clear scene playback
        self.current_step_index = 0
        self.current_step_data = None
        self.playback_start_time = time.time()
        self.playback_paused = False
        self.total_pause_time = 0
        
        def run():
            while not self.shutdown_requested and self.current_sequence_playback:  # Loop indefinitely if loop=True
                for step_index, step in enumerate(sequence):
                    # Check for shutdown request or stop request
                    if self.shutdown_requested or not self.current_sequence_playback:
                        break
                    # Update current step information with enhanced progress tracking
                    self.current_step_index = step_index
                    step_start_time = time.time()
                    
                    # Enhanced step data with progress tracking
                    self.current_step_data = {
                        'scene_name': step.get('scene_name') or step.get('scene_id', 'Unknown'),
                        'duration': step.get('duration', default_duration),
                        'progress': 0,
                        'start_time': step_start_time,
                        'total_duration': step.get('duration', default_duration)
                    }
                    
                    print(f"Playing step {step_index + 1}/{len(sequence)}")
                    
                    # Check if this is a scene-based step or direct DMX step
                    if 'scene_id' in step or 'scene_name' in step:
                        # This is a scene-based step - play the scene
                        scene_name = step.get('scene_name') or step.get('scene_id')
                        duration = step.get('duration', default_duration)
                        if isinstance(duration, int):
                            duration = duration / 1000.0  # Convert ms to seconds
                        
                        print(f"Playing scene: {scene_name} for {duration}s")
                        if scene_name in self.config.get('scenes', {}):
                            self.play_scene(scene_name)
                        else:
                            print(f"Scene '{scene_name}' not found")
                        
                        # Wait for duration with progress tracking
                        step_elapsed = 0
                        while step_elapsed < duration:
                            if self.shutdown_requested or not self.current_sequence_playback:
                                break
                            time.sleep(0.1)
                            step_elapsed = time.time() - step_start_time
                            # Update progress
                            if self.current_step_data:
                                self.current_step_data['progress'] = min(step_elapsed / duration, 1.0)
                        if self.shutdown_requested or not self.current_sequence_playback:
                            break
                    else:
                        # This is a direct DMX step
                        dmx_data = step.get('dmx', {})
                        duration = step.get('duration', default_duration)
                        
                        print(f"Setting DMX data for {duration}s")
                        
                        # Convert string keys to integers for DMX channels
                        dmx_channels = {}
                        for channel_str, value in dmx_data.items():
                            try:
                                channel = int(channel_str)
                                dmx_channels[channel] = value
                            except (ValueError, TypeError):
                                print(f"Invalid channel number: {channel_str}")
                                continue
                        
                        # Set channels for this step
                        self.set_channels_with_followers(dmx_channels)
                        if auto_play:
                            self.dmx_manager.send()
                        
                        # Wait for duration with progress tracking
                        step_elapsed = 0
                        while step_elapsed < duration:
                            if self.shutdown_requested or not self.current_sequence_playback:
                                break
                            time.sleep(0.1)
                            step_elapsed = time.time() - step_start_time
                            # Update progress
                            if self.current_step_data:
                                self.current_step_data['progress'] = min(step_elapsed / duration, 1.0)
                        if self.shutdown_requested or not self.current_sequence_playback:
                            break
                
                if not loop:
                    break  # Exit loop if not set to loop
                else:
                    print("Sequence loop completed, restarting...")
            
            # Clear sequence playback state when finished
            self.current_sequence_playback = None
            self.current_step_index = 0
            self.current_step_data = None
            print("Sequence finished.")
            
            # Trigger fallback for non-looping sequences
            if not loop:
                self.trigger_fallback()
                # Also trigger sequence fallback
                self.trigger_sequence_fallback()
        
        threading.Thread(target=run).start()

    def play_programmable_scene(self, scene_id):
        """Play a programmable scene with mathematical expressions"""
        if scene_id not in self.programmable_scenes:
            print(f"Programmable scene '{scene_id}' not found")
            return
            
        scene_data = self.programmable_scenes[scene_id]
        duration = scene_data.get('duration', 10000) / 1000.0  # Convert ms to seconds
        max_fps = 100  # Maximum 100Hz update rate
        loop = scene_data.get('loop', False)
        expressions = scene_data.get('expressions', {})
        
        print(f"Playing programmable scene: {scene_id} (duration: {duration}s, max_fps: {max_fps}, loop: {loop})")
        
        # Set programmable scene playback state
        self.current_programmable_scene_playback = {
            'scene_id': scene_id,
            'scene_data': scene_data,
            'duration': duration,
            'fps': max_fps,
            'loop': loop,
            'expressions': expressions
        }
        self.current_sequence_playback = None  # Clear sequence playback
        self.current_scene_playback = None  # Clear scene playback
        self.playback_start_time = time.time()
        self.playback_paused = False
        self.total_pause_time = 0
        
        def run():
            frame_interval = 1.0 / max_fps  # 10ms intervals for 100Hz
            start_time = time.time()
            previous_channels = {}  # Track previous channel values
            
            while not self.shutdown_requested and self.current_programmable_scene_playback:
                # Check for pause state
                if self.playback_paused:
                    time.sleep(0.1)  # Short sleep while paused
                    continue
                
                current_time = time.time() - start_time - self.total_pause_time
                
                # Check if scene duration exceeded (unless looping)
                if not loop and current_time >= duration:
                    break
                
                # Calculate time within the scene (for looping)
                scene_time = current_time % duration if loop else current_time
                
                # Evaluate expressions for each channel
                channels = {}
                for channel_str, expression in expressions.items():
                    try:
                        channel = int(channel_str)
                        value = self.programmable_scene_evaluator.evaluate_expression(expression, scene_time, channel)
                        channels[channel] = value
                    except (ValueError, TypeError) as e:
                        print(f"Invalid channel number or expression for channel {channel_str}: {e}")
                        continue
                
                # Check if any channel values have changed
                channels_changed = False
                for channel, value in channels.items():
                    if channel not in previous_channels or abs(previous_channels[channel] - value) > 0.1:  # Small threshold for floating point comparison
                        channels_changed = True
                        break
                
                # Only send DMX if values have changed
                if channels_changed and channels:
                    self.set_channels_with_followers(channels)
                    self.dmx_manager.send()
                    # Update previous channels
                    previous_channels.update(channels)
                
                # Wait for next frame
                time.sleep(frame_interval)
            
            # Clear programmable scene playback state when finished
            self.current_programmable_scene_playback = None
            print(f"Programmable scene '{scene_id}' finished")
            
            # Trigger fallback for non-looping scenes
            if not loop:
                self.trigger_fallback()
        
        threading.Thread(target=run).start()

    def start_dmx_retransmission(self):
        if self.dmx_retransmission_thread and self.dmx_retransmission_thread.is_alive():
            return
        self.dmx_retransmission_stop.clear()
        def retransmit():
            while not self.dmx_retransmission_stop.is_set():
                interval = self.dmx_retransmission_settings.get('interval', 5.0)
                self.dmx_manager.send()
                self.dmx_retransmission_stop.wait(interval)
        self.dmx_retransmission_thread = threading.Thread(target=retransmit, daemon=True)
        self.dmx_retransmission_thread.start()

    def stop_dmx_retransmission(self):
        self.dmx_retransmission_stop.set()
        if self.dmx_retransmission_thread:
            self.dmx_retransmission_thread.join(timeout=2)

    def update_dmx_retransmission_settings(self, enabled, interval):
        self.dmx_retransmission_settings['enabled'] = enabled
        self.dmx_retransmission_settings['interval'] = interval
        self.config_manager.settings['dmx_retransmission'] = self.dmx_retransmission_settings
        self.config_manager.save_settings()
        if enabled:
            self.start_dmx_retransmission()
        else:
            self.stop_dmx_retransmission()

    def apply_follower_channels(self, channels):
        if not self.dmx_followers_settings.get('enabled', False):
            return channels
        mappings = self.dmx_followers_settings.get('mappings', {})
        # mappings: {"source_channel": [follower1, follower2, ...]}
        updated = dict(channels)
        for src, followers in mappings.items():
            src = int(src)
            if src in channels:
                for follower in followers:
                    updated[int(follower)] = channels[src]
        return updated

    # Patch DMX set_channels to apply followers
    def set_channels_with_followers(self, channels):
        channels = self.apply_follower_channels(channels)
        self.dmx_manager.set_channels(channels)

    def run(self):
        """Run the MQTT DMX sequencer"""
        try:
            print("MQTT DMX Sequencer started")
            print(f"Active DMX senders: {self.dmx_manager.list_senders()}")
            
            # Start autostart if configured
            if self.autostart_config.get('enabled'):
                print(f"Starting autostart: {self.autostart_config.get('type')} '{self.autostart_config.get('id')}'")
                self.start_autostart()
            
            # Start MQTT loop with automatic reconnection
            if self.client:
                self.client.loop_forever()
            else:
                print("MQTT client not initialized, running without MQTT")
                # Keep the application running even without MQTT
                while not self.shutdown_requested:
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            print("\nReceived Ctrl+C, initiating graceful shutdown...")
            self.shutdown()


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
    parser.add_argument('--disable-mqtt', action='store_true', help='Disable MQTT functionality')
    
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
    
    # Disable MQTT if requested
    if args.disable_mqtt:
        print("MQTT functionality disabled by command line argument")
        sequencer.stop_mqtt_reconnection()
    
    sequencer.run()
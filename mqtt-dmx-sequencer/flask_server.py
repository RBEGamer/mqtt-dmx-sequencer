#!/usr/bin/env python3
"""
Flask API Server for MQTT DMX Sequencer
Provides REST API endpoints to manage scenes and sequences
"""

from flask import Flask, request, jsonify, send_from_directory
import json
import os
from typing import Dict, Any, List
from config_manager import ConfigManager

app = Flask(__name__, static_folder='static')

# Global config manager instance
config_manager = None
config_path = None

def load_config_files(config_dir: str = None):
    """Load configuration files"""
    global config_manager, config_path
    
    if config_dir is None:
        # Default to current directory
        config_dir = os.path.dirname(os.path.abspath(__file__))
    
    settings_path = os.path.join(config_dir, 'settings.json')
    config_path = os.path.join(config_dir, 'config.json')
    
    config_manager = ConfigManager(settings_path)
    return config_path

def load_scenes_and_sequences() -> Dict[str, Any]:
    """Load scenes and sequences from config file"""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"scenes": {}, "sequences": {}}
    except json.JSONDecodeError:
        return {"scenes": {}, "sequences": {}}

def save_scenes_and_sequences(data: Dict[str, Any]) -> bool:
    """Save scenes and sequences to config file"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        with open(config_path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving configuration: {e}")
        return False

# Web Interface Routes

@app.route('/')
def index():
    """Serve the main web interface"""
    return send_from_directory('static', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    """Serve static files"""
    return send_from_directory('static', filename)

# API Routes

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "mqtt-dmx-sequencer-api",
        "version": "1.0.0"
    })

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    try:
        config = load_scenes_and_sequences()
        return jsonify({
            "success": True,
            "data": config
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/scenes', methods=['GET'])
def get_scenes():
    """Get all scenes"""
    try:
        config = load_scenes_and_sequences()
        scenes = config.get('scenes', {})
        return jsonify({
            "success": True,
            "data": scenes,
            "count": len(scenes)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/scenes/<scene_name>', methods=['GET'])
def get_scene(scene_name: str):
    """Get a specific scene"""
    try:
        config = load_scenes_and_sequences()
        scenes = config.get('scenes', {})
        
        if scene_name not in scenes:
            return jsonify({
                "success": False,
                "error": f"Scene '{scene_name}' not found"
            }), 404
        
        return jsonify({
            "success": True,
            "data": {
                "name": scene_name,
                "channels": scenes[scene_name]
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/scenes', methods=['POST'])
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
        
        config = load_scenes_and_sequences()
        config['scenes'][scene_name] = channels
        
        if save_scenes_and_sequences(config):
            return jsonify({
                "success": True,
                "message": f"Scene '{scene_name}' created successfully",
                "data": {
                    "name": scene_name,
                    "channels": channels
                }
            }), 201
        else:
            return jsonify({
                "success": False,
                "error": "Failed to save configuration"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/scenes/<scene_name>', methods=['PUT'])
def update_scene(scene_name: str):
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
        
        config = load_scenes_and_sequences()
        
        if scene_name not in config.get('scenes', {}):
            return jsonify({
                "success": False,
                "error": f"Scene '{scene_name}' not found"
            }), 404
        
        config['scenes'][scene_name] = channels
        
        if save_scenes_and_sequences(config):
            return jsonify({
                "success": True,
                "message": f"Scene '{scene_name}' updated successfully",
                "data": {
                    "name": scene_name,
                    "channels": channels
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to save configuration"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/scenes/<scene_name>', methods=['DELETE'])
def delete_scene(scene_name: str):
    """Delete a scene"""
    try:
        config = load_scenes_and_sequences()
        
        if scene_name not in config.get('scenes', {}):
            return jsonify({
                "success": False,
                "error": f"Scene '{scene_name}' not found"
            }), 404
        
        deleted_channels = config['scenes'].pop(scene_name)
        
        if save_scenes_and_sequences(config):
            return jsonify({
                "success": True,
                "message": f"Scene '{scene_name}' deleted successfully",
                "data": {
                    "name": scene_name,
                    "channels": deleted_channels
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to save configuration"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/sequences', methods=['GET'])
def get_sequences():
    """Get all sequences"""
    try:
        config = load_scenes_and_sequences()
        sequences = config.get('sequences', {})
        return jsonify({
            "success": True,
            "data": sequences,
            "count": len(sequences)
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/sequences/<sequence_name>', methods=['GET'])
def get_sequence(sequence_name: str):
    """Get a specific sequence"""
    try:
        config = load_scenes_and_sequences()
        sequences = config.get('sequences', {})
        
        if sequence_name not in sequences:
            return jsonify({
                "success": False,
                "error": f"Sequence '{sequence_name}' not found"
            }), 404
        
        return jsonify({
            "success": True,
            "data": {
                "name": sequence_name,
                "steps": sequences[sequence_name]
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/sequences', methods=['POST'])
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
        
        # Validate each step
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                return jsonify({
                    "success": False,
                    "error": f"Step {i+1} must be an object"
                }), 400
            
            if 'dmx' not in step:
                return jsonify({
                    "success": False,
                    "error": f"Step {i+1} missing required field: dmx"
                }), 400
            
            if 'duration' not in step:
                return jsonify({
                    "success": False,
                    "error": f"Step {i+1} missing required field: duration"
                }), 400
            
            # Validate DMX data
            dmx_data = step['dmx']
            if not isinstance(dmx_data, dict):
                return jsonify({
                    "success": False,
                    "error": f"Step {i+1} dmx field must be an object"
                }), 400
            
            for channel, value in dmx_data.items():
                try:
                    channel_num = int(channel)
                    if channel_num < 1 or channel_num > 512:
                        return jsonify({
                            "success": False,
                            "error": f"Step {i+1} channel {channel} must be 1-512"
                        }), 400
                except ValueError:
                    return jsonify({
                        "success": False,
                        "error": f"Step {i+1} channel {channel} must be a number"
                    }), 400
                
                if not isinstance(value, int) or value < 0 or value > 255:
                    return jsonify({
                        "success": False,
                        "error": f"Step {i+1} channel {channel} value must be 0-255"
                    }), 400
            
            # Validate duration
            try:
                duration = float(step['duration'])
                if duration < 0:
                    return jsonify({
                        "success": False,
                        "error": f"Step {i+1} duration must be non-negative"
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    "success": False,
                    "error": f"Step {i+1} duration must be a number"
                }), 400
        
        config = load_scenes_and_sequences()
        config['sequences'][sequence_name] = steps
        
        if save_scenes_and_sequences(config):
            return jsonify({
                "success": True,
                "message": f"Sequence '{sequence_name}' created successfully",
                "data": {
                    "name": sequence_name,
                    "steps": steps
                }
            }), 201
        else:
            return jsonify({
                "success": False,
                "error": "Failed to save configuration"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/sequences/<sequence_name>', methods=['PUT'])
def update_sequence(sequence_name: str):
    """Update an existing sequence"""
    try:
        data = request.get_json()
        
        if not data or 'steps' not in data:
            return jsonify({
                "success": False,
                "error": "Missing required field: steps"
            }), 400
        
        steps = data['steps']
        
        # Validate steps (same validation as create_sequence)
        if not isinstance(steps, list):
            return jsonify({
                "success": False,
                "error": "Steps must be a list"
            }), 400
        
        # Validate each step
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                return jsonify({
                    "success": False,
                    "error": f"Step {i+1} must be an object"
                }), 400
            
            if 'dmx' not in step:
                return jsonify({
                    "success": False,
                    "error": f"Step {i+1} missing required field: dmx"
                }), 400
            
            if 'duration' not in step:
                return jsonify({
                    "success": False,
                    "error": f"Step {i+1} missing required field: duration"
                }), 400
            
            # Validate DMX data
            dmx_data = step['dmx']
            if not isinstance(dmx_data, dict):
                return jsonify({
                    "success": False,
                    "error": f"Step {i+1} dmx field must be an object"
                }), 400
            
            for channel, value in dmx_data.items():
                try:
                    channel_num = int(channel)
                    if channel_num < 1 or channel_num > 512:
                        return jsonify({
                            "success": False,
                            "error": f"Step {i+1} channel {channel} must be 1-512"
                        }), 400
                except ValueError:
                    return jsonify({
                        "success": False,
                        "error": f"Step {i+1} channel {channel} must be a number"
                    }), 400
                
                if not isinstance(value, int) or value < 0 or value > 255:
                    return jsonify({
                        "success": False,
                        "error": f"Step {i+1} channel {channel} value must be 0-255"
                    }), 400
            
            # Validate duration
            try:
                duration = float(step['duration'])
                if duration < 0:
                    return jsonify({
                        "success": False,
                        "error": f"Step {i+1} duration must be non-negative"
                    }), 400
            except (ValueError, TypeError):
                return jsonify({
                    "success": False,
                    "error": f"Step {i+1} duration must be a number"
                }), 400
        
        config = load_scenes_and_sequences()
        
        if sequence_name not in config.get('sequences', {}):
            return jsonify({
                "success": False,
                "error": f"Sequence '{sequence_name}' not found"
            }), 404
        
        config['sequences'][sequence_name] = steps
        
        if save_scenes_and_sequences(config):
            return jsonify({
                "success": True,
                "message": f"Sequence '{sequence_name}' updated successfully",
                "data": {
                    "name": sequence_name,
                    "steps": steps
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to save configuration"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/sequences/<sequence_name>', methods=['DELETE'])
def delete_sequence(sequence_name: str):
    """Delete a sequence"""
    try:
        config = load_scenes_and_sequences()
        
        if sequence_name not in config.get('sequences', {}):
            return jsonify({
                "success": False,
                "error": f"Sequence '{sequence_name}' not found"
            }), 404
        
        deleted_steps = config['sequences'].pop(sequence_name)
        
        if save_scenes_and_sequences(config):
            return jsonify({
                "success": True,
                "message": f"Sequence '{sequence_name}' deleted successfully",
                "data": {
                    "name": sequence_name,
                    "steps": deleted_steps
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to save configuration"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/dmx/channel/<int:channel>', methods=['POST'])
def set_channel(channel: int):
    """Set a specific DMX channel value"""
    try:
        data = request.get_json()
        
        if not data or 'value' not in data:
            return jsonify({
                "success": False,
                "error": "Missing required field: value"
            }), 400
        
        value = data['value']
        
        if not isinstance(value, int) or value < 0 or value > 255:
            return jsonify({
                "success": False,
                "error": "Value must be 0-255"
            }), 400
        
        if channel < 1 or channel > 512:
            return jsonify({
                "success": False,
                "error": "Channel must be 1-512"
            }), 400
        
        # TODO: Integrate with MQTT to send the channel command
        # For now, just return success
        return jsonify({
            "success": True,
            "message": f"Channel {channel} set to {value}",
            "data": {
                "channel": channel,
                "value": value
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/dmx/scene/<scene_name>', methods=['POST'])
def play_scene(scene_name: str):
    """Play a scene via API"""
    try:
        data = request.get_json() or {}
        transition_time = data.get('transition_time', 0.0)
        
        config = load_scenes_and_sequences()
        scenes = config.get('scenes', {})
        
        if scene_name not in scenes:
            return jsonify({
                "success": False,
                "error": f"Scene '{scene_name}' not found"
            }), 404
        
        # TODO: Integrate with MQTT to send the scene command
        # For now, just return success
        return jsonify({
            "success": True,
            "message": f"Scene '{scene_name}' triggered with transition time {transition_time}s",
            "data": {
                "scene": scene_name,
                "transition_time": transition_time,
                "channels": scenes[scene_name]
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/dmx/sequence/<sequence_name>', methods=['POST'])
def play_sequence(sequence_name: str):
    """Play a sequence via API"""
    try:
        config = load_scenes_and_sequences()
        sequences = config.get('sequences', {})
        
        if sequence_name not in sequences:
            return jsonify({
                "success": False,
                "error": f"Sequence '{sequence_name}' not found"
            }), 404
        
        # TODO: Integrate with MQTT to send the sequence command
        # For now, just return success
        return jsonify({
            "success": True,
            "message": f"Sequence '{sequence_name}' triggered",
            "data": {
                "sequence": sequence_name,
                "steps": sequences[sequence_name]
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Flask API Server for MQTT DMX Sequencer')
    parser.add_argument('--config-dir', help='Directory containing settings.json and config.json files')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind to (default: 5000)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # Load configuration
    load_config_files(args.config_dir)
    
    print(f"Starting Flask API server on {args.host}:{args.port}")
    print(f"Configuration directory: {args.config_dir or 'default'}")
    
    app.run(host=args.host, port=args.port, debug=args.debug) 
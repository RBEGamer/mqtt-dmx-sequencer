# MQTT DMX Sequencer (Python)

> Control DMX devices via Art-Net or E1.31 by MQTT with Python.

A Python implementation of the MQTT DMX Sequencer that allows you to control DMX devices through MQTT messages. Supports both Art-Net and E1.31 protocols for DMX output with the ability to run multiple DMX senders simultaneously and comprehensive configuration management.

## Features

- **Individual Channel Control**: Set specific DMX channels via MQTT
- **Scene Switching**: Apply predefined scenes with optional transition times
- **Sequence Playback**: Play complex sequences with timing
- **Multiple DMX Protocols**: Support for both Art-Net and E1.31
- **Multiple DMX Outputs**: Run multiple DMX senders simultaneously
- **Modular Architecture**: Clean separation of DMX sender implementations
- **Configuration Management**: Comprehensive settings management via JSON files
- **MQTT Integration**: Full MQTT control with topic-based commands
- **Sender Management**: Add, remove, and manage DMX senders via MQTT

## Requirements

- Python 3.6+
- MQTT broker (e.g., Mosquitto)
- DMX devices supporting Art-Net or E1.31

## Installation

1. Clone or download this repository
2. Install required dependencies:

```bash
pip install paho-mqtt pyartnet sacn
```

## Project Structure

```
mqtt-dmx-sequencer/
├── mqtt-dmx-sequencer/      # Python package
│   ├── __init__.py
│   ├── main.py             # Main application
│   ├── dmx_senders.py      # DMX sender implementations
│   ├── config_manager.py   # Configuration management
│   ├── settings.json       # Application settings
│   └── config.json         # Scenes and sequences
├── config/                 # Configuration directory (optional)
├── mosquitto/              # MQTT broker configuration
├── run.py                  # Launcher script
├── Dockerfile
├── docker-compose.yaml
└── README.md
```

## Configuration

The application uses two configuration files:

### 1. Settings Configuration (`settings.json`)

This file contains all application settings including MQTT and DMX configurations:

```json
{
  "mqtt": {
    "url": "mqtt://192.168.178.75",
    "port": 1883,
    "username": "",
    "password": "",
    "client_id": "mqtt-dmx-sequencer",
    "keepalive": 60,
    "clean_session": true
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
      "multicast": true
    }
  },
  "logging": {
    "level": "info",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  },
  "scenes": {
    "default_transition_time": 0.0,
    "auto_send": true
  },
  "sequences": {
    "default_duration": 1.0,
    "auto_play": true
  }
}
```

#### MQTT Configuration
- **url**: MQTT broker URL
- **port**: MQTT broker port
- **username/password**: Authentication credentials (optional)
- **client_id**: Unique client identifier
- **keepalive**: Connection keepalive interval
- **clean_session**: Whether to use clean session

#### DMX Configuration
- **default_configs**: Array of DMX sender configurations
- **artnet**: Art-Net protocol settings
- **e131**: E1.31 protocol settings

#### DMX Sender Configuration Format
```json
{
  "type": "e131",           // "artnet" or "e131"
  "name": "main",           // Unique sender name
  "target": "192.168.1.100", // Target IP address
  "universe": 1,            // DMX universe number
  "fps": 40,               // FPS for E1.31 (optional)
  "port": 6454             // Port for Art-Net (optional)
}
```

### 2. Scenes and Sequences (`config.json`)

This file contains scene and sequence definitions:

```json
{
  "scenes": {
    "blackout": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "led white": [255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0],
    "led red": [255, 0, 255, 255, 255, 0, 255, 255, 255, 0, 255, 255, 255, 0, 255, 255, 255, 0, 255, 255, 255, 0, 255, 255]
  },
  "sequences": {
    "scene/intro": [
      { "dmx": { "1": 255, "2": 128 }, "duration": 2 },
      { "dmx": { "1": 0, "2": 255 }, "duration": 3 }
    ]
  }
}
```

### Scene Format
- Array where index 0 = Channel 1, index 1 = Channel 2, etc.
- Values: 0-255 (DMX levels)
- Use `null` to skip a channel (don't change it)

### Sequence Format
- Array of steps with DMX values and durations
- Each step contains `dmx` object (channel: value) and `duration` in seconds

## Usage

### Basic Usage

```bash
# Use default configuration files in current directory
python run.py

# Use configuration files from specific directory
python run.py --config-dir /path/to/config/directory

# Show current configuration
python run.py --show-config

# Run directly from package directory (alternative)
python mqtt-dmx-sequencer/main.py
```

### Command Line Options

```
--config-dir PATH       Directory containing settings.json and config.json files (default: script directory)
--show-config           Show current configuration and exit
```

### Configuration Directory Structure

The application expects the following files in the configuration directory:

```
config-directory/
├── settings.json       # Application settings (MQTT, DMX, etc.)
└── config.json         # Scenes and sequences definitions
```

### Examples

```bash
# Use default configuration (current directory)
python run.py

# Use configuration from custom directory
python run.py --config-dir /etc/mqtt-dmx-sequencer

# Use configuration from user's home directory
python run.py --config-dir ~/.mqtt-dmx-sequencer

# Show configuration without starting the application
python run.py --show-config
```

### Multiple DMX Senders Example

Edit `settings.json` to configure multiple DMX senders:

```json
{
  "dmx": {
    "default_configs": [
      {
        "type": "e131",
        "name": "stage",
        "target": "192.168.1.10",
        "universe": 1,
        "fps": 40
      },
      {
        "type": "artnet",
        "name": "backdrop",
        "target": "192.168.1.20",
        "universe": 2,
        "port": 6454
      }
    ]
  }
}
```

## MQTT Topics

### Individual Channel Control

**Topic**: `dmx/set/channel/{channel_number}`  
**Payload**: `{value}` (0-255)

Set a specific DMX channel to a value on all active senders.

**Examples**:
```bash
# Set channel 1 to full intensity on all senders
mosquitto_pub -h 192.168.178.75 -t "dmx/set/channel/1" -m "255"

# Set channel 5 to half intensity on all senders
mosquitto_pub -h 192.168.178.75 -t "dmx/set/channel/5" -m "128"
```

### Scene Control

**Topic**: `dmx/scene/{scene_name}`  
**Payload**: `{transition_time}` (optional, seconds)

Apply a predefined scene with optional transition time to all active senders.

**Examples**:
```bash
# Apply blackout scene immediately to all senders
mosquitto_pub -h 192.168.178.75 -t "dmx/scene/blackout" -m ""

# Apply white LED scene with 2-second transition to all senders
mosquitto_pub -h 192.168.178.75 -t "dmx/scene/led white" -m "2.0"
```

### Sequence Control

**Topic**: `{sequence_name}` (as defined in config.json)  
**Payload**: Any (triggers sequence playback)

Play a predefined sequence on all active senders.

**Examples**:
```bash
# Play intro sequence on all senders
mosquitto_pub -h 192.168.178.75 -t "scene/intro" -m "play"
```

### DMX Sender Management

**Topic**: `dmx/sender/{action}[/{sender_name}]`  
**Payload**: Any (triggers action)

Manage DMX senders via MQTT.

**Actions**:
- `dmx/sender/status` - Get status of all senders
- `dmx/sender/list` - List all active senders
- `dmx/sender/blackout` - Blackout all senders
- `dmx/sender/blackout/{sender_name}` - Blackout specific sender
- `dmx/sender/remove/{sender_name}` - Remove specific sender

**Examples**:
```bash
# Get status of all senders
mosquitto_pub -h 192.168.178.75 -t "dmx/sender/status" -m ""

# List all active senders
mosquitto_pub -h 192.168.178.75 -t "dmx/sender/list" -m ""

# Blackout all senders
mosquitto_pub -h 192.168.178.75 -t "dmx/sender/blackout" -m ""

# Blackout specific sender
mosquitto_pub -h 192.168.178.75 -t "dmx/sender/blackout/stage" -m ""

# Remove specific sender
mosquitto_pub -h 192.168.178.75 -t "dmx/sender/remove/backdrop" -m ""
```

### Configuration Management

**Topic**: `dmx/config/{action}`  
**Payload**: Any (triggers action)

Manage application configuration via MQTT.

**Actions**:
- `dmx/config/show` - Show current configuration
- `dmx/config/reload` - Reload configuration from file
- `dmx/config/save` - Save current configuration to file

**Examples**:
```bash
# Show current configuration
mosquitto_pub -h 192.168.178.75 -t "dmx/config/show" -m ""

# Reload configuration from file
mosquitto_pub -h 192.168.178.75 -t "dmx/config/reload" -m ""

# Save current configuration
mosquitto_pub -h 192.168.178.75 -t "dmx/config/save" -m ""
```

## DMX Protocol Support

### Art-Net
- Protocol: Art-Net 3
- Default port: 6454
- Multicast support
- Compatible with most professional lighting systems

### E1.31 (sACN)
- Protocol: ANSI E1.31 (Streaming ACN)
- Default port: 5568
- Multicast support
- Compatible with many LED controllers and lighting systems

## Architecture

The application uses a modular architecture with the following components:

### Configuration Management (`mqtt-dmx-sequencer/config_manager.py`)
- **ConfigManager**: Manages application settings
- Loads and saves configuration from JSON files
- Validates configuration data
- Merges command line arguments with settings

### DMX Senders Module (`mqtt-dmx-sequencer/dmx_senders.py`)
- **DMXSender**: Abstract base class for all DMX senders
- **ArtNetSender**: Art-Net protocol implementation
- **E131Sender**: E1.31 protocol implementation
- **DMXManager**: Manages multiple DMX senders

### Main Application (`mqtt-dmx-sequencer/main.py`)
- **MQTTDMXSequencer**: Main application class
- Handles MQTT communication
- Manages scenes and sequences
- Coordinates multiple DMX senders
- Integrates with configuration management

## Troubleshooting

### Common Issues

1. **MQTT Connection Failed**
   - Check MQTT broker is running
   - Verify broker URL and port in settings.json
   - Check network connectivity
   - Verify authentication credentials if required

2. **DMX Not Working**
   - Verify DMX device IP address in settings.json
   - Check universe number matches device
   - Ensure device supports chosen protocol (Art-Net or E1.31)
   - Check protocol-specific settings (port, fps, etc.)

3. **Scene/Sequence Not Found**
   - Check scene/sequence name in config.json
   - Verify JSON syntax is correct
   - Restart application after config changes

4. **Multiple Senders Not Working**
   - Verify each sender has a unique name in settings.json
   - Check that target IPs are correct
   - Ensure universe numbers don't conflict
   - Validate DMX configurations using `--show-config`

5. **Configuration Issues**
   - Check JSON syntax in settings.json and config.json
   - Use `--show-config` to verify current settings
   - Reload configuration via MQTT: `dmx/config/reload`

### Debug Mode

Run with verbose logging to troubleshoot:

```bash
python run.py --verbosity debug
```

### Configuration Verification

Check the current configuration:

```bash
# Show configuration from command line
python run.py --show-config

# Show configuration via MQTT
mosquitto_pub -h 192.168.178.75 -t "dmx/config/show" -m ""
```

### Sender Status

Check the status of all DMX senders:

```bash
mosquitto_pub -h 192.168.178.75 -t "dmx/sender/status" -m ""
```

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## Acknowledgments

- Original Node.js implementation by Sebastian Raff
- Art-Net support via pyartnet library
- E1.31 support via sacn library
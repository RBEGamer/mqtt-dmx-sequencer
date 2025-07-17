# MQTT DMX Sequencer

A powerful Python-based DMX controller with MQTT integration, modern WebUI, programmable scenes, and advanced automation features. Supports Art-Net and E1.31 (sACN) protocols, multi-sender output, and full configuration via JSON and WebUI.

---

## Features

- **WebUI**: Modern web interface for live channel control, scene/sequence/programmable scene editing, playback, and configuration (autostart, fallback, retransmit, followers, etc.)
- **Individual Channel Control**: Set DMX channels via MQTT or WebUI
- **Scene Management**: Create, edit, and trigger scenes with optional transitions
- **Sequence Playback**: Design and play step-based sequences with timing and looping
- **Programmable Scenes**: Use mathematical expressions (including HSV color math) for dynamic effects
- **Multiple DMX Protocols**: Art-Net and E1.31 (sACN) support
- **Multi-Sender Output**: Drive multiple universes/outputs simultaneously
- **MQTT Integration**: Full topic-based control for automation and remote integration
- **Channel Followers**: Mirror/follow channel values for grouped fixtures
- **DMX Retransmit**: Periodic DMX resend to keep late-joining devices in sync
- **Fallback Scenes/Sequences**: Auto-trigger fallback after inactivity
- **Autostart**: Automatically start a scene/sequence/programmable scene on boot
- **Docker Support**: Easy deployment and multi-instance synchronization via MQTT
- **Extensible**: Modular Python codebase, easy to add new features

---

## WebUI

![WebUI Screenshot](documentation/images/Screenshot%202025-07-15%20at%2001.05.30.png)

- **Live Channel Faders**: Adjust DMX channels in real time
- **Scene/Sequence/Programmable Scene Editor**: Create, edit, and organize all show elements
- **Playback Controls**: Play, pause, stop, and monitor current playback
- **Settings**: Configure retransmit, autostart, fallback, followers, and more
- **Status Panels**: See current playback, DMX output, and system health

Access the WebUI at:  
`http://<your-server-ip>:5001`

---

## Programmable Scenes

- Use mathematical expressions for channel values (e.g., sine, cosine, HSV color cycling)
- Supported functions: `sin`, `cos`, `tan`, `abs`, `min`, `max`, `round`, `sqrt`, `pow`, `floor`, `ceil`, `log`, `exp`, `mod`, `clamp`, and more
- **HSV Color Helpers**:
  - `hsv_to_rgb(h, s, v)` → returns `(r, g, b)` tuple
  - `hsv_to_rgb_r(h, s, v)` → red channel only
  - `hsv_to_rgb_g(h, s, v)` → green channel only
  - `hsv_to_rgb_b(h, s, v)` → blue channel only

**Example:**
```json
{
  "7": "hsv_to_rgb_r(t*36, 1, 1)",
  "8": "hsv_to_rgb_g(t*36, 1, 1)",
  "9": "hsv_to_rgb_b(t*36, 1, 1)"
}
```
This will smoothly animate RGB channels 7, 8, 9 through the HSV color wheel.

---

## MQTT Topics

- **Channel**: `dmx/set/channel/{channel}` (payload: 0-255)
- **Scene**: `dmx/scene/{scene_name}` (payload: transition time, optional)
- **Sequence**: `{sequence_name}` (payload: any)
- **Sender Management**: `dmx/sender/{action}` (status, list, blackout, remove)
- **Config Management**: `dmx/config/{action}` (show, reload, save)

See full topic list and examples in the MQTT section below.

---

## Configuration

- **settings.json**: MQTT, DMX sender, and global settings
- **config.json**: Scenes, sequences, programmable scenes

See the Configuration section for file formats and examples.

---

## Installation & Usage

### Python
```bash
python3 -m venv .venv
source .venv/bin/activate
cd mqtt-dmx-sequencer
pip install -r requirements.txt
python run.py
```

### Docker
```bash
docker build -t mqtt-dmx-sequencer .
docker run --rm --network host -v config-directory:/app/config mqtt-dmx-sequencer
# or
docker compose up
```

### Command Line Options
- `--config-dir PATH` : Use custom config directory
- `--show-config` : Print current config and exit

---

## Advanced Features

- **Channel Followers**: Configure channels to follow others (great for grouped fixtures)
- **DMX Retransmit**: Periodically resend DMX to keep all devices in sync
- **Fallback**: Auto-trigger a scene/sequence after inactivity
- **Autostart**: Start a scene/sequence/programmable scene on boot
- **Multi-Instance**: Synchronize multiple instances via MQTT

---

## Project Structure

```
mqtt-dmx-sequencer/
├── mqtt-dmx-sequencer/      # Python package
│   ├── __init__.py
│   ├── main.py             # Main application
│   ├── dmx_senders.py      # DMX sender implementations
│   ├── config_manager.py   # Configuration management
│   ├── settings.json       # Application settings
│   └── config.json         # Scenes, sequences, programmable scenes
├── docker-compose.yaml
└── README.md
```

---

## Configuration Details

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

### 2. Scenes, Sequences, and Programmable Scenes (`config.json`)

This file contains scene, sequence, and programmable scene definitions:

```json
{
  "scenes": {
    "blackout": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "led white": [255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0, 255, 0, 0, 0]
  },
  "sequences": {
    "scene/intro": [
      { "dmx": { "1": 255, "2": 128 }, "duration": 2 },
      { "dmx": { "1": 0, "2": 255 }, "duration": 3 }
    ]
  },
  "programmable_scenes": {
    "hsv_fade_example": {
      "name": "HSV Fade Example",
      "duration": 10000,
      "loop": true,
      "expressions": {
        "7": "hsv_to_rgb_r(t*36, 1, 1)",
        "8": "hsv_to_rgb_g(t*36, 1, 1)",
        "9": "hsv_to_rgb_b(t*36, 1, 1)"
      }
    }
  }
}
```

---

## MQTT Topics (Detailed)

### Individual Channel Control

**Topic**: `dmx/set/channel/{channel_number}`  
**Payload**: `{value}` (0-255)

Set a specific DMX channel to a value on all active senders.

**Examples**:
```bash
mosquitto_pub -h 192.168.178.75 -t "dmx/set/channel/1" -m "255"
mosquitto_pub -h 192.168.178.75 -t "dmx/set/channel/5" -m "128"
```

### Scene Control

**Topic**: `dmx/scene/{scene_name}`  
**Payload**: `{transition_time}` (optional, seconds)

**Examples**:
```bash
mosquitto_pub -h 192.168.178.75 -t "dmx/scene/blackout" -m ""
mosquitto_pub -h 192.168.178.75 -t "dmx/scene/led white" -m "2.0"
```

### Sequence Control

**Topic**: `{sequence_name}` (as defined in config.json)  
**Payload**: Any (triggers sequence playback)

**Examples**:
```bash
mosquitto_pub -h 192.168.178.75 -t "scene/intro" -m "play"
```

### DMX Sender Management

**Topic**: `dmx/sender/{action}[/{sender_name}]`  
**Payload**: Any (triggers action)

**Actions**:
- `dmx/sender/status` - Get status of all senders
- `dmx/sender/list` - List all active senders
- `dmx/sender/blackout` - Blackout all senders
- `dmx/sender/blackout/{sender_name}` - Blackout specific sender
- `dmx/sender/remove/{sender_name}` - Remove specific sender

**Examples**:
```bash
mosquitto_pub -h 192.168.178.75 -t "dmx/sender/status" -m ""
mosquitto_pub -h 192.168.178.75 -t "dmx/sender/list" -m ""
mosquitto_pub -h 192.168.178.75 -t "dmx/sender/blackout" -m ""
mosquitto_pub -h 192.168.178.75 -t "dmx/sender/blackout/stage" -m ""
mosquitto_pub -h 192.168.178.75 -t "dmx/sender/remove/backdrop" -m ""
```

### Configuration Management

**Topic**: `dmx/config/{action}`  
**Payload**: Any (triggers action)

**Actions**:
- `dmx/config/show` - Show current configuration
- `dmx/config/reload` - Reload configuration from file
- `dmx/config/save` - Save current configuration to file

**Examples**:
```bash
mosquitto_pub -h 192.168.178.75 -t "dmx/config/show" -m ""
mosquitto_pub -h 192.168.178.75 -t "dmx/config/reload" -m ""
mosquitto_pub -h 192.168.178.75 -t "dmx/config/save" -m ""
```

---

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

---

## Troubleshooting

See the Troubleshooting section above for common issues and solutions.

---

## License

MIT License

---

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

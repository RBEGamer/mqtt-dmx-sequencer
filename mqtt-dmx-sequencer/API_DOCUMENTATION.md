# MQTT DMX Sequencer API Documentation

## Overview

The Flask API server provides REST endpoints to manage scenes and sequences for the MQTT DMX Sequencer. The API allows you to create, read, update, and delete scenes and sequences, as well as trigger DMX commands.

## Base URL

```
http://localhost:5000/api
```

## Endpoints

### Health Check

**GET** `/api/health`

Returns the health status of the API server.

**Response:**
```json
{
  "status": "healthy",
  "service": "mqtt-dmx-sequencer-api",
  "version": "1.0.0"
}
```

### Configuration

**GET** `/api/config`

Returns the complete configuration including all scenes and sequences.

**Response:**
```json
{
  "success": true,
  "data": {
    "scenes": { ... },
    "sequences": { ... }
  }
}
```

### Scenes

#### Get All Scenes

**GET** `/api/scenes`

Returns all available scenes.

**Response:**
```json
{
  "success": true,
  "data": {
    "scene_name": [channel_values],
    ...
  },
  "count": 5
}
```

#### Get Specific Scene

**GET** `/api/scenes/{scene_name}`

Returns a specific scene by name.

**Response:**
```json
{
  "success": true,
  "data": {
    "name": "scene_name",
    "channels": [channel_values]
  }
}
```

#### Create Scene

**POST** `/api/scenes`

Creates a new scene.

**Request Body:**
```json
{
  "name": "scene_name",
  "channels": [255, 128, 64, 0, ...]
}
```

**Response:**
```json
{
  "success": true,
  "message": "Scene 'scene_name' created successfully",
  "data": {
    "name": "scene_name",
    "channels": [channel_values]
  }
}
```

#### Update Scene

**PUT** `/api/scenes/{scene_name}`

Updates an existing scene.

**Request Body:**
```json
{
  "channels": [255, 128, 64, 0, ...]
}
```

**Response:**
```json
{
  "success": true,
  "message": "Scene 'scene_name' updated successfully",
  "data": {
    "name": "scene_name",
    "channels": [channel_values]
  }
}
```

#### Delete Scene

**DELETE** `/api/scenes/{scene_name}`

Deletes a scene.

**Response:**
```json
{
  "success": true,
  "message": "Scene 'scene_name' deleted successfully",
  "data": {
    "name": "scene_name",
    "channels": [channel_values]
  }
}
```

### Sequences

#### Get All Sequences

**GET** `/api/sequences`

Returns all available sequences.

**Response:**
```json
{
  "success": true,
  "data": {
    "sequence_name": [steps],
    ...
  },
  "count": 2
}
```

#### Get Specific Sequence

**GET** `/api/sequences/{sequence_name}`

Returns a specific sequence by name.

**Response:**
```json
{
  "success": true,
  "data": {
    "name": "sequence_name",
    "steps": [
      {
        "dmx": {"1": 255, "2": 0},
        "duration": 2.0
      },
      ...
    ]
  }
}
```

#### Create Sequence

**POST** `/api/sequences`

Creates a new sequence.

**Request Body:**
```json
{
  "name": "sequence_name",
  "steps": [
    {
      "dmx": {"1": 255, "2": 0},
      "duration": 2.0
    },
    {
      "dmx": {"1": 0, "2": 255},
      "duration": 3.0
    }
  ]
}
```

**Response:**
```json
{
  "success": true,
  "message": "Sequence 'sequence_name' created successfully",
  "data": {
    "name": "sequence_name",
    "steps": [steps]
  }
}
```

#### Update Sequence

**PUT** `/api/sequences/{sequence_name}`

Updates an existing sequence.

**Request Body:**
```json
{
  "steps": [
    {
      "dmx": {"1": 255, "2": 0},
      "duration": 2.0
    },
    ...
  ]
}
```

**Response:**
```json
{
  "success": true,
  "message": "Sequence 'sequence_name' updated successfully",
  "data": {
    "name": "sequence_name",
    "steps": [steps]
  }
}
```

#### Delete Sequence

**DELETE** `/api/sequences/{sequence_name}`

Deletes a sequence.

**Response:**
```json
{
  "success": true,
  "message": "Sequence 'sequence_name' deleted successfully",
  "data": {
    "name": "sequence_name",
    "steps": [steps]
  }
}
```

### DMX Control

#### Set Channel

**POST** `/api/dmx/channel/{channel}`

Sets a specific DMX channel value.

**Request Body:**
```json
{
  "value": 255
}
```

**Response:**
```json
{
  "success": true,
  "message": "Channel 1 set to 255",
  "data": {
    "channel": 1,
    "value": 255
  }
}
```

#### Play Scene

**POST** `/api/dmx/scene/{scene_name}`

Triggers a scene to play.

**Request Body (optional):**
```json
{
  "transition_time": 1.5
}
```

**Response:**
```json
{
  "success": true,
  "message": "Scene 'scene_name' triggered with transition time 1.5s",
  "data": {
    "scene": "scene_name",
    "transition_time": 1.5,
    "channels": [channel_values]
  }
}
```

#### Play Sequence

**POST** `/api/dmx/sequence/{sequence_name}`

Triggers a sequence to play.

**Response:**
```json
{
  "success": true,
  "message": "Sequence 'sequence_name' triggered",
  "data": {
    "sequence": "sequence_name",
    "steps": [steps]
  }
}
```

## Data Formats

### Scene Format

A scene is an array of channel values where:
- Index 0 = Channel 1, Index 1 = Channel 2, etc.
- Values: 0-255 (DMX levels)
- Use `null` to skip a channel (don't change it)

**Example:**
```json
[255, 128, 64, 0, 255, 0, 128, 0]
```

### Sequence Format

A sequence is an array of steps, where each step contains:
- `dmx`: Object with channel numbers as keys and values (0-255)
- `duration`: Time in seconds for this step

**Example:**
```json
[
  {
    "dmx": {"1": 255, "2": 0},
    "duration": 2.0
  },
  {
    "dmx": {"1": 0, "2": 255},
    "duration": 3.0
  }
]
```

## Error Responses

All endpoints return error responses in the following format:

```json
{
  "success": false,
  "error": "Error message description"
}
```

Common HTTP status codes:
- `200`: Success
- `201`: Created
- `400`: Bad Request (validation error)
- `404`: Not Found
- `500`: Internal Server Error

## Usage Examples

### Using curl

```bash
# Get all scenes
curl http://localhost:5000/api/scenes

# Create a new scene
curl -X POST http://localhost:5000/api/scenes \
  -H "Content-Type: application/json" \
  -d '{"name": "my_scene", "channels": [255, 128, 64, 0]}'

# Play a scene
curl -X POST http://localhost:5000/api/dmx/scene/blackout \
  -H "Content-Type: application/json" \
  -d '{"transition_time": 2.0}'

# Set a channel
curl -X POST http://localhost:5000/api/dmx/channel/1 \
  -H "Content-Type: application/json" \
  -d '{"value": 255}'
```

### Using Python requests

```python
import requests

# Get all scenes
response = requests.get('http://localhost:5000/api/scenes')
scenes = response.json()['data']

# Create a scene
scene_data = {
    "name": "my_scene",
    "channels": [255, 128, 64, 0, 255, 0, 128, 0]
}
response = requests.post('http://localhost:5000/api/scenes', json=scene_data)

# Play a scene
play_data = {"transition_time": 1.5}
response = requests.post('http://localhost:5000/api/dmx/scene/my_scene', json=play_data)
```

## Starting the API Server

```bash
# Basic usage
python flask_server.py

# With custom configuration directory
python flask_server.py --config-dir /path/to/config

# With custom host and port
python flask_server.py --host 0.0.0.0 --port 8080

# With debug mode
python flask_server.py --debug
```

## Configuration

The API server uses the same configuration files as the main DMX sequencer:
- `settings.json`: Application settings
- `config.json`: Scenes and sequences

The API automatically loads and saves changes to these files. 
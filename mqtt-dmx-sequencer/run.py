#!/usr/bin/env python3
"""
Launcher script for MQTT DMX Sequencer
This script runs the main application from the src directory
"""

import sys
import os

# Add src directory to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(script_dir, '.')
sys.path.insert(0, src_dir)

# Import and run the main application
if __name__ == '__main__':
    # Execute the main application
    exec(open(os.path.join(src_dir, 'main.py')).read()) 
# Use official Node.js LTS base image
FROM node:18

# Set working directory
WORKDIR /usr/src/app

# Clone the repository
RUN git clone https://github.com/hobbyquaker/mqtt-dmx-sequencer.git .

# Install dependencies
RUN npm install

# Expose port (adjust if needed for MQTT or internal server)
EXPOSE 3000

# Define default command to run the application
CMD ["npm", "start"]

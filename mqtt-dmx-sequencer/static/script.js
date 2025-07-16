// MQTT DMX Sequencer Console JavaScript
class DMXConsole {
    constructor() {
        this.apiUrl = window.location.origin + '/api';
        this.channelCount = 24;
        this.currentChannels = new Array(512).fill(0);
        this.scenes = [];
        this.sequences = [];
        this.currentSequence = null;
        this.currentScene = null;
        this.currentProgrammableScene = null;
        this.isPlaying = false;
        this.currentStep = 0;
        this.currentStepData = null;
        this.stepStartTime = null;
        this.stepTimer = null;
        this.sequenceTimer = null;
        this.stepProgressTimer = null;
        this.autostartConfig = null;
        this.mqttPassthroughEnabled = false;
        this.fallbackConfig = null;
        this.programmableScenes = [];
        
        this.init();
    }

    async init() {
        await this.fetchMQTTPassthroughSetting();
        await this.loadBackendSettings();
        this.setupEventListeners();
        this.loadSettings();
        this.generateFaders();
        this.updateTime();
        this.testConnection();
        this.loadScenes();
        this.loadSequences();
        this.loadProgrammableScenes();
        this.loadAutostartConfig();
        this.loadFallbackConfig();
        // DMX retransmission settings
        await this.loadDMXRetransmissionSettings();
        this.setupDMXRetransmissionListeners();
        
        // Update fader visual states after everything is loaded
        await this.updateFaderVisualStates();
        
        // Setup fallback delay event listener after settings are loaded
        this.setupFallbackDelayListener();
        
        // Update time every second
        setInterval(() => this.updateTime(), 1000);
        
        // Sync sliders with current DMX state every 5 seconds
        setInterval(() => this.syncSlidersWithDMX(), 5000);
        
        // Poll for playback status every 500ms when playing
        setInterval(() => this.pollPlaybackStatus(), 500);
        
        // Poll for MQTT channel updates every 200ms
        setInterval(() => this.pollMQTTChannelUpdates(), 200);
    }

    async fetchMQTTPassthroughSetting() {
        try {
            const response = await fetch(`${this.apiUrl}/config`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data && typeof data.data.frontend_mqtt_passthrough !== 'undefined') {
                    this.mqttPassthroughEnabled = data.data.frontend_mqtt_passthrough;
                }
            }
        } catch (error) {
            // Ignore errors, default to false
        }
    }

    async loadBackendSettings() {
        try {
            const response = await fetch(`${this.apiUrl}/config`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    // Load fallback delay from backend settings
                    const fallbackDelay = data.data.fallback_delay || 1.0;
                    document.getElementById('fallback-delay').value = fallbackDelay;
                }
            }
        } catch (error) {
            console.error('Failed to load backend settings:', error);
        }
    }

    setupEventListeners() {
        // Panel tabs
        document.querySelectorAll('.panel-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                this.switchPanel(e.target.dataset.panel);
            });
        });

        // Modal close buttons
        document.querySelectorAll('.close').forEach(close => {
            close.addEventListener('click', (e) => {
                e.target.closest('.modal').style.display = 'none';
            });
        });

        // Close modals when clicking outside
        window.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal')) {
                e.target.style.display = 'none';
            }
        });

        // Settings changes
        document.getElementById('channel-count').addEventListener('change', (e) => {
            this.channelCount = parseInt(e.target.value);
            this.generateFaders();
            this.saveSettings();
        });
    }

    setupFallbackDelayListener() {
        const fallbackDelayInput = document.getElementById('fallback-delay');
        if (fallbackDelayInput) {
            // Remove any existing listeners to avoid duplicates
            fallbackDelayInput.removeEventListener('input', this.handleFallbackDelayChange);
            fallbackDelayInput.removeEventListener('change', this.handleFallbackDelayChange);
            
            // Add new listeners for both input and change events
            fallbackDelayInput.addEventListener('input', this.handleFallbackDelayChange.bind(this));
            fallbackDelayInput.addEventListener('change', this.handleFallbackDelayChange.bind(this));
        } else {
            console.error('Fallback delay input element not found');
        }
    }

    async handleFallbackDelayChange(e) {
        this.saveSettings();
        // Also save to backend
        await this.saveFallbackDelayToBackend();
    }

    switchPanel(panelName) {
        // Update tab buttons
        document.querySelectorAll('.panel-tab').forEach(tab => {
            tab.classList.remove('active');
        });
        document.querySelector(`[data-panel="${panelName}"]`).classList.add('active');

        // Update panel content
        document.querySelectorAll('.panel-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(`${panelName}-panel`).classList.add('active');
    }

    generateFaders() {
        const container = document.getElementById('fader-container');
        container.innerHTML = '';

        for (let i = 1; i <= this.channelCount; i++) {
            const fader = document.createElement('div');
            fader.className = 'dmx-fader';
            fader.dataset.channel = i; // Add data attribute for easier selection
            fader.innerHTML = `
                <div class="fader-label" data-fader-label="${i}">CH${i}</div>
                <input type="range" class="fader-slider" min="0" max="255" value="0" 
                       data-channel="${i}">
                <div class="fader-value">0</div>
            `;

            // Fader label click for follower editor
            const label = fader.querySelector('.fader-label');
            label.addEventListener('click', () => {
                this.openFollowerEditor(i);
            });

            const slider = fader.querySelector('.fader-slider');
            const valueDisplay = fader.querySelector('.fader-value');

            slider.addEventListener('input', async (e) => {
                const value = parseInt(e.target.value);
                const channel = parseInt(e.target.dataset.channel);
                // If a scene or sequence is playing, stop it before sending manual DMX
                if (this.isPlaying) {
                    await this.stopSequence();
                }
                this.currentChannels[channel - 1] = value;
                valueDisplay.textContent = value;
                this.sendDMXChannel(channel, value);
                
                // Sync follower channels
                this.syncFollowerChannels(channel, value);
                
                // MQTT passthrough
                if (this.mqttPassthroughEnabled) {
                    await this.sendMQTTPublish(`dmx/set/channel/${channel}`, value);
                }
            });

            container.appendChild(fader);
        }
        
        // Update visual states after generating faders
        this.updateFaderVisualStates();
    }

    async updateFaderVisualStates() {
        try {
            console.log('Updating fader visual states...');
            const response = await fetch(`${this.apiUrl}/settings/dmx-followers`);
            if (response.ok) {
                const data = await response.json();
                console.log('Follower data:', data);
                if (data.success && data.data && data.data.enabled) {
                    const mappings = data.data.mappings || {};
                    console.log('Mappings:', mappings);
                    
                    // Get all follower channels and their controllers
                    const allFollowers = new Set();
                    const followerControllers = new Map(); // follower -> controller
                    Object.entries(mappings).forEach(([controller, followers]) => {
                        followers.forEach(follower => {
                            allFollowers.add(follower);
                            followerControllers.set(follower, controller);
                        });
                    });
                    console.log('All followers:', Array.from(allFollowers));
                    console.log('Follower controllers:', Object.fromEntries(followerControllers));
                    
                    // Update each fader's visual state
                    for (let i = 1; i <= this.channelCount; i++) {
                        const fader = document.querySelector(`.dmx-fader[data-channel="${i}"]`);
                        if (fader) {
                            const hasFollowers = mappings[i] && mappings[i].length > 0;
                            const isFollower = allFollowers.has(i);
                            const controller = followerControllers.get(i);
                            
                            console.log(`Channel ${i}: hasFollowers=${hasFollowers}, isFollower=${isFollower}, controller=${controller}`);
                            
                            // Remove existing classes
                            fader.classList.remove('has-followers', 'is-follower');
                            
                            // Update channel label for followers
                            const label = fader.querySelector('.fader-label');
                            if (isFollower && controller) {
                                label.textContent = `CH${i} [CH${controller}]`;
                            } else {
                                label.textContent = `CH${i}`;
                            }
                            
                            // Add appropriate classes
                            if (hasFollowers) {
                                fader.classList.add('has-followers');
                                console.log(`Added has-followers to channel ${i}`);
                            }
                            if (isFollower) {
                                fader.classList.add('is-follower');
                                console.log(`Added is-follower to channel ${i}`);
                            }
                        } else {
                            console.log(`Fader not found for channel ${i}`);
                        }
                    }
                } else {
                    console.log('Followers disabled or no data');
                    // Clear all visual states if followers are disabled
                    document.querySelectorAll('.dmx-fader').forEach(fader => {
                        fader.classList.remove('has-followers', 'is-follower');
                        // Reset labels to original format
                        const label = fader.querySelector('.fader-label');
                        const channel = fader.dataset.channel;
                        if (label && channel) {
                            label.textContent = `CH${channel}`;
                        }
                    });
                }
            }
        } catch (error) {
            console.error('Failed to update fader visual states:', error);
        }
    }

    openFollowerEditor(channel) {
        // Load current mappings
        fetch(`${this.apiUrl}/settings/dmx-followers`).then(r => r.json()).then(data => {
            if (data.success && data.data) {
                const mappings = data.data.mappings || {};
                const followers = mappings[channel] || [];
                document.getElementById('follower-editor-channel').textContent = channel;
                document.getElementById('follower-editor-input').value = followers.join(',');
                document.getElementById('follower-editor-modal').style.display = 'block';
            }
        });
        // Setup modal listeners (only once)
        if (!this._followerEditorSetup) {
            document.getElementById('follower-editor-close').onclick = () => {
                document.getElementById('follower-editor-modal').style.display = 'none';
            };
            document.getElementById('follower-editor-cancel').onclick = () => {
                document.getElementById('follower-editor-modal').style.display = 'none';
            };
            document.getElementById('follower-editor-save').onclick = async () => {
                const ch = parseInt(document.getElementById('follower-editor-channel').textContent);
                const val = document.getElementById('follower-editor-input').value.trim();
                let arr = [];
                if (val) {
                    arr = val.split(',').map(x => parseInt(x.trim())).filter(x => !isNaN(x) && x !== ch);
                }
                console.log(`Saving followers for channel ${ch}:`, arr);
                
                // Get current settings
                let settings = await fetch(`${this.apiUrl}/settings/dmx-followers`).then(r => r.json());
                if (settings.success && settings.data) {
                    let mappings = settings.data.mappings || {};
                    let enabled = settings.data.enabled || false;
                    
                    if (arr.length > 0) {
                        mappings[ch] = arr;
                        enabled = true; // Auto-enable when mappings are added
                    } else {
                        delete mappings[ch];
                        // Check if any mappings remain
                        enabled = Object.keys(mappings).length > 0;
                    }
                    console.log('New mappings:', mappings);
                    console.log('Enabled:', enabled);
                    
                    // Save
                    const saveResponse = await fetch(`${this.apiUrl}/settings/dmx-followers`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ enabled: enabled, mappings })
                    });
                    
                    if (saveResponse.ok) {
                        this.showNotification('Follower channels updated', 'success');
                        
                        // Update visual states after saving
                        console.log('Triggering visual update after save...');
                        await this.updateFaderVisualStates();
                    } else {
                        this.showNotification('Failed to save follower settings', 'error');
                    }
                }
                document.getElementById('follower-editor-modal').style.display = 'none';
            };
            this._followerEditorSetup = true;
        }
    }

    // Manual refresh function for testing
    async refreshFaderVisuals() {
        console.log('Manual refresh triggered');
        await this.updateFaderVisualStates();
    }

    async syncFollowerChannels(sourceChannel, value) {
        try {
            const response = await fetch(`${this.apiUrl}/settings/dmx-followers`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data && data.data.enabled) {
                    const mappings = data.data.mappings || {};
                    const followers = mappings[sourceChannel] || [];
                    
                    // Update follower sliders
                    followers.forEach(followerChannel => {
                        const followerSlider = document.querySelector(`.fader-slider[data-channel="${followerChannel}"]`);
                        const followerValue = document.querySelector(`.fader-slider[data-channel="${followerChannel}"]`).nextElementSibling;
                        
                        if (followerSlider && followerValue) {
                            followerSlider.value = value;
                            followerValue.textContent = value;
                            this.currentChannels[followerChannel - 1] = value;
                        }
                    });
                }
            }
        } catch (error) {
            console.error('Failed to sync follower channels:', error);
        }
    }

    updateTime() {
        const now = new Date();
        const timeString = now.toLocaleTimeString();
        document.getElementById('current-time').textContent = timeString;
    }

    async testConnection() {
        try {
            const response = await fetch(`${this.apiUrl}/config`);
            if (response.ok) {
                this.updateConnectionStatus(true);
                this.showNotification('Connected to API', 'success');
            } else {
                throw new Error('API not responding');
            }
        } catch (error) {
            this.updateConnectionStatus(false);
            this.showNotification('Failed to connect to API', 'error');
        }
    }

    updateConnectionStatus(connected) {
        const status = document.getElementById('connection-status');
        if (connected) {
            status.className = 'connection-status connected';
            status.innerHTML = '<i class="fas fa-circle"></i> Connected';
        } else {
            status.className = 'connection-status offline';
            status.innerHTML = '<i class="fas fa-circle"></i> Offline';
        }
    }

    async sendDMXChannel(channel, value) {
        try {
            await fetch(`${this.apiUrl}/dmx/channel/${channel}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ value: value })
            });
        } catch (error) {
            console.error('Failed to send DMX channel:', error);
        }
    }

    async sendDMXAll(channels) {
        try {
            await fetch(`${this.apiUrl}/dmx/all`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channels: channels })
            });
        } catch (error) {
            console.error('Failed to send DMX all:', error);
        }
    }

    // DMX Control Functions
    async blackout() {
        try {
            const response = await fetch(`${this.apiUrl}/dmx/blackout`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (response.ok) {
                this.currentChannels.fill(0);
                this.updateAllFaders();
                this.showNotification('Blackout activated - all channels set to 0', 'warning');
            } else {
                throw new Error('Failed to activate blackout');
            }
        } catch (error) {
            console.error('Failed to activate blackout:', error);
            this.showNotification('Failed to activate blackout', 'error');
        }
    }

    setAllChannels(value) {
        this.currentChannels.fill(value);
        this.updateAllFaders();
        this.sendDMXAll(this.currentChannels);
        this.showNotification(`All channels set to ${value}`, 'success');
    }

    updateAllFaders() {
        document.querySelectorAll('.fader-slider').forEach((slider, index) => {
            if (index < this.channelCount) {
                slider.value = this.currentChannels[index];
                slider.nextElementSibling.textContent = this.currentChannels[index];
            }
        });
    }

    updateFaderFromChannel(channel, value) {
        // Update a specific fader when a channel value changes
        const slider = document.querySelector(`.fader-slider[data-channel="${channel}"]`);
        if (slider) {
            slider.value = value;
            slider.nextElementSibling.textContent = value;
        }
        // Also update the currentChannels array
        if (channel >= 1 && channel <= this.currentChannels.length) {
            this.currentChannels[channel - 1] = value;
        }
    }

    async syncSlidersWithDMX() {
        // This function could be used to sync sliders with current DMX state
        // For now, we'll just ensure the sliders reflect the currentChannels array
        this.updateAllFaders();
    }

    async pollPlaybackStatus() {
        try {
            const response = await fetch(`${this.apiUrl}/playback/status`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    const status = data.data;
                    console.log('[pollPlaybackStatus] status:', status); // DEBUG
                    // Sync frontend playing state with backend
                    const backendIsPlaying = status.is_playing;
                    if (backendIsPlaying !== this.isPlaying) {
                        this.isPlaying = backendIsPlaying;
                        this.updatePlaybackInfo();
                    }
                    
                    // Handle sequence playback
                    if (status.current_sequence && status.current_step !== undefined && status.step_data) {
                        this.currentSequence = status.current_sequence;
                        this.currentScene = null;
                        this.currentProgrammableScene = null;
                        this.currentStep = status.current_step;
                        this.currentStepData = status.step_data;
                        this.updateSequenceStepInfo(this.currentStep, this.currentStepData);
                        this.showSequenceStepInfo();
                        this.hideProgrammableSceneInfo();
                        
                        // Start progress tracking for current step
                        if (status.step_data.duration) {
                            this.startStepProgress(status.step_data);
                        }
                    }
                    // Handle programmable scene playback
                    else if (status.current_programmable_scene && status.step_data) {
                        this.currentProgrammableScene = status.current_programmable_scene;
                        this.currentScene = null;
                        this.currentSequence = null;
                        this.currentStepData = status.step_data;
                        this.showProgrammableSceneInfo();
                        this.hideSequenceStepInfo();
                        
                        // Update progress bar for programmable scene
                        if (status.step_progress !== undefined) {
                            this.updateProgrammableSceneProgress(status.step_progress);
                        }
                    }
                    // Handle regular scene playback
                    else if (status.current_scene && !status.current_sequence && !status.current_programmable_scene) {
                        this.currentScene = status.current_scene;
                        this.currentSequence = null;
                        this.currentProgrammableScene = null;
                        this.hideSequenceStepInfo();
                        this.hideProgrammableSceneInfo();
                    }
                    else if (!backendIsPlaying) {
                        // Hide all info if not playing
                        this.hideSequenceStepInfo();
                        this.hideProgrammableSceneInfo();
                        this.currentScene = null;
                        this.currentSequence = null;
                        this.currentProgrammableScene = null;
                    }
                }
            }
        } catch (error) {
            console.error('Failed to poll playback status:', error);
        }
    }

    async pollMQTTChannelUpdates() {
        try {
            const response = await fetch(`${this.apiUrl}/dmx/channel-update`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.update) {
                    const { channel, value } = data.update;
                    console.log(`MQTT channel update: ${channel} = ${value}`);
                    
                    // Update the frontend slider and internal state
                    this.updateFaderFromChannel(channel, value);
                    this.currentChannels[channel - 1] = value;
                }
            }
        } catch (error) {
            // Silently ignore errors for this polling endpoint
        }
    }

    async loadAutostartConfig() {
        try {
            const response = await fetch(`${this.apiUrl}/autostart`);
            if (response.ok) {
                const data = await response.json();
                this.autostartConfig = data.data;
                this.updateAutostartUI();
            }
        } catch (error) {
            console.error('Failed to load autostart config:', error);
        }
    }

    async setAutostart(type, id, enabled = true) {
        try {
            const response = await fetch(`${this.apiUrl}/autostart`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type, id, enabled })
            });
            
            if (response.ok) {
                await this.loadAutostartConfig();
                this.showNotification(`Autostart ${enabled ? 'enabled' : 'disabled'} for ${type}`, 'success');
                
                // Refresh UI to update autostart indicators
                this.renderScenes();
                this.renderSequences();
            } else {
                throw new Error('Failed to set autostart');
            }
        } catch (error) {
            console.error('Failed to set autostart:', error);
            this.showNotification('Failed to set autostart', 'error');
        }
    }

    async disableAutostart() {
        try {
            const response = await fetch(`${this.apiUrl}/autostart`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                await this.loadAutostartConfig();
                this.showNotification('Autostart disabled', 'success');
            } else {
                throw new Error('Failed to disable autostart');
            }
        } catch (error) {
            console.error('Failed to disable autostart:', error);
            this.showNotification('Failed to disable autostart', 'error');
        }
    }

    updateAutostartUI() {
        // Update scene cards
        this.scenes.forEach(scene => {
            const card = document.querySelector(`[data-scene-id="${scene.id}"]`);
            if (card) {
                const autostartBtn = card.querySelector('.btn-autostart');
                if (autostartBtn) {
                    const isAutostart = this.autostartConfig?.config?.type === 'scene' && 
                                       this.autostartConfig?.config?.id === scene.id;
                    autostartBtn.className = `btn ${isAutostart ? 'btn-success' : 'btn-secondary'} btn-autostart`;
                    autostartBtn.innerHTML = `<i class="fas fa-${isAutostart ? 'stop' : 'play'}"></i> ${isAutostart ? 'Autostart ON' : 'Autostart'}`;
                }
            }
        });

        // Update sequence cards
        this.sequences.forEach(sequence => {
            const card = document.querySelector(`[data-sequence-id="${sequence.id}"]`);
            if (card) {
                const autostartBtn = card.querySelector('.btn-autostart');
                if (autostartBtn) {
                    const isAutostart = this.autostartConfig?.config?.type === 'sequence' && 
                                       this.autostartConfig?.config?.id === sequence.id;
                    autostartBtn.className = `btn ${isAutostart ? 'btn-success' : 'btn-secondary'} btn-autostart`;
                    autostartBtn.innerHTML = `<i class="fas fa-${isAutostart ? 'stop' : 'play'}"></i> ${isAutostart ? 'Autostart ON' : 'Autostart'}`;
                }
            }
        });
    }

    async toggleSceneAutostart(sceneId) {
        const isCurrentlyAutostart = this.autostartConfig?.config?.type === 'scene' && 
                                    this.autostartConfig?.config?.id === sceneId;
        
        if (isCurrentlyAutostart) {
            await this.disableAutostart();
        } else {
            await this.setAutostart('scene', sceneId, true);
        }
        
        // Refresh scenes to update autostart indicators
        this.renderScenes();
    }

    async toggleSequenceAutostart(sequenceId) {
        const isCurrentlyAutostart = this.autostartConfig?.config?.type === 'sequence' && 
                                    this.autostartConfig?.config?.id === sequenceId;
        
        if (isCurrentlyAutostart) {
            await this.disableAutostart();
        } else {
            await this.setAutostart('sequence', sequenceId, true);
        }
        
        // Refresh sequences to update autostart indicators
        this.renderSequences();
    }

    updateSceneAutostartButton(sceneId) {
        const autostartBtn = document.getElementById('scene-autostart-btn');
        const isAutostart = this.autostartConfig?.config?.type === 'scene' && 
                           this.autostartConfig?.config?.id === sceneId;
        
        autostartBtn.className = `btn ${isAutostart ? 'btn-success' : 'btn-secondary'} btn-autostart`;
        autostartBtn.innerHTML = `<i class="fas fa-${isAutostart ? 'stop' : 'play'}"></i> ${isAutostart ? 'Autostart ON' : 'Set Autostart'}`;
    }

    updateSequenceAutostartButton(sequenceId) {
        const autostartBtn = document.getElementById('sequence-autostart-btn');
        const isAutostart = this.autostartConfig?.config?.type === 'sequence' && 
                           this.autostartConfig?.config?.id === sequenceId;
        
        autostartBtn.className = `btn ${isAutostart ? 'btn-success' : 'btn-secondary'} btn-autostart`;
        autostartBtn.innerHTML = `<i class="fas fa-${isAutostart ? 'stop' : 'play'}"></i> ${isAutostart ? 'Autostart ON' : 'Set Autostart'}`;
    }

    async toggleSceneAutostartFromEditor() {
        const modal = document.getElementById('scene-editor');
        const sceneId = modal.dataset.sceneId;
        
        if (sceneId) {
            await this.toggleSceneAutostart(sceneId);
            this.updateSceneAutostartButton(sceneId);
        }
    }

    async toggleSequenceAutostartFromEditor() {
        const modal = document.getElementById('sequence-editor');
        const sequenceId = modal.dataset.sequenceId;
        
        if (sequenceId) {
            await this.toggleSequenceAutostart(sequenceId);
            this.updateSequenceAutostartButton(sequenceId);
        }
    }

    async deleteSceneFromEditor() {
        const modal = document.getElementById('scene-editor');
        const sceneId = modal.dataset.sceneId;
        
        if (sceneId) {
            await this.deleteScene(sceneId);
            this.closeSceneEditor();
        }
    }

    async deleteSequenceFromEditor() {
        const modal = document.getElementById('sequence-editor');
        const sequenceId = modal.dataset.sequenceId;
        
        if (sequenceId) {
            await this.deleteSequence(sequenceId);
            this.closeSequenceEditor();
        }
    }

    setActiveScene(sceneId) {
        // Remove active class from all scene cards
        document.querySelectorAll('.scene-card').forEach(card => {
            card.classList.remove('active');
        });
        
        // Add active class to the current scene card
        if (sceneId) {
            const activeCard = document.querySelector(`.scene-card[data-scene-id="${sceneId}"]`);
            if (activeCard) {
                activeCard.classList.add('active');
            }
        }
    }

    // Scene Management
    openSceneEditor(sceneId = null) {
        const modal = document.getElementById('scene-editor');
        const title = document.getElementById('scene-editor-title');
        const nameInput = document.getElementById('scene-name');
        const descInput = document.getElementById('scene-description');
        const fadeInput = document.getElementById('scene-fade');
        const deleteBtn = document.getElementById('scene-delete-btn');
        const autostartBtn = document.getElementById('scene-autostart-btn');
        const fallbackBtn = document.getElementById('scene-fallback-btn');

        if (sceneId) {
            const scene = this.scenes.find(s => s.id === sceneId);
            if (scene) {
                title.textContent = 'Edit Scene';
                nameInput.value = scene.name;
                descInput.value = scene.description || '';
                fadeInput.value = scene.fade_time || 1000;
                this.generateChannelEditor(scene.channels || []);
                
                // Show delete button for existing scenes
                deleteBtn.style.display = 'block';
                
                // Update autostart button state
                this.updateSceneAutostartButton(sceneId);
                
                // Update fallback button state
                this.updateSceneFallbackButton(sceneId);
                
                // Update fallback button state
                this.updateSceneFallbackButton(sceneId);
            }
        } else {
            title.textContent = 'New Scene';
            nameInput.value = '';
            descInput.value = '';
            fadeInput.value = 1000;
            this.generateChannelEditor([]);
            
            // Hide delete button for new scenes
            deleteBtn.style.display = 'none';
            
            // Reset autostart button
            autostartBtn.className = 'btn btn-secondary btn-autostart';
            autostartBtn.innerHTML = '<i class="fas fa-play"></i> Set Autostart';
            
            // Reset fallback button
            fallbackBtn.className = 'btn btn-secondary btn-fallback';
            fallbackBtn.innerHTML = '<i class="fas fa-play"></i> Set Fallback';
        }

        modal.dataset.sceneId = sceneId;
        modal.style.display = 'block';
    }

    closeSceneEditor() {
        document.getElementById('scene-editor').style.display = 'none';
    }

    generateChannelEditor(channels) {
        const container = document.getElementById('channel-editor');
        container.innerHTML = '';

        for (let i = 1; i <= this.channelCount; i++) {
            const channelValue = channels[i-1] || 0;
            const channelDiv = document.createElement('div');
            channelDiv.className = 'channel-slider';
            channelDiv.innerHTML = `
                <input type="range" min="0" max="255" value="${channelValue}" 
                       data-channel="${i}">
                <label>CH${i}</label>
                <div class="value">${channelValue}</div>
            `;

            const slider = channelDiv.querySelector('input[type="range"]');
            const value = channelDiv.querySelector('.value');

            slider.addEventListener('input', (e) => {
                value.textContent = e.target.value;
            });

            container.appendChild(channelDiv);
        }
    }

    async saveScene() {
        const modal = document.getElementById('scene-editor');
        const sceneId = modal.dataset.sceneId;
        const name = document.getElementById('scene-name').value;
        const description = document.getElementById('scene-description').value;
        const fadeTime = parseInt(document.getElementById('scene-fade').value);

        if (!name.trim()) {
            this.showNotification('Scene name is required', 'error');
            return;
        }

        const channels = [];
        document.querySelectorAll('#channel-editor input[type="range"]').forEach(slider => {
            channels.push(parseInt(slider.value));
        });

        const sceneData = {
            name: name,
            description: description,
            fade_time: fadeTime,
            channels: channels
        };

        try {
            let response;
            if (sceneId) {
                response = await fetch(`${this.apiUrl}/scenes/${sceneId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(sceneData)
                });
            } else {
                response = await fetch(`${this.apiUrl}/scenes`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(sceneData)
                });
            }

            if (response.ok) {
                this.closeSceneEditor();
                this.loadScenes();
                this.showNotification(`Scene ${sceneId ? 'updated' : 'created'} successfully`, 'success');
            } else {
                throw new Error('Failed to save scene');
            }
        } catch (error) {
            this.showNotification('Failed to save scene', 'error');
        }
    }

    async loadScenes() {
        try {
            const response = await fetch(`${this.apiUrl}/scenes`);
            if (response.ok) {
                this.scenes = await response.json();
                this.renderScenes();
            }
        } catch (error) {
            console.error('Failed to load scenes:', error);
        }
    }

    renderScenes() {
        const container = document.getElementById('scenes-grid');
        container.innerHTML = '';

        this.scenes.forEach(scene => {
            const isAutostart = this.autostartConfig?.config?.type === 'scene' && 
                               this.autostartConfig?.config?.id === scene.id;
            
            // Check for scene fallback (new feature)
            const sceneFallbackConfig = this.fallbackConfig?.config?.scene_fallback;
            const isSceneFallback = sceneFallbackConfig?.enabled && sceneFallbackConfig?.scene_id === scene.id;
            
            // Check for sequence fallback (existing feature)
            const isSequenceFallback = this.fallbackConfig?.config?.type === 'scene' && 
                                      this.fallbackConfig?.config?.id === scene.id;
            
            const isFallback = isSceneFallback || isSequenceFallback;
            
            const card = document.createElement('div');
            card.className = 'scene-card';
            if (isAutostart) {
                card.classList.add('autostart-active');
            }
            if (isFallback) {
                card.classList.add('fallback-active');
            }
            card.dataset.sceneId = scene.id;
            card.innerHTML = `
                <div class="card-header">
                    <h4>${scene.name}</h4>
                    ${isAutostart ? '<div class="autostart-indicator" title="Autostart Enabled"><i class="fas fa-circle"></i></div>' : ''}
                    ${isFallback ? '<div class="fallback-indicator" title="Fallback Enabled"><i class="fas fa-circle"></i></div>' : ''}
                </div>
                <p>${scene.description || 'No description'}</p>
                <div class="card-actions">
                    <button class="btn btn-primary" onclick="dmxConsole.playScene('${scene.id}')">
                        <i class="fas fa-play"></i> Play
                    </button>
                    <button class="btn btn-secondary" onclick="dmxConsole.openSceneEditor('${scene.id}')">
                        <i class="fas fa-edit"></i> Edit
                    </button>

                </div>
            `;
            container.appendChild(card);
        });
        
        // Update fallback UI after rendering
        this.updateFallbackUI();
    }

    async playScene(sceneId) {
        try {
            // Always stop any current playback first
            await fetch(`${this.apiUrl}/playback/stop`, { method: 'POST' });

            // Find the scene data to get channel values
            const scene = this.scenes.find(s => s.id === sceneId);
            if (!scene) {
                this.showNotification('Scene not found', 'error');
                return;
            }

            // Play the scene via API
            const response = await fetch(`${this.apiUrl}/scenes/${sceneId}/play`, {
                method: 'POST'
            });
            
            if (response.ok) {
                // Set current scene and update playback state
                this.currentScene = sceneId;
                this.currentSequence = null;
                this.currentProgrammableScene = null;
                this.isPlaying = true;
                
                // Update current channels with scene values
                if (scene.channels && Array.isArray(scene.channels)) {
                    // Update the currentChannels array with scene values
                    for (let i = 0; i < Math.min(scene.channels.length, this.currentChannels.length); i++) {
                        this.currentChannels[i] = scene.channels[i] || 0;
                    }
                    
                    // Update the sidebar sliders to reflect the scene values
                    this.updateAllFaders();
                }
                
                this.updatePlaybackInfo();
                this.showNotification(`Scene "${scene.name}" played successfully`, 'success');
            } else {
                throw new Error('Failed to play scene');
            }
        } catch (error) {
            console.error('Failed to play scene:', error);
            this.showNotification('Failed to play scene', 'error');
        }
    }

    async deleteScene(sceneId) {
        if (!confirm('Are you sure you want to delete this scene?')) return;

        try {
            const response = await fetch(`${this.apiUrl}/scenes/${sceneId}`, {
                method: 'DELETE'
            });
            if (response.ok) {
                this.loadScenes();
                this.showNotification('Scene deleted successfully', 'success');
            }
        } catch (error) {
            this.showNotification('Failed to delete scene', 'error');
        }
    }

    // Sequence Management
    openSequenceEditor(sequenceId = null) {
        const modal = document.getElementById('sequence-editor');
        const title = document.getElementById('sequence-editor-title');
        const nameInput = document.getElementById('sequence-name');
        const descInput = document.getElementById('sequence-description');
        const loopInput = document.getElementById('sequence-loop');
        const deleteBtn = document.getElementById('sequence-delete-btn');
        const autostartBtn = document.getElementById('sequence-autostart-btn');
        const fallbackBtn = document.getElementById('sequence-fallback-btn');

        if (sequenceId) {
            const sequence = this.sequences.find(s => s.id === sequenceId);
            if (sequence) {
                title.textContent = 'Edit Sequence';
                nameInput.value = sequence.name;
                descInput.value = sequence.description || '';
                loopInput.checked = sequence.loop || false;
                this.renderSequenceSteps(sequence.steps || []);
                
                // Show delete button for existing sequences
                deleteBtn.style.display = 'block';
                
                // Update autostart button state
                this.updateSequenceAutostartButton(sequenceId);
                
                // Update fallback button state
                this.updateSequenceFallbackButton(sequenceId);
                
                // Update fallback button state
                this.updateSequenceFallbackButton(sequenceId);
            }
        } else {
            title.textContent = 'New Sequence';
            nameInput.value = '';
            descInput.value = '';
            loopInput.checked = false;
            this.renderSequenceSteps([]);
            
            // Hide delete button for new sequences
            deleteBtn.style.display = 'none';
            
            // Reset autostart button
            autostartBtn.className = 'btn btn-secondary btn-autostart';
            autostartBtn.innerHTML = '<i class="fas fa-play"></i> Set Autostart';
            
            // Reset fallback button
            fallbackBtn.className = 'btn btn-secondary btn-fallback';
            fallbackBtn.innerHTML = '<i class="fas fa-play"></i> Set Fallback';
        }

        modal.dataset.sequenceId = sequenceId;
        modal.style.display = 'block';
    }

    closeSequenceEditor() {
        document.getElementById('sequence-editor').style.display = 'none';
    }

    addSequenceStep() {
        const stepsContainer = document.getElementById('sequence-steps');
        const stepIndex = stepsContainer.children.length;
        
        const stepDiv = document.createElement('div');
        stepDiv.className = 'step-item';
        stepDiv.innerHTML = `
                <div class="step-header">
                    <h5>Step ${stepIndex + 1}</h5>
                    <button class="btn btn-sm btn-danger" onclick="dmxConsole.removeStep(${stepIndex})">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
                <div class="step-content">
                    <div class="form-group">
                        <label>Duration (ms):</label>
                        <input type="number" class="form-control" value="1000" min="100" max="30000" 
                               data-step-index="${stepIndex}">
                    </div>
                    <div class="form-group">
                        <label>Scene:</label>
                        <select class="form-control" data-step-index="${stepIndex}">
                            <option value="">Select a scene</option>
                            ${this.scenes.map(scene => `<option value="${scene.id}">${scene.name}</option>`).join('')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Sequence:</label>
                        <select class="form-control" data-step-index="${stepIndex}">
                            <option value="">Select a sequence</option>
                            ${this.sequences.map(sequence => `<option value="${sequence.id}">${sequence.name}</option>`).join('')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Blackout:</label>
                        <select class="form-control" data-step-index="${stepIndex}">
                            <option value="false">No</option>
                            <option value="true">Yes</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Fade Time (ms):</label>
                        <input type="number" class="form-control" value="1000" min="0" max="10000" 
                               data-step-index="${stepIndex}">
                    </div>
                </div>
            `;

        stepsContainer.appendChild(stepDiv);
    }

    editStep(index) {
        const step = document.getElementById(`step-${index}`);
        if (step) {
            const durationInput = step.querySelector('input[type="number"][data-step-index]');
            const sceneSelect = step.querySelector('select[data-step-index]');
            const sequenceSelect = step.querySelector('select[data-step-index]'); // This is a duplicate, should be sequenceSelect
            const blackoutSelect = step.querySelector('select[data-step-index]'); // This is a duplicate, should be blackoutSelect
            const fadeInput = step.querySelector('input[type="number"][data-step-index]');

            if (durationInput) durationInput.value = this.sequences[index].duration || 1000;
            if (sceneSelect) sceneSelect.value = this.sequences[index].scene_id || '';
            if (sequenceSelect) sequenceSelect.value = this.sequences[index].sequence_id || '';
            if (blackoutSelect) blackoutSelect.value = this.sequences[index].blackout || 'false';
            if (fadeInput) fadeInput.value = this.sequences[index].fade_time || 1000;
        }
    }

    closeStepEditor() {
        document.getElementById('sequence-step-editor').style.display = 'none';
    }

    async saveStep() {
        const stepIndex = document.getElementById('sequence-step-editor').dataset.stepIndex;
        const step = document.getElementById(`step-${stepIndex}`);
        if (!step) return;

        const duration = parseInt(step.querySelector('input[type="number"][data-step-index]').value);
        const sceneId = step.querySelector('select[data-step-index]').value;
        const sequenceId = step.querySelector('select[data-step-index]').value; // This is a duplicate, should be sequenceId
        const blackout = step.querySelector('select[data-step-index]').value; // This is a duplicate, should be blackout
        const fadeTime = parseInt(step.querySelector('input[type="number"][data-step-index]').value);

        if (!sceneId && !sequenceId) {
            this.showNotification('Please select a scene or sequence for the step', 'error');
            return;
        }

        const stepData = {
            duration: duration,
            scene_id: sceneId,
            sequence_id: sequenceId,
            blackout: blackout,
            fade_time: fadeTime
        };

        try {
            const response = await fetch(`${this.apiUrl}/sequences/${this.currentSequence}/steps/${stepIndex}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(stepData)
            });

            if (response.ok) {
                this.closeStepEditor();
                this.renderSequenceSteps(this.sequences[this.currentSequence].steps);
                this.showNotification('Step updated successfully', 'success');
            } else {
                throw new Error('Failed to save step');
            }
        } catch (error) {
            this.showNotification('Failed to save step', 'error');
        }
    }

    async removeStep(index) {
        if (!confirm('Are you sure you want to delete this step?')) return;

        try {
            const response = await fetch(`${this.apiUrl}/sequences/${this.currentSequence}/steps/${index}`, {
                method: 'DELETE'
            });
            if (response.ok) {
                this.renderSequenceSteps(this.sequences[this.currentSequence].steps);
                this.showNotification('Step deleted successfully', 'success');
            }
        } catch (error) {
            this.showNotification('Failed to delete step', 'error');
        }
    }

    async playSequence(sequenceId) {
        try {
            // Always stop any current playback first
            await fetch(`${this.apiUrl}/playback/stop`, { method: 'POST' });

            const sequence = this.sequences.find(s => s.id === sequenceId);
            if (!sequence) {
                this.showNotification('Sequence not found', 'error');
                return;
            }

            // Play the sequence via API
            const response = await fetch(`${this.apiUrl}/sequences/${sequenceId}/play`, {
                method: 'POST'
            });
            
            if (response.ok) {
                // Set current sequence and update playback state
                this.currentSequence = sequenceId;
                this.currentScene = null;
                this.isPlaying = true;
                
                // Update current channels with sequence values
                if (sequence.steps && Array.isArray(sequence.steps)) {
                    // Calculate total duration and update sequence timer
                    let totalDuration = 0;
                    for (const step of sequence.steps) {
                        totalDuration += step.duration;
                    }
                    this.sequenceTimer = setInterval(() => this.pollPlaybackStatus(), 500);
                    this.sequenceTimer = setInterval(() => this.pollPlaybackStatus(), 500);
                    
                    // Update the currentChannels array with sequence values
                    for (let i = 0; i < Math.min(totalDuration, this.currentChannels.length); i++) {
                        this.currentChannels[i] = 0; // Initialize with 0
                    }
                    
                    // Update the sidebar sliders to reflect the sequence values
                    this.updateAllFaders();
                }
                
                this.updatePlaybackInfo();
                this.showNotification(`Sequence "${sequence.name}" played successfully`, 'success');
            } else {
                throw new Error('Failed to play sequence');
            }
        } catch (error) {
            console.error('Failed to play sequence:', error);
            this.showNotification('Failed to play sequence', 'error');
        }
    }

    async pauseSequence() {
        try {
            const response = await fetch(`${this.apiUrl}/sequences/${this.currentSequence}/pause`, {
                method: 'POST'
            });
            
            if (response.ok) {
                this.isPlaying = false;
                this.updatePlaybackInfo();
                this.showNotification('Sequence paused', 'info');
            } else {
                throw new Error('Failed to pause sequence');
            }
        } catch (error) {
            console.error('Failed to pause sequence:', error);
            this.showNotification('Failed to pause sequence', 'error');
        }
    }

    async stopSequence() {
        try {
            const response = await fetch(`${this.apiUrl}/sequences/${this.currentSequence}/stop`, {
                method: 'POST'
            });
            
            if (response.ok) {
                this.isPlaying = false;
                this.currentStep = 0;
                this.currentStepData = null;
                this.stepStartTime = null;
                this.stepTimer = null;
                this.sequenceTimer = null;
                this.stepProgressTimer = null;
                this.updatePlaybackInfo();
                this.showNotification('Sequence stopped', 'info');
            } else {
                throw new Error('Failed to stop sequence');
            }
        } catch (error) {
            console.error('Failed to stop sequence:', error);
            this.showNotification('Failed to stop sequence', 'error');
        }
    }

    togglePlayback() {
        if (this.isPlaying) {
            this.pauseSequence();
        } else {
            this.playSequence(this.currentSequence);
        }
    }

    updatePlaybackInfo() {
        const currentPlayback = document.getElementById('current-playback');
        const playbackType = document.getElementById('playback-type');
        const playbackStatus = document.getElementById('playback-status');
        console.log('[updatePlaybackInfo] isPlaying:', this.isPlaying, 'currentScene:', this.currentScene, 'currentSequence:', this.currentSequence, 'currentProgrammableScene:', this.currentProgrammableScene); // DEBUG
        if (this.isPlaying) {
            let playingName = 'Unknown';
            let typeName = 'Unknown';
            
            if (this.currentProgrammableScene) {
                const programmableScene = this.programmableScenes.find(s => s.id === this.currentProgrammableScene);
                playingName = programmableScene ? programmableScene.name : this.currentProgrammableScene;
                typeName = 'Programmable Scene';
            } else if (this.currentSequence) {
                const sequence = this.sequences.find(s => s.id === this.currentSequence);
                playingName = sequence ? sequence.name : this.currentSequence;
                typeName = 'Sequence';
            } else if (this.currentScene) {
                const scene = this.scenes.find(s => s.id === this.currentScene);
                playingName = scene ? scene.name : this.currentScene;
                typeName = 'Scene';
            }
            
            if (currentPlayback) currentPlayback.textContent = playingName;
            if (playbackType) playbackType.textContent = typeName;
            if (playbackStatus) playbackStatus.textContent = 'Playing';
        } else {
            if (currentPlayback) currentPlayback.textContent = 'None';
            if (playbackType) playbackType.textContent = 'None';
            if (playbackStatus) playbackStatus.textContent = 'Stopped';
        }
    }

    updateSequenceStepInfo(stepNumber, stepData) {
        // This method will be called to update the sequence step info display
        this.currentStep = stepNumber;
        this.currentStepData = stepData;
        if (this.currentStepData) {
            this.showSequenceStepInfo();
        }
    }

    showSequenceStepInfo() {
        const stepInfo = document.getElementById('sequence-step-info');
        const currentStepNumber = document.getElementById('current-step-number');
        const currentStepScene = document.getElementById('current-step-scene');
        const currentStepDuration = document.getElementById('current-step-duration');
        const stepProgressFill = document.getElementById('step-progress-fill');
        
        if (stepInfo) {
            stepInfo.style.display = 'block';
        }
        
        if (this.currentStepData) {
            if (currentStepNumber) {
                currentStepNumber.textContent = `${this.currentStep + 1}`;
            }
            if (currentStepScene) {
                currentStepScene.textContent = this.currentStepData.scene_name || 'Unknown';
            }
            if (currentStepDuration) {
                const duration = this.currentStepData.duration || 0;
                currentStepDuration.textContent = `${duration}ms`;
            }
            if (stepProgressFill) {
                const progress = this.currentStepData.progress || 0;
                stepProgressFill.style.width = `${progress}%`;
            }
        } else {
            if (currentStepNumber) currentStepNumber.textContent = '-';
            if (currentStepScene) currentStepScene.textContent = '-';
            if (currentStepDuration) currentStepDuration.textContent = '-';
            if (stepProgressFill) stepProgressFill.style.width = '0%';
        }
    }

    hideSequenceStepInfo() {
        const stepInfo = document.getElementById('sequence-step-info');
        if (stepInfo) {
            stepInfo.style.display = 'none';
        }
    }

    showProgrammableSceneInfo() {
        const stepInfo = document.getElementById('sequence-step-info');
        const currentStepNumber = document.getElementById('current-step-number');
        const currentStepScene = document.getElementById('current-step-scene');
        const currentStepDuration = document.getElementById('current-step-duration');
        const stepProgressFill = document.getElementById('step-progress-fill');
        
        if (stepInfo) {
            stepInfo.style.display = 'block';
        }
        
        if (this.currentStepData) {
            if (currentStepNumber) {
                currentStepNumber.textContent = '1';
            }
            if (currentStepScene) {
                currentStepScene.textContent = this.currentStepData.scene_name || 'Unknown';
            }
            if (currentStepDuration) {
                const duration = this.currentStepData.duration || 0;
                currentStepDuration.textContent = `${duration}s`;
            }
            if (stepProgressFill) {
                const progress = this.currentStepData.progress || 0;
                stepProgressFill.style.width = `${progress}%`;
            }
        } else {
            if (currentStepNumber) currentStepNumber.textContent = '-';
            if (currentStepScene) currentStepScene.textContent = '-';
            if (currentStepDuration) currentStepDuration.textContent = '-';
            if (stepProgressFill) stepProgressFill.style.width = '0%';
        }
    }

    hideProgrammableSceneInfo() {
        const stepInfo = document.getElementById('sequence-step-info');
        if (stepInfo) {
            stepInfo.style.display = 'none';
        }
    }

    updateProgrammableSceneProgress(progress) {
        const stepProgressFill = document.getElementById('step-progress-fill');
        
        if (stepProgressFill) {
            stepProgressFill.style.width = `${progress}%`;
        }
    }

    startStepProgress(stepData) {
        this.stepStartTime = Date.now();
        this.stepTimer = setInterval(() => {
            const elapsedTime = Date.now() - this.stepStartTime;
            const progress = Math.min(elapsedTime / stepData.duration, 1);
            const currentValue = Math.round(progress * 255);

            this.updateFaderFromChannel(stepData.channel, currentValue);
            this.currentChannels[stepData.channel - 1] = currentValue;

            if (progress >= 1) {
                clearInterval(this.stepTimer);
                this.stepTimer = null;
                this.stepProgressTimer = null;
                this.currentStep++;
                this.updatePlaybackInfo();
                this.showSequenceStepInfo();
                if (this.currentStep < this.sequences.find(s => s.id === this.currentSequence)?.steps?.length) {
                    this.startStepProgress(this.sequences.find(s => s.id === this.currentSequence)?.steps[this.currentStep]);
                } else {
                    this.isPlaying = false;
                    this.updatePlaybackInfo();
                    this.showNotification('Sequence finished', 'info');
                    clearInterval(this.sequenceTimer);
                    this.sequenceTimer = null;
                }
            }
        }, 10); // Update every 10ms for smooth progress
    }

    async loadSequences() {
        try {
            const response = await fetch(`${this.apiUrl}/sequences`);
            if (response.ok) {
                this.sequences = await response.json();
                this.renderSequences();
            }
        } catch (error) {
            console.error('Failed to load sequences:', error);
        }
    }

    renderSequences() {
        const container = document.getElementById('sequences-grid');
        container.innerHTML = '';

        this.sequences.forEach(sequence => {
            const isAutostart = this.autostartConfig?.config?.type === 'sequence' && 
                               this.autostartConfig?.config?.id === sequence.id;
            const isFallback = this.fallbackConfig?.config?.type === 'sequence' && 
                               this.fallbackConfig?.config?.id === sequence.id;
            
            const card = document.createElement('div');
            card.className = 'sequence-card';
            if (isAutostart) {
                card.classList.add('autostart-active');
            }
            if (isFallback) {
                card.classList.add('fallback-active');
            }
            card.dataset.sequenceId = sequence.id;
            card.innerHTML = `
                <div class="card-header">
                    <h4>${sequence.name}</h4>
                    ${isAutostart ? '<div class="autostart-indicator" title="Autostart Enabled"><i class="fas fa-circle"></i></div>' : ''}
                    ${isFallback ? '<div class="fallback-indicator" title="Fallback Enabled"><i class="fas fa-circle"></i></div>' : ''}
                </div>
                <p>${sequence.description || 'No description'}</p>
                <div class="card-actions">
                    <button class="btn btn-primary" onclick="dmxConsole.playSequence('${sequence.id}')">
                        <i class="fas fa-play"></i> Play
                    </button>
                    <button class="btn btn-secondary" onclick="dmxConsole.openSequenceEditor('${sequence.id}')">
                        <i class="fas fa-edit"></i> Edit
                    </button>
                </div>
            `;
            container.appendChild(card);
        });
    }

    async deleteSequence(sequenceId) {
        if (!confirm('Are you sure you want to delete this sequence?')) return;

        try {
            const response = await fetch(`${this.apiUrl}/sequences/${sequenceId}`, {
                method: 'DELETE'
            });
            if (response.ok) {
                this.loadSequences();
                this.showNotification('Sequence deleted successfully', 'success');
            }
        } catch (error) {
            this.showNotification('Failed to delete sequence', 'error');
        }
    }

    async saveSequence() {
        const modal = document.getElementById('sequence-editor');
        const sequenceId = modal.dataset.sequenceId;
        const name = document.getElementById('sequence-name').value;
        const description = document.getElementById('sequence-description').value;
        const loop = document.getElementById('sequence-loop').checked;

        if (!name.trim()) {
            this.showNotification('Sequence name is required', 'error');
            return;
        }

        const steps = [];
        document.querySelectorAll('#sequence-steps .step-item').forEach(stepDiv => {
            const duration = parseInt(stepDiv.querySelector('input[type="number"][data-step-index]').value);
            const sceneId = stepDiv.querySelector('select[data-step-index]').value;
            const sequenceId = stepDiv.querySelector('select[data-step-index]').value; // This is a duplicate, should be sequenceId
            const blackout = stepDiv.querySelector('select[data-step-index]').value; // This is a duplicate, should be blackout
            const fadeTime = parseInt(stepDiv.querySelector('input[type="number"][data-step-index]').value);

            steps.push({
                duration: duration,
                scene_id: sceneId,
                sequence_id: sequenceId,
                blackout: blackout,
                fade_time: fadeTime
            });
        });

        const sequenceData = {
            name: name,
            description: description,
            loop: loop,
            steps: steps
        };

        try {
            let response;
            if (sequenceId) {
                response = await fetch(`${this.apiUrl}/sequences/${sequenceId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(sequenceData)
                });
            } else {
                response = await fetch(`${this.apiUrl}/sequences`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(sequenceData)
                });
            }

            if (response.ok) {
                this.closeSequenceEditor();
                this.loadSequences();
                this.showNotification(`Sequence ${sequenceId ? 'updated' : 'created'} successfully`, 'success');
            } else {
                throw new Error('Failed to save sequence');
            }
        } catch (error) {
            this.showNotification('Failed to save sequence', 'error');
        }
    }

    renderSequenceSteps(steps) {
        const stepsContainer = document.getElementById('sequence-steps');
        stepsContainer.innerHTML = '';

        steps.forEach((step, index) => {
            const stepDiv = document.createElement('div');
            stepDiv.id = `step-${index}`;
            stepDiv.className = 'step-item';
            stepDiv.innerHTML = `
                <div class="step-header">
                    <h5>Step ${index + 1}</h5>
                    <button class="btn btn-sm btn-danger" onclick="dmxConsole.removeStep(${index})">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
                <div class="step-content">
                    <div class="form-group">
                        <label>Duration (ms):</label>
                        <input type="number" class="form-control" value="${step.duration || 1000}" min="100" max="30000" 
                               data-step-index="${index}">
                    </div>
                    <div class="form-group">
                        <label>Scene:</label>
                        <select class="form-control" data-step-index="${index}">
                            <option value="">Select a scene</option>
                            ${this.scenes.map(scene => `<option value="${scene.id}" ${scene.id === step.scene_id ? 'selected' : ''}>${scene.name}</option>`).join('')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Sequence:</label>
                        <select class="form-control" data-step-index="${index}">
                            <option value="">Select a sequence</option>
                            ${this.sequences.map(sequence => `<option value="${sequence.id}" ${sequence.id === step.sequence_id ? 'selected' : ''}>${sequence.name}</option>`).join('')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Blackout:</label>
                        <select class="form-control" data-step-index="${index}">
                            <option value="false" ${step.blackout === 'false' ? 'selected' : ''}>No</option>
                            <option value="true" ${step.blackout === 'true' ? 'selected' : ''}>Yes</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Fade Time (ms):</label>
                        <input type="number" class="form-control" value="${step.fade_time || 1000}" min="0" max="10000" 
                               data-step-index="${index}">
                    </div>
                </div>
            `;
            stepsContainer.appendChild(stepDiv);
        });
    }

    // Programmable Scene Methods
    async loadProgrammableScenes() {
        try {
            const response = await fetch(`${this.apiUrl}/programmable`);
            if (response.ok) {
                const data = await response.json();
                this.programmableScenes = data.data || [];
                this.renderProgrammableScenes();
            }
        } catch (error) {
            console.error('Failed to load programmable scenes:', error);
        }
    }

    renderProgrammableScenes() {
        const container = document.getElementById('programmable-grid');
        container.innerHTML = '';

        this.programmableScenes.forEach(scene => {
            const isAutostart = this.autostartConfig && this.autostartConfig.type === 'programmable' && this.autostartConfig.id === scene.id;
            const isFallback = this.fallbackConfig && this.fallbackConfig.type === 'programmable' && this.fallbackConfig.id === scene.id;
            
            const card = document.createElement('div');
            card.className = 'scene-card';
            card.innerHTML = `
                <div class="card-header">
                    <h4>${scene.name}</h4>
                    ${isAutostart ? '<div class="autostart-indicator" title="Autostart Enabled"><i class="fas fa-circle"></i></div>' : ''}
                    ${isFallback ? '<div class="fallback-indicator" title="Fallback Enabled"><i class="fas fa-circle"></i></div>' : ''}
                </div>
                <p>${scene.description || 'No description'}</p>
                <div class="card-actions">
                    <button class="btn btn-primary" onclick="dmxConsole.playProgrammable('${scene.id}')">
                        <i class="fas fa-play"></i> Play
                    </button>
                    <button class="btn btn-secondary" onclick="dmxConsole.openProgrammableEditor('${scene.id}')">
                        <i class="fas fa-edit"></i> Edit
                    </button>
                    <button class="btn btn-danger" onclick="dmxConsole.deleteProgrammable('${scene.id}')">
                        <i class="fas fa-trash"></i> Delete
                    </button>
                </div>
            `;
            container.appendChild(card);
        });
    }

    async playProgrammable(sceneId) {
        try {
            // Always stop any current playback first
            await fetch(`${this.apiUrl}/playback/stop`, { method: 'POST' });

            const scene = this.programmableScenes.find(s => s.id === sceneId);
            if (!scene) {
                this.showNotification('Programmable scene not found', 'error');
                return;
            }

            const response = await fetch(`${this.apiUrl}/programmable/${sceneId}/play`, {
                method: 'POST'
            });
            if (response.ok) {
                this.isPlaying = true;
                this.currentScene = sceneId;
                this.currentSequence = null;
                this.updatePlaybackInfo();
                this.showNotification('Programmable scene started', 'success');
            }
        } catch (error) {
            this.showNotification('Failed to play programmable scene', 'error');
        }
    }

    async deleteProgrammable(sceneId) {
        if (!confirm('Are you sure you want to delete this programmable scene?')) return;

        try {
            const response = await fetch(`${this.apiUrl}/programmable/${sceneId}`, {
                method: 'DELETE'
            });
            if (response.ok) {
                this.loadProgrammableScenes();
                this.showNotification('Programmable scene deleted successfully', 'success');
            }
        } catch (error) {
            this.showNotification('Failed to delete programmable scene', 'error');
        }
    }

    openProgrammableEditor(sceneId = null) {
        const modal = document.getElementById('programmable-editor');
        const title = document.getElementById('programmable-editor-title');
        
        if (sceneId) {
            title.textContent = 'Edit Programmable Scene';
            modal.dataset.programmableId = sceneId;
            
            const scene = this.programmableScenes.find(s => s.id === sceneId);
            if (scene) {
                document.getElementById('programmable-name').value = scene.name;
                document.getElementById('programmable-description').value = scene.description || '';
                document.getElementById('programmable-duration').value = scene.duration || 5000;
                document.getElementById('programmable-loop').checked = scene.loop || false;
                
                this.generateExpressionEditor(scene.expressions || {});
            }
            
            document.getElementById('programmable-delete-btn').style.display = 'block';
            this.updateProgrammableAutostartButton(sceneId);
            this.updateProgrammableFallbackButton(sceneId);
        } else {
            title.textContent = 'New Programmable Scene';
            delete modal.dataset.programmableId;
            
            document.getElementById('programmable-name').value = '';
            document.getElementById('programmable-description').value = '';
            document.getElementById('programmable-duration').value = 5000;
            document.getElementById('programmable-loop').checked = false;
            
            this.generateExpressionEditor({});
            
            document.getElementById('programmable-delete-btn').style.display = 'none';
            document.getElementById('programmable-autostart-btn').textContent = 'Set Autostart';
            document.getElementById('programmable-fallback-btn').textContent = 'Set Fallback';
        }
        
        modal.style.display = 'block';
    }

    closeProgrammableEditor() {
        document.getElementById('programmable-editor').style.display = 'none';
    }

    generateExpressionEditor(expressions) {
        const container = document.getElementById('expression-editor');
        container.innerHTML = '';

        for (let i = 1; i <= this.channelCount; i++) {
            const expressionDiv = document.createElement('div');
            expressionDiv.className = 'expression-item';
            expressionDiv.innerHTML = `
                <label for="expression-${i}">CH${i}:</label>
                <input type="text" id="expression-${i}" class="expression-input" 
                       placeholder="e.g., 255 * sin(t)" value="${expressions[i] || ''}" />
            `;
            container.appendChild(expressionDiv);
        }
    }

    async saveProgrammable() {
        const modal = document.getElementById('programmable-editor');
        const sceneId = modal.dataset.programmableId;
        const name = document.getElementById('programmable-name').value;
        const description = document.getElementById('programmable-description').value;
        const duration = parseInt(document.getElementById('programmable-duration').value);
        const loop = document.getElementById('programmable-loop').checked;

        if (!name.trim()) {
            this.showNotification('Programmable scene name is required', 'error');
            return;
        }

        const expressions = {};
        for (let i = 1; i <= this.channelCount; i++) {
            const expression = document.getElementById(`expression-${i}`).value.trim();
            if (expression) {
                expressions[i] = expression;
            }
        }

        const sceneData = {
            name: name,
            description: description,
            duration: duration,
            loop: loop,
            expressions: expressions
        };

        try {
            let response;
            if (sceneId) {
                response = await fetch(`${this.apiUrl}/programmable/${sceneId}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(sceneData)
                });
            } else {
                response = await fetch(`${this.apiUrl}/programmable`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(sceneData)
                });
            }

            if (response.ok) {
                this.closeProgrammableEditor();
                this.loadProgrammableScenes();
                this.showNotification(`Programmable scene ${sceneId ? 'updated' : 'created'} successfully`, 'success');
            } else {
                throw new Error('Failed to save programmable scene');
            }
        } catch (error) {
            this.showNotification('Failed to save programmable scene', 'error');
        }
    }

    updateProgrammableAutostartButton(sceneId) {
        const button = document.getElementById('programmable-autostart-btn');
        const isAutostart = this.autostartConfig && this.autostartConfig.type === 'programmable' && this.autostartConfig.id === sceneId;
        button.textContent = isAutostart ? 'Remove Autostart' : 'Set Autostart';
        button.className = isAutostart ? 'btn btn-secondary btn-autostart active' : 'btn btn-secondary btn-autostart';
    }

    updateProgrammableFallbackButton(sceneId) {
        const button = document.getElementById('programmable-fallback-btn');
        const isFallback = this.fallbackConfig && this.fallbackConfig.type === 'programmable' && this.fallbackConfig.id === sceneId;
        button.textContent = isFallback ? 'Remove Fallback' : 'Set Fallback';
        button.className = isFallback ? 'btn btn-secondary btn-fallback active' : 'btn btn-secondary btn-fallback';
    }

    async toggleProgrammableAutostartFromEditor() {
        const modal = document.getElementById('programmable-editor');
        const sceneId = modal.dataset.programmableId;
        if (!sceneId) return;

        const isAutostart = this.autostartConfig && this.autostartConfig.type === 'programmable' && this.autostartConfig.id === sceneId;
        
        if (isAutostart) {
            await this.disableAutostart();
        } else {
            await this.setAutostart('programmable', sceneId);
        }
        
        this.updateProgrammableAutostartButton(sceneId);
    }

    async toggleProgrammableFallbackFromEditor() {
        const modal = document.getElementById('programmable-editor');
        const sceneId = modal.dataset.programmableId;
        if (!sceneId) return;

        const isFallback = this.fallbackConfig && this.fallbackConfig.type === 'programmable' && this.fallbackConfig.id === sceneId;
        
        if (isFallback) {
            await this.disableFallback();
        } else {
            await this.setFallback('programmable', sceneId);
        }
        
        this.updateProgrammableFallbackButton(sceneId);
    }

    async deleteProgrammableFromEditor() {
        const modal = document.getElementById('programmable-editor');
        const sceneId = modal.dataset.programmableId;
        if (!sceneId) return;

        if (confirm('Are you sure you want to delete this programmable scene?')) {
            await this.deleteProgrammable(sceneId);
            this.closeProgrammableEditor();
        }
    }

    async loadFallbackConfig() {
        try {
            const response = await fetch(`${this.apiUrl}/fallback`);
            if (response.ok) {
                const data = await response.json();
                this.fallbackConfig = data.data;
                this.updateFallbackUI();
            }
        } catch (error) {
            console.error('Failed to load fallback config:', error);
        }
    }

    async setFallback(type, id, enabled = true) {
        try {
            const response = await fetch(`${this.apiUrl}/fallback`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type, id, enabled })
            });
            
            if (response.ok) {
                await this.loadFallbackConfig();
                this.showNotification(`Fallback ${enabled ? 'enabled' : 'disabled'} for ${type}`, 'success');
                
                // Refresh UI to update fallback indicators
                this.renderScenes();
                this.renderSequences();
            } else {
                throw new Error('Failed to set fallback');
            }
        } catch (error) {
            console.error('Failed to set fallback:', error);
            this.showNotification('Failed to set fallback', 'error');
        }
    }

    async disableFallback() {
        try {
            const response = await fetch(`${this.apiUrl}/fallback`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                await this.loadFallbackConfig();
                this.showNotification('Fallback disabled', 'success');
            } else {
                throw new Error('Failed to disable fallback');
            }
        } catch (error) {
            console.error('Failed to disable fallback:', error);
            this.showNotification('Failed to disable fallback', 'error');
        }
    }

    updateFallbackUI() {
        // Update scene cards
        this.scenes.forEach(scene => {
            const card = document.querySelector(`[data-scene-id="${scene.id}"]`);
            if (card) {
                const fallbackBtn = card.querySelector('.btn-fallback');
                if (fallbackBtn) {
                    // Check for scene fallback (new feature)
                    const sceneFallbackConfig = this.fallbackConfig?.config?.scene_fallback;
                    const isSceneFallback = sceneFallbackConfig?.enabled && sceneFallbackConfig?.scene_id === scene.id;
                    
                    // Check for sequence fallback (existing feature)
                    const isSequenceFallback = this.fallbackConfig?.config?.type === 'scene' && 
                                              this.fallbackConfig?.config?.id === scene.id;
                    
                    const isFallback = isSceneFallback || isSequenceFallback;
                    fallbackBtn.className = `btn ${isFallback ? 'btn-success' : 'btn-secondary'} btn-fallback`;
                    
                    if (isSceneFallback) {
                        const delay = sceneFallbackConfig.delay || 1.0;
                        fallbackBtn.innerHTML = `<i class="fas fa-clock"></i> Global Fallback (${delay}s)`;
                    } else if (isSequenceFallback) {
                        fallbackBtn.innerHTML = `<i class="fas fa-stop"></i> Fallback ON`;
                    } else {
                        fallbackBtn.innerHTML = `<i class="fas fa-play"></i> Set Global Fallback`;
                    }
                }
            }
        });

        // Update sequence cards
        this.sequences.forEach(sequence => {
            const card = document.querySelector(`[data-sequence-id="${sequence.id}"]`);
            if (card) {
                const fallbackBtn = card.querySelector('.btn-fallback');
                if (fallbackBtn) {
                    const isFallback = this.fallbackConfig?.config?.type === 'sequence' && 
                                      this.fallbackConfig?.config?.id === sequence.id;
                    fallbackBtn.className = `btn ${isFallback ? 'btn-success' : 'btn-secondary'} btn-fallback`;
                    fallbackBtn.innerHTML = `<i class="fas fa-${isFallback ? 'stop' : 'play'}"></i> ${isFallback ? 'Fallback ON' : 'Fallback'}`;
                }
            }
        });
    }

    async toggleSceneFallback(sceneId) {
        // Use the new scene fallback with delay functionality
        await this.toggleSceneFallbackWithDelay(sceneId);
    }

    async toggleSequenceFallback(sequenceId) {
        const isCurrentlyFallback = this.fallbackConfig?.config?.type === 'sequence' && 
                                   this.fallbackConfig?.config?.id === sequenceId;
        
        if (isCurrentlyFallback) {
            await this.disableFallback();
        } else {
            await this.setFallback('sequence', sequenceId, true);
        }
        
        // Refresh sequences to update fallback indicators
        this.renderSequences();
    }

    updateSceneFallbackButton(sceneId) {
        const fallbackBtn = document.getElementById('scene-fallback-btn');
        const sceneFallbackConfig = this.fallbackConfig?.config?.scene_fallback;
        const isFallback = sceneFallbackConfig?.enabled && sceneFallbackConfig?.scene_id === sceneId;
        
        fallbackBtn.className = `btn ${isFallback ? 'btn-success' : 'btn-secondary'} btn-fallback`;
        fallbackBtn.innerHTML = `<i class="fas fa-${isFallback ? 'stop' : 'play'}"></i> ${isFallback ? 'Fallback ON' : 'Set Fallback'}`;
    }

    updateSequenceFallbackButton(sequenceId) {
        const fallbackBtn = document.getElementById('sequence-fallback-btn');
        const sequenceFallbackConfig = this.fallbackConfig?.config?.sequence_fallback;
        const isFallback = sequenceFallbackConfig?.enabled && sequenceFallbackConfig?.sequence_id === sequenceId;
        
        fallbackBtn.className = `btn ${isFallback ? 'btn-success' : 'btn-secondary'} btn-fallback`;
        fallbackBtn.innerHTML = `<i class="fas fa-${isFallback ? 'stop' : 'play'}"></i> ${isFallback ? 'Fallback ON' : 'Set Fallback'}`;
    }

    async toggleSceneFallbackFromEditor() {
        const modal = document.getElementById('scene-editor');
        const sceneId = modal.dataset.sceneId;
        
        if (sceneId) {
            const sceneFallbackConfig = this.fallbackConfig?.config?.scene_fallback;
            const isCurrentlyFallback = sceneFallbackConfig?.enabled && sceneFallbackConfig?.scene_id === sceneId;
            
            if (isCurrentlyFallback) {
                // Disable scene fallback
                await this.setSceneFallback(sceneId, false);
            } else {
                // Enable scene fallback with this scene (using global delay setting)
                const fallbackDelay = parseFloat(document.getElementById('fallback-delay').value) || 1.0;
                await this.setSceneFallback(sceneId, true, fallbackDelay);
            }
            
            this.updateSceneFallbackButton(sceneId);
        }
    }

    async toggleSequenceFallbackFromEditor() {
        const modal = document.getElementById('sequence-editor');
        const sequenceId = modal.dataset.sequenceId;
        
        if (sequenceId) {
            const sequenceFallbackConfig = this.fallbackConfig?.config?.sequence_fallback;
            const isCurrentlyFallback = sequenceFallbackConfig?.enabled && sequenceFallbackConfig?.sequence_id === sequenceId;
            
            if (isCurrentlyFallback) {
                // Disable sequence fallback
                await this.setSequenceFallback(sequenceId, false);
            } else {
                // Enable sequence fallback with this sequence (using global delay setting)
                const fallbackDelay = parseFloat(document.getElementById('fallback-delay').value) || 1.0;
                await this.setSequenceFallback(sequenceId, true, fallbackDelay);
            }
            
            this.updateSequenceFallbackButton(sequenceId);
        }
    }

    async setSceneFallback(sceneId, enabled = true, delay = 1.0) {
        try {
            const response = await fetch(`${this.apiUrl}/fallback`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    scene_fallback: {
                        enabled: enabled,
                        scene_id: sceneId,
                        delay: delay
                    }
                })
            });
            
            if (response.ok) {
                await this.loadFallbackConfig();
                this.showNotification(`Scene fallback ${enabled ? 'enabled' : 'disabled'} for scene '${sceneId}' with ${delay}s delay`, 'success');
            } else {
                throw new Error('Failed to set scene fallback');
            }
        } catch (error) {
            console.error('Failed to set scene fallback:', error);
            this.showNotification('Failed to set scene fallback', 'error');
        }
    }

    async setSequenceFallback(sequenceId, enabled = true, delay = 1.0) {
        try {
            const response = await fetch(`${this.apiUrl}/fallback`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sequence_fallback: {
                        enabled: enabled,
                        scene_id: 'blackout', // Sequence fallback always triggers a scene (default: blackout)
                        delay: delay
                    }
                })
            });
            
            if (response.ok) {
                await this.loadFallbackConfig();
                this.showNotification(`Sequence fallback ${enabled ? 'enabled' : 'disabled'} with ${delay}s delay`, 'success');
            } else {
                throw new Error('Failed to set sequence fallback');
            }
        } catch (error) {
            console.error('Failed to set sequence fallback:', error);
            this.showNotification('Failed to set sequence fallback', 'error');
        }
    }

    async toggleSceneFallbackWithDelay(sceneId) {
        const sceneFallbackConfig = this.fallbackConfig?.config?.scene_fallback;
        const isCurrentlyFallback = sceneFallbackConfig?.enabled && sceneFallbackConfig?.scene_id === sceneId;
        
        if (isCurrentlyFallback) {
            // Disable scene fallback
            document.getElementById('scene-fallback-enabled').checked = false;
            await this.updateSceneFallbackConfig();
        } else {
            // Enable scene fallback with this scene
            const globalDelay = parseFloat(document.getElementById('scene-fallback-delay').value) || 1.0;
            document.getElementById('scene-fallback-enabled').checked = true;
            document.getElementById('scene-fallback-scene').value = sceneId;
            await this.updateSceneFallbackConfig();
        }
        
        // Refresh scenes to update fallback indicators
        this.renderScenes();
    }

    async updateSceneFallbackConfig() {
        const enabled = document.getElementById('scene-fallback-enabled').checked;
        const delay = parseFloat(document.getElementById('scene-fallback-delay').value) || 1.0;
        const sceneId = document.getElementById('scene-fallback-scene').value;
        
        try {
            const response = await fetch(`${this.apiUrl}/fallback`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    global_scene_fallback: {
                        enabled: enabled,
                        scene_id: sceneId,
                        delay: delay
                    }
                })
            });
            
            if (response.ok) {
                await this.loadFallbackConfig();
                this.showNotification(`Global scene fallback ${enabled ? 'enabled' : 'disabled'} for scene '${sceneId}' with ${delay}s delay`, 'success');
            } else {
                throw new Error('Failed to update global scene fallback');
            }
        } catch (error) {
            console.error('Failed to update global scene fallback:', error);
            this.showNotification('Failed to update global scene fallback', 'error');
        }
    }

    async loadDMXRetransmissionSettings() {
        try {
            const response = await fetch(`${this.apiUrl}/settings/dmx-retransmission`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    document.getElementById('dmx-retransmission-enabled').checked = data.data.enabled;
                    document.getElementById('dmx-retransmission-interval').value = data.data.interval;
                    document.getElementById('dmx-retransmission-interval').disabled = !data.data.enabled;
                }
            }
        } catch (error) {
            console.error('Failed to load DMX retransmission settings:', error);
        }
    }

    async saveDMXRetransmissionSettings() {
        const enabled = document.getElementById('dmx-retransmission-enabled').checked;
        const interval = parseFloat(document.getElementById('dmx-retransmission-interval').value) || 5.0;
        try {
            const response = await fetch(`${this.apiUrl}/settings/dmx-retransmission`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled, interval })
            });
            if (response.ok) {
                this.showNotification(`DMX retransmission ${enabled ? 'enabled' : 'disabled'} (interval: ${interval}s)`, 'success');
            } else {
                throw new Error('Failed to save DMX retransmission settings');
            }
        } catch (error) {
            console.error('Failed to save DMX retransmission settings:', error);
            this.showNotification('Failed to save DMX retransmission settings', 'error');
        }
    }

    setupDMXRetransmissionListeners() {
        const enabledInput = document.getElementById('dmx-retransmission-enabled');
        const intervalInput = document.getElementById('dmx-retransmission-interval');
        if (enabledInput && intervalInput) {
            enabledInput.addEventListener('change', () => {
                intervalInput.disabled = !enabledInput.checked;
                this.saveDMXRetransmissionSettings();
            });
            intervalInput.addEventListener('input', () => {
                this.saveDMXRetransmissionSettings();
            });
        }
    }


    // Settings Management
    loadSettings() {
        const settings = JSON.parse(localStorage.getItem('dmxConsoleSettings') || '{}');
        this.channelCount = settings.channelCount || this.channelCount;
        document.getElementById('channel-count').value = this.channelCount;
        
        // Load fallback delay setting
        const fallbackDelay = settings.fallbackDelay || 1.0;
        document.getElementById('fallback-delay').value = fallbackDelay;
    }

    saveSettings() {
        const settings = {
            channelCount: this.channelCount,
            fallbackDelay: parseFloat(document.getElementById('fallback-delay').value) || 1.0
        };
        localStorage.setItem('dmxConsoleSettings', JSON.stringify(settings));
    }

    async saveFallbackDelayToBackend() {
        try {
            const delay = parseFloat(document.getElementById('fallback-delay').value) || 1.0;
            const response = await fetch(`${this.apiUrl}/settings/fallback-delay`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ delay: delay })
            });
            
            if (response.ok) {
                this.showNotification(`Fallback delay set to ${delay}s`, 'success');
            } else {
                throw new Error('Failed to save fallback delay');
            }
        } catch (error) {
            console.error('Failed to save fallback delay:', error);
            this.showNotification('Failed to save fallback delay', 'error');
        }
    }

    // Utility Functions
    showNotification(message, type = 'info') {
        const notification = document.getElementById('notification');
        notification.textContent = message;
        notification.className = `notification ${type}`;
        notification.classList.add('show');

        setTimeout(() => {
            notification.classList.remove('show');
        }, 3000);
    }
}

// Global functions for onclick handlers
let dmxConsole;

// Initialize console when page loads
document.addEventListener('DOMContentLoaded', () => {
    dmxConsole = new DMXConsole();
    // Explicitly bind the stop button to the async function
    const stopBtn = document.getElementById('stop-btn');
    if (stopBtn) {
        stopBtn.onclick = async function() {
            console.log('Stop button clicked');
            await dmxConsole.stopSequence();
        };
    }
});

// Global functions for HTML onclick handlers
function blackout() { dmxConsole.blackout(); }
function setAllChannels(value) { dmxConsole.setAllChannels(value); }
function testConnection() { dmxConsole.testConnection(); }
function openSceneEditor(id) { dmxConsole.openSceneEditor(id); }
function closeSceneEditor() { dmxConsole.closeSceneEditor(); }
function saveScene() { dmxConsole.saveScene(); }
function openSequenceEditor(id) { dmxConsole.openSequenceEditor(id); }
function closeSequenceEditor() { dmxConsole.closeSequenceEditor(); }
function saveSequence() { dmxConsole.saveSequence(); }
function addSequenceStep() { dmxConsole.addSequenceStep(); }
function editStep(index) { dmxConsole.editStep(index); }
function closeStepEditor() { dmxConsole.closeStepEditor(); }
function saveStep() { dmxConsole.saveStep(); }
function removeStep(index) { dmxConsole.removeStep(index); }
function playSequence(id) { dmxConsole.playSequence(id); }
function pauseSequence() { dmxConsole.pauseSequence(); }
async function stopSequence() { await dmxConsole.stopSequence(); }
function togglePlayback() { dmxConsole.togglePlayback(); }
function toggleSceneAutostart(id) { dmxConsole.toggleSceneAutostart(id); }
function toggleSequenceAutostart(id) { dmxConsole.toggleSequenceAutostart(id); }
function toggleSceneAutostartFromEditor() { dmxConsole.toggleSceneAutostartFromEditor(); }
function toggleSequenceAutostartFromEditor() { dmxConsole.toggleSequenceAutostartFromEditor(); }
function deleteSceneFromEditor() { dmxConsole.deleteSceneFromEditor(); }
function deleteSequenceFromEditor() { dmxConsole.deleteSequenceFromEditor(); }
function toggleSceneFallback(id) { dmxConsole.toggleSceneFallback(id); }
function toggleSequenceFallback(id) { dmxConsole.toggleSequenceFallback(id); }
function toggleSceneFallbackFromEditor() { dmxConsole.toggleSceneFallbackFromEditor(); }
function toggleSequenceFallbackFromEditor() { dmxConsole.toggleSequenceFallbackFromEditor(); }
function toggleSceneFallbackWithDelay(id) { dmxConsole.toggleSceneFallbackWithDelay(id); }
function openProgrammableEditor(id) { dmxConsole.openProgrammableEditor(id); }
function closeProgrammableEditor() { dmxConsole.closeProgrammableEditor(); }
function saveProgrammable() { dmxConsole.saveProgrammable(); }
function deleteProgrammableFromEditor() { dmxConsole.deleteProgrammableFromEditor(); }
function toggleProgrammableAutostartFromEditor() { dmxConsole.toggleProgrammableAutostartFromEditor(); }
function toggleProgrammableFallbackFromEditor() { dmxConsole.toggleProgrammableFallbackFromEditor(); }
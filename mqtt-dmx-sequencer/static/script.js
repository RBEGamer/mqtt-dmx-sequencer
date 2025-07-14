// MQTT DMX Sequencer Console JavaScript
class DMXConsole {
    constructor() {
        this.apiUrl = window.location.origin + '/api';
        this.channelCount = 24;
        this.currentChannels = new Array(512).fill(0);
        this.scenes = [];
        this.sequences = [];
        this.currentSequence = null;
        this.isPlaying = false;
        this.currentStep = 0;
        this.stepTimer = null;
        this.sequenceTimer = null;
        this.autostartConfig = null;
        
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadSettings();
        this.generateFaders();
        this.updateTime();
        this.testConnection();
        this.loadScenes();
        this.loadSequences();
        this.loadAutostartConfig();
        
        // Update time every second
        setInterval(() => this.updateTime(), 1000);
        
        // Sync sliders with current DMX state every 5 seconds
        setInterval(() => this.syncSlidersWithDMX(), 5000);
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
            fader.innerHTML = `
                <div class="fader-label">CH${i}</div>
                <input type="range" class="fader-slider" min="0" max="255" value="0" 
                       data-channel="${i}">
                <div class="fader-value">0</div>
            `;

            const slider = fader.querySelector('.fader-slider');
            const valueDisplay = fader.querySelector('.fader-value');

            slider.addEventListener('input', (e) => {
                const value = parseInt(e.target.value);
                const channel = parseInt(e.target.dataset.channel);
                this.currentChannels[channel - 1] = value;
                valueDisplay.textContent = value;
                this.sendDMXChannel(channel, value);
            });

            container.appendChild(fader);
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
        const fadeInput = document.getElementById('scene-fade-time');
        const deleteBtn = document.getElementById('scene-delete-btn');
        const autostartBtn = document.getElementById('scene-autostart-btn');

        if (sceneId) {
            const scene = this.scenes.find(s => s.id === sceneId);
            if (scene) {
                title.textContent = 'Edit Scene';
                nameInput.value = scene.name;
                descInput.value = scene.description || '';
                fadeInput.value = scene.fade_time || 1000;
                this.generateChannelEditor(scene.channels);
                
                // Show delete button for existing scenes
                deleteBtn.style.display = 'block';
                
                // Update autostart button state
                this.updateSceneAutostartButton(sceneId);
            }
        } else {
            title.textContent = 'New Scene';
            nameInput.value = '';
            descInput.value = '';
            fadeInput.value = 1000;
            this.generateChannelEditor(this.currentChannels);
            
            // Hide delete button for new scenes
            deleteBtn.style.display = 'none';
            
            // Reset autostart button
            autostartBtn.className = 'btn btn-secondary btn-autostart';
            autostartBtn.innerHTML = '<i class="fas fa-play"></i> Set Autostart';
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
        const fadeTime = parseInt(document.getElementById('scene-fade-time').value);

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
            
            const card = document.createElement('div');
            card.className = 'scene-card';
            if (isAutostart) {
                card.classList.add('autostart-active');
            }
            card.dataset.sceneId = scene.id;
            card.innerHTML = `
                <div class="card-header">
                    <h4>${scene.name}</h4>
                    ${isAutostart ? '<div class="autostart-indicator" title="Autostart Enabled"><i class="fas fa-circle"></i></div>' : ''}
                </div>
                <p>${scene.description || 'No description'}</p>
                <div class="card-actions">
                    <button class="btn btn-primary" onclick="console.playScene('${scene.id}')">
                        <i class="fas fa-play"></i> Play
                    </button>
                    <button class="btn btn-secondary" onclick="console.openSceneEditor('${scene.id}')">
                        <i class="fas fa-edit"></i> Edit
                    </button>
                </div>
            `;
            container.appendChild(card);
        });
    }

    async playScene(sceneId) {
        try {
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
                // Update current channels with scene values
                if (scene.channels && Array.isArray(scene.channels)) {
                    // Update the currentChannels array with scene values
                    for (let i = 0; i < Math.min(scene.channels.length, this.currentChannels.length); i++) {
                        this.currentChannels[i] = scene.channels[i] || 0;
                    }
                    
                    // Update the sidebar sliders to reflect the scene values
                    this.updateAllFaders();
                }
                
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
            <div class="step-info">
                <h5>Step ${stepIndex + 1}</h5>
                <p>Click to configure</p>
            </div>
            <div class="step-actions">
                <button class="btn-icon" onclick="console.editStep(${stepIndex})" title="Edit">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn-icon danger" onclick="console.removeStep(${stepIndex})" title="Remove">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        
        stepsContainer.appendChild(stepDiv);
    }

    renderSequenceSteps(steps) {
        const container = document.getElementById('sequence-steps');
        container.innerHTML = '';

        steps.forEach((step, index) => {
            const stepDiv = document.createElement('div');
            stepDiv.className = 'step-item';
            stepDiv.innerHTML = `
                <div class="step-info">
                    <h5>Step ${index + 1}</h5>
                    <p>Scene: ${step.scene_name || 'Unknown'}, Duration: ${step.duration}ms</p>
                </div>
                <div class="step-actions">
                    <button class="btn-icon" onclick="console.editStep(${index})" title="Edit">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn-icon danger" onclick="console.removeStep(${index})" title="Remove">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            `;
            container.appendChild(stepDiv);
        });
    }

    editStep(stepIndex) {
        // Load available scenes for step selection
        const sceneSelect = document.getElementById('step-scene');
        sceneSelect.innerHTML = '<option value="">Select a scene</option>';
        
        this.scenes.forEach(scene => {
            const option = document.createElement('option');
            option.value = scene.id;
            option.textContent = scene.name;
            sceneSelect.appendChild(option);
        });

        // Show step editor modal
        const modal = document.getElementById('step-editor');
        modal.dataset.stepIndex = stepIndex;
        modal.style.display = 'block';
    }

    closeStepEditor() {
        document.getElementById('step-editor').style.display = 'none';
    }

    saveStep() {
        const modal = document.getElementById('step-editor');
        const stepIndex = parseInt(modal.dataset.stepIndex);
        const sceneId = document.getElementById('step-scene').value;
        const duration = parseInt(document.getElementById('step-duration').value);
        const fade = parseInt(document.getElementById('step-fade').value);

        if (!sceneId) {
            this.showNotification('Please select a scene', 'error');
            return;
        }

        const scene = this.scenes.find(s => s.id === sceneId);
        const step = {
            scene_id: sceneId,
            scene_name: scene.name,
            duration: duration,
            fade: fade
        };

        // Update the step in the sequence editor
        const stepsContainer = document.getElementById('sequence-steps');
        const stepDiv = stepsContainer.children[stepIndex];
        
        if (stepDiv) {
            stepDiv.querySelector('h5').textContent = `Step ${stepIndex + 1}`;
            stepDiv.querySelector('p').textContent = `Scene: ${scene.name}, Duration: ${duration}ms`;
        }

        this.closeStepEditor();
    }

    removeStep(stepIndex) {
        const stepsContainer = document.getElementById('sequence-steps');
        const stepDiv = stepsContainer.children[stepIndex];
        
        if (stepDiv) {
            stepDiv.remove();
            
            // Renumber remaining steps
            Array.from(stepsContainer.children).forEach((step, index) => {
                step.querySelector('h5').textContent = `Step ${index + 1}`;
                step.querySelectorAll('.btn-icon').forEach(btn => {
                    btn.onclick = () => {
                        if (btn.classList.contains('danger')) {
                            this.removeStep(index);
                        } else {
                            this.editStep(index);
                        }
                    };
                });
            });
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

        // Collect steps data
        const steps = [];
        const stepsContainer = document.getElementById('sequence-steps');
        Array.from(stepsContainer.children).forEach((stepDiv, index) => {
            // This is a simplified version - in a real implementation,
            // you'd store the actual step data when editing
            steps.push({
                scene_id: `scene_${index + 1}`,
                scene_name: `Scene ${index + 1}`,
                duration: 1000,
                fade: 500
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
            
            const card = document.createElement('div');
            card.className = 'sequence-card';
            if (isAutostart) {
                card.classList.add('autostart-active');
            }
            card.dataset.sequenceId = sequence.id;
            card.innerHTML = `
                <div class="card-header">
                    <h4>${sequence.name}</h4>
                    ${isAutostart ? '<div class="autostart-indicator" title="Autostart Enabled"><i class="fas fa-circle"></i></div>' : ''}
                </div>
                <p>${sequence.description || 'No description'}</p>
                <div class="card-actions">
                    <button class="btn btn-primary" onclick="console.playSequence('${sequence.id}')">
                        <i class="fas fa-play"></i> Play
                    </button>
                    <button class="btn btn-secondary" onclick="console.openSequenceEditor('${sequence.id}')">
                        <i class="fas fa-edit"></i> Edit
                    </button>
                </div>
            `;
            container.appendChild(card);
        });
    }

    async playSequence(sequenceId) {
        try {
            const response = await fetch(`${this.apiUrl}/sequences/${sequenceId}/play`, {
                method: 'POST'
            });
            if (response.ok) {
                this.currentSequence = sequenceId;
                this.isPlaying = true;
                this.updatePlaybackInfo();
                this.showNotification('Sequence started', 'success');
            }
        } catch (error) {
            this.showNotification('Failed to start sequence', 'error');
        }
    }

    pauseSequence() {
        this.isPlaying = false;
        if (this.stepTimer) {
            clearTimeout(this.stepTimer);
        }
        this.updatePlaybackInfo();
        this.showNotification('Sequence paused', 'warning');
    }

    stopSequence() {
        this.isPlaying = false;
        this.currentSequence = null;
        this.currentStep = 0;
        if (this.stepTimer) {
            clearTimeout(this.stepTimer);
        }
        if (this.sequenceTimer) {
            clearInterval(this.sequenceTimer);
        }
        this.updatePlaybackInfo();
        this.showNotification('Sequence stopped', 'warning');
    }

    updatePlaybackInfo() {
        document.getElementById('current-sequence').textContent = 
            this.currentSequence ? this.sequences.find(s => s.id === this.currentSequence)?.name || 'Unknown' : 'None';
        document.getElementById('current-step').textContent = `${this.currentStep}/${this.sequences.find(s => s.id === this.currentSequence)?.steps?.length || 0}`;
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

    // Settings Management
    loadSettings() {
        const settings = JSON.parse(localStorage.getItem('dmxConsoleSettings') || '{}');
        this.channelCount = settings.channelCount || this.channelCount;
        document.getElementById('channel-count').value = this.channelCount;
    }

    saveSettings() {
        const settings = {
            channelCount: this.channelCount
        };
        localStorage.setItem('dmxConsoleSettings', JSON.stringify(settings));
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
let console;

// Initialize console when page loads
document.addEventListener('DOMContentLoaded', () => {
    console = new DMXConsole();
});

// Global functions for HTML onclick handlers
function blackout() { console.blackout(); }
function setAllChannels(value) { console.setAllChannels(value); }
function testConnection() { console.testConnection(); }
function openSceneEditor(id) { console.openSceneEditor(id); }
function closeSceneEditor() { console.closeSceneEditor(); }
function saveScene() { console.saveScene(); }
function openSequenceEditor(id) { console.openSequenceEditor(id); }
function closeSequenceEditor() { console.closeSequenceEditor(); }
function saveSequence() { console.saveSequence(); }
function addSequenceStep() { console.addSequenceStep(); }
function editStep(index) { console.editStep(index); }
function closeStepEditor() { console.closeStepEditor(); }
function saveStep() { console.saveStep(); }
function removeStep(index) { console.removeStep(index); }
function playSequence(id) { console.playSequence(id); }
function pauseSequence() { console.pauseSequence(); }
function stopSequence() { console.stopSequence(); }
function toggleSceneAutostart(id) { console.toggleSceneAutostart(id); }
function toggleSequenceAutostart(id) { console.toggleSequenceAutostart(id); }
function toggleSceneAutostartFromEditor() { console.toggleSceneAutostartFromEditor(); }
function toggleSequenceAutostartFromEditor() { console.toggleSequenceAutostartFromEditor(); }
function deleteSceneFromEditor() { console.deleteSceneFromEditor(); }
function deleteSequenceFromEditor() { console.deleteSequenceFromEditor(); } 
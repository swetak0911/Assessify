// Content script for Assessify - Injects widget with Shadow DOM
(function() {
  'use strict';
  
  const UNIQUE_ID = 'afy-widget-container-x7k9';
  const BACKEND_URL = 'http://127.0.0.1:8000/api'; // FastAPI backend
  
  let shadowHost = null;
  let shadowRoot = null;
  let isWidgetVisible = false;
  
  // Model configurations
  const MODELS = {
    openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-5', 'gpt-4', 'o1', 'o1-mini'],
    anthropic: ['claude-3-7-sonnet-20250219', 'claude-3-5-sonnet-20241022', 'claude-4-sonnet-20250514'],
    gemini: ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-2.5-pro', 'gemini-1.5-flash'],
    deepseek: ['deepseek-chat', 'deepseek-coder']
  };
  
  // State
  let currentTab = 'text';
  let currentQuestion = '';
  let isRecording = false;
  let recognition = null;
  let dragOffset = { x: 0, y: 0 };
  let isDragging = false;
  
  // Create and inject widget
  function createWidget() {
    if (shadowHost) return;
    
    // Create shadow host element with unique ID
    shadowHost = document.createElement('div');
    shadowHost.id = UNIQUE_ID;
    shadowHost.style.cssText = 'all: initial; position: fixed; z-index: 2147483647; pointer-events: none;';
    
    // Attach shadow DOM for complete isolation
    shadowRoot = shadowHost.attachShadow({ mode: 'open' });
    
    // Load widget HTML and CSS
    const widgetHtmlUrl = chrome.runtime.getURL('widget.html');
    const widgetCssUrl = chrome.runtime.getURL('widget.css');
    
    Promise.all([
      fetch(widgetHtmlUrl).then(r => r.text()),
      fetch(widgetCssUrl).then(r => r.text())
    ]).then(([html, css]) => {
      // Inject CSS
      const style = document.createElement('style');
      style.textContent = css;
      shadowRoot.appendChild(style);
      
      // Inject HTML
      const container = document.createElement('div');
      container.innerHTML = html;
      shadowRoot.appendChild(container);
      
      // Initialize widget functionality
      initializeWidget();
    }).catch(err => {
      console.error('[Assessify] Failed to load widget:', err);
    });
    
    document.documentElement.appendChild(shadowHost);
  }
  
  // Initialize all widget functionality
  function initializeWidget() {
    const widget = shadowRoot.querySelector('#afy-widget-root');
    if (!widget) {
      console.error('[Assessify] Widget root not found');
      return;
    }
    
    widget.style.pointerEvents = 'auto';
    
    // Setup all functionality
    setupDragging();
    setupTabs();
    setupControls();
    setupModelSelector();
    setupVoiceRecognition();
    setupScreenCapture();
    setupClipboard();
    setupSolveButton();
    setupCopyButton();
  }
  
  // Setup dragging functionality
  function setupDragging() {
    const header = shadowRoot.querySelector('#afy-header');
    const widget = shadowRoot.querySelector('#afy-draggable-window');
    
    if (!header || !widget) return;
    
    header.addEventListener('mousedown', (e) => {
      if (e.target.closest('button') || e.target.closest('input')) return;
      
      isDragging = true;
      const rect = widget.getBoundingClientRect();
      dragOffset.x = e.clientX - rect.left;
      dragOffset.y = e.clientY - rect.top;
      header.style.cursor = 'grabbing';
    });
    
    document.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      
      const newX = e.clientX - dragOffset.x;
      const newY = e.clientY - dragOffset.y;
      
      widget.style.left = `${newX}px`;
      widget.style.top = `${newY}px`;
      widget.style.right = 'auto';
      widget.style.bottom = 'auto';
    });
    
    document.addEventListener('mouseup', () => {
      if (isDragging) {
        isDragging = false;
        const header = shadowRoot.querySelector('#afy-header');
        if (header) header.style.cursor = 'move';
      }
    });
  }
  
  // Setup tab switching
  function setupTabs() {
    const tabs = shadowRoot.querySelectorAll('.afy-tab-btn');
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        shadowRoot.querySelectorAll('.afy-tab-btn').forEach(t => t.classList.remove('active'));
        shadowRoot.querySelectorAll('.afy-tab-content').forEach(c => c.classList.remove('active'));
        
        tab.classList.add('active');
        const tabName = tab.dataset.tab;
        const tabContent = shadowRoot.querySelector(`#afy-tab-${tabName}`);
        if (tabContent) tabContent.classList.add('active');
        currentTab = tabName;
        
        updateSolveButton();
      });
    });
  }
  
  // Setup window controls
  function setupControls() {
    const transparencySlider = shadowRoot.querySelector('#afy-transparency-slider');
    const widget = shadowRoot.querySelector('#afy-draggable-window');
    
    if (transparencySlider && widget) {
      transparencySlider.addEventListener('input', (e) => {
        const opacity = e.target.value / 100;
        widget.style.opacity = opacity;
      });
    }
    
    const minimizeBtn = shadowRoot.querySelector('#afy-minimize-btn');
    const content = shadowRoot.querySelector('#afy-content');
    
    let isMinimized = false;
    if (minimizeBtn && content) {
      minimizeBtn.addEventListener('click', () => {
        isMinimized = !isMinimized;
        content.style.display = isMinimized ? 'none' : 'block';
      });
    }
    
    const closeBtn = shadowRoot.querySelector('#afy-close-btn');
    const widgetRoot = shadowRoot.querySelector('#afy-widget-root');
    
    if (closeBtn && widgetRoot) {
      closeBtn.addEventListener('click', () => {
        hideWidget();
        chrome.runtime.sendMessage({ action: 'widgetClosed' });
      });
    }
  }
  
  // Setup model selector
  function setupModelSelector() {
    const providerSelect = shadowRoot.querySelector('#afy-provider-select');
    const modelSelect = shadowRoot.querySelector('#afy-model-select');
    
    if (!providerSelect || !modelSelect) return;
    
    providerSelect.addEventListener('change', () => {
      const provider = providerSelect.value;
      const models = MODELS[provider];
      
      modelSelect.innerHTML = '';
      models.forEach(model => {
        const option = document.createElement('option');
        option.value = model;
        option.textContent = model;
        modelSelect.appendChild(option);
      });
    });
    
    // Trigger initial load
    providerSelect.dispatchEvent(new Event('change'));
  }
  
  // Setup voice recognition
  function setupVoiceRecognition() {
    const recordBtn = shadowRoot.querySelector('#afy-record-btn');
    const recordText = shadowRoot.querySelector('#afy-record-text');
    const transcriptBox = shadowRoot.querySelector('#afy-transcript-box');
    
    if (!recordBtn || !('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)) {
      if (recordBtn) recordBtn.disabled = true;
      if (transcriptBox) transcriptBox.textContent = 'Speech recognition not supported in this browser';
      return;
    }
    
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    
    recordBtn.addEventListener('click', () => {
      if (!isRecording) {
        recognition.start();
        isRecording = true;
        recordBtn.classList.add('recording');
        recordText.textContent = 'Stop Recording';
        transcriptBox.textContent = 'Listening...';
      } else {
        recognition.stop();
        isRecording = false;
        recordBtn.classList.remove('recording');
        recordText.textContent = 'Start Recording';
      }
    });
    
    recognition.onresult = (event) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      transcriptBox.textContent = transcript;
      currentQuestion = transcript;
      updateSolveButton();
    };
    
    recognition.onerror = (event) => {
      console.error('[Assessify] Speech recognition error:', event.error);
      transcriptBox.textContent = `Error: ${event.error}`;
      isRecording = false;
      recordBtn.classList.remove('recording');
      recordText.textContent = 'Start Recording';
    };
  }
  
  // Setup screen capture
  function setupScreenCapture() {
    const screenshotBtn = shadowRoot.querySelector('#afy-screenshot-btn');
    const scanBtn = shadowRoot.querySelector('#afy-scan-btn');
    
    if (screenshotBtn) {
      screenshotBtn.addEventListener('click', async () => {
        try {
          const stream = await navigator.mediaDevices.getDisplayMedia({ 
            video: { mediaSource: 'screen' } 
          });
          await captureAndOCR(stream, 'Screenshot');
          stream.getTracks().forEach(track => track.stop());
        } catch (error) {
          console.error('[Assessify] Screenshot error:', error);
          showError('Failed to capture screenshot. Please try again.');
        }
      });
    }
    
    if (scanBtn) {
      scanBtn.addEventListener('click', async () => {
        try {
          const stream = await navigator.mediaDevices.getDisplayMedia({ 
            video: { mediaSource: 'screen' } 
          });
          await captureAndOCR(stream, 'Full Screen');
          stream.getTracks().forEach(track => track.stop());
        } catch (error) {
          console.error('[Assessify] Screen scan error:', error);
          showError('Failed to scan screen. Please try again.');
        }
      });
    }
  }
  
  // Capture and OCR
  async function captureAndOCR(stream, type) {
    const video = document.createElement('video');
    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;
    
    await new Promise((resolve) => {
      video.onloadedmetadata = () => {
        video.play();
        resolve();
      };
    });
    
    // Wait for video to be ready
    await new Promise(resolve => setTimeout(resolve, 100));
    
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);
    
    const imageDataUrl = canvas.toDataURL('image/png');
    
    showLoading(`Processing ${type}...`);
    
    try {
      const result = await sendApiRequest('/ocr-image', 'POST', {
        image_base64: imageDataUrl
      });
      
      if (result.success && result.data) {
        currentQuestion = result.data.extracted_text;
        const textInput = shadowRoot.querySelector('#afy-text-input');
        if (textInput) textInput.value = result.data.extracted_text;
        
        // Switch to text tab
        const textTab = shadowRoot.querySelector('.afy-tab-btn[data-tab="text"]');
        if (textTab) textTab.click();
        
        hideLoading();
        updateSolveButton();
      } else {
        throw new Error(result.error || 'OCR failed');
      }
    } catch (error) {
      console.error('[Assessify] OCR error:', error);
      hideLoading();
      showError(`OCR failed: ${error.message}`);
    }
  }
  
  // Setup clipboard paste
  function setupClipboard() {
    const pasteBtn = shadowRoot.querySelector('#afy-paste-clipboard');
    const textInput = shadowRoot.querySelector('#afy-text-input');
    
    if (pasteBtn && textInput) {
      pasteBtn.addEventListener('click', async () => {
        try {
          const text = await navigator.clipboard.readText();
          textInput.value = text;
          currentQuestion = text;
          updateSolveButton();
        } catch (error) {
          console.error('[Assessify] Clipboard error:', error);
          showError('Failed to read clipboard. Please paste manually.');
        }
      });
    }
    
    if (textInput) {
      textInput.addEventListener('input', (e) => {
        currentQuestion = e.target.value;
        updateSolveButton();
      });
    }
  }
  
  // Setup solve button
  function setupSolveButton() {
    const solveBtn = shadowRoot.querySelector('#afy-solve-btn');
    
    if (solveBtn) {
      solveBtn.addEventListener('click', async () => {
        const question = getCurrentQuestion();
        if (!question) return;
        
        const provider = shadowRoot.querySelector('#afy-provider-select').value;
        const model = shadowRoot.querySelector('#afy-model-select').value;
        
        await generateSolution(question, provider, model);
      });
    }
  }
  
  // Setup copy button
  function setupCopyButton() {
    const copyBtn = shadowRoot.querySelector('#afy-copy-btn');
    
    if (copyBtn) {
      copyBtn.addEventListener('click', () => {
        const solutionText = shadowRoot.querySelector('#afy-solution-text');
        if (solutionText) {
          navigator.clipboard.writeText(solutionText.textContent).then(() => {
            const originalHTML = copyBtn.innerHTML;
            copyBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg> Copied!';
            setTimeout(() => {
              copyBtn.innerHTML = originalHTML;
            }, 2000);
          }).catch(err => {
            console.error('[Assessify] Copy failed:', err);
            showError('Failed to copy to clipboard');
          });
        }
      });
    }
  }
  
  function getCurrentQuestion() {
    if (currentTab === 'text') {
      const textInput = shadowRoot.querySelector('#afy-text-input');
      return textInput ? textInput.value : '';
    } else if (currentTab === 'voice') {
      const transcriptBox = shadowRoot.querySelector('#afy-transcript-box');
      return transcriptBox ? transcriptBox.textContent : '';
    }
    return currentQuestion;
  }
  
  function updateSolveButton() {
    const solveBtn = shadowRoot.querySelector('#afy-solve-btn');
    const question = getCurrentQuestion();
    if (solveBtn) {
      solveBtn.disabled = !question || question.trim().length === 0;
    }
  }
  
  async function generateSolution(question, provider, model) {
    const outputSection = shadowRoot.querySelector('#afy-output-section');
    const solutionText = shadowRoot.querySelector('#afy-solution-text');
    
    showLoading('Generating solution...');
    
    try {
      const result = await sendApiRequest('/solve-code', 'POST', {
        question,
        model_provider: provider,
        model_name: model,
        session_id: generateSessionId()
      });
      
      console.log('[Assessify] API Response:', result);
      
      hideLoading();
      
      if (result.success && result.data) {
        if (outputSection && solutionText) {
          outputSection.style.display = 'block';
          solutionText.textContent = result.data.solution || JSON.stringify(result.data, null, 2);
        }
      } else {
        throw new Error(result.error || 'Invalid response structure');
      }
    } catch (error) {
      console.error('[Assessify] Generation error:', error);
      hideLoading();
      
      if (solutionText) {
        solutionText.textContent = `Error: ${error.message}\n\nPlease check:\n1. Backend is running at ${BACKEND_URL}\n2. EMERGENT_LLM_KEY is configured in backend .env\n3. Internet connection is active`;
      }
      if (outputSection) {
        outputSection.style.display = 'block';
      }
    }
  }
  
  // API request helper using background script proxy
  async function sendApiRequest(endpoint, method = 'POST', body = null) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({
        action: 'apiRequest',
        data: { endpoint, method, body }
      }, (response) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
        } else if (response.success) {
          resolve(response);
        } else {
          reject(new Error(response.error || 'API request failed'));
        }
      });
    });
  }
  
  // Helper functions
  function showLoading(message) {
    const solveBtn = shadowRoot.querySelector('#afy-solve-btn');
    if (solveBtn) {
      solveBtn.disabled = true;
      solveBtn.innerHTML = `<div class="afy-spinner"></div>${message}`;
    }
  }
  
  function hideLoading() {
    const solveBtn = shadowRoot.querySelector('#afy-solve-btn');
    if (solveBtn) {
      solveBtn.disabled = false;
      solveBtn.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="9 18 15 12 9 6"></polyline>
        </svg>
        Generate Solution
      `;
      updateSolveButton();
    }
  }
  
  function showError(message) {
    const solutionText = shadowRoot.querySelector('#afy-solution-text');
    const outputSection = shadowRoot.querySelector('#afy-output-section');
    
    if (solutionText) {
      solutionText.textContent = `⚠️ ${message}`;
    }
    if (outputSection) {
      outputSection.style.display = 'block';
    }
  }
  
  function generateSessionId() {
    return 'session-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
  }
  
  function showWidget() {
    if (!shadowHost) createWidget();
    const widget = shadowRoot?.querySelector('#afy-widget-root');
    if (widget) {
      widget.style.display = 'block';
      isWidgetVisible = true;
    }
  }
  
  function hideWidget() {
    const widget = shadowRoot?.querySelector('#afy-widget-root');
    if (widget) {
      widget.style.display = 'none';
      isWidgetVisible = false;
    }
  }
  
  // Listen for messages from background script
  chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'show') {
      showWidget();
    } else if (request.action === 'hide') {
      hideWidget();
    }
    sendResponse({success: true});
  });
  
  // Auto-inject on load (hidden by default)
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', createWidget);
  } else {
    createWidget();
  }
})();

// Background service worker for Assessify
let widgetVisible = {};

const BACKEND_URL = 'http://127.0.0.1:8000/api';

chrome.action.onClicked.addListener((tab) => {
  const tabId = tab.id;
  
  widgetVisible[tabId] = !widgetVisible[tabId];
  
  chrome.tabs.sendMessage(tabId, {
    action: widgetVisible[tabId] ? 'show' : 'hide'
  }, (response) => {
    if (chrome.runtime.lastError) {
      console.warn('No receiver found — injecting content script...');
      
      chrome.scripting.executeScript({
        target: { tabId: tabId },
        files: ['content.js']
      }, () => {
        chrome.tabs.sendMessage(tabId, {
          action: widgetVisible[tabId] ? 'show' : 'hide'
        });
      });
    }
  });
});

chrome.tabs.onRemoved.addListener((tabId) => {
  delete widgetVisible[tabId];
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'widgetClosed' && sender.tab) {
    widgetVisible[sender.tab.id] = false;
    sendResponse({ success: true });
    return true;
  }
  
  if (request.action === 'apiRequest') {
    (async () => {
      try {
        const { endpoint, method, body } = request.data;
        
        const response = await fetch(`${BACKEND_URL}${endpoint}`, {
          method: method || 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: body ? JSON.stringify(body) : undefined
        });

        const data = await response.json();
        
        if (!response.ok) {
          throw new Error(data.detail || `HTTP error! status: ${response.status}`);
        }
        
        sendResponse({ success: true, data: data });
      } catch (error) {
        console.error('[BG] API Error:', error);
        sendResponse({ success: false, error: error.message });
      }
    })();
    return true;
  }
  
  sendResponse({ success: true });
  return true;
});

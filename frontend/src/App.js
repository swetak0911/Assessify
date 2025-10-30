import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import axios from 'axios';
import { Mic, MicOff, Image, Scan, Copy, CheckCircle2, Loader2, Code2, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Model configurations
const MODELS = {
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-5', 'gpt-4', 'o1', 'o1-mini'],
  anthropic: ['claude-3-7-sonnet-20250219', 'claude-3-5-sonnet-20241022', 'claude-4-sonnet-20250514'],
  gemini: ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-2.5-pro', 'gemini-1.5-flash'],
  deepseek: ['deepseek-chat', 'deepseek-coder']
};

function App() {
  const [activeTab, setActiveTab] = useState('text');
  const [question, setQuestion] = useState('');
  const [provider, setProvider] = useState('openai');
  const [model, setModel] = useState('gpt-4o-mini');
  const [solution, setSolution] = useState('');
  const [loading, setLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [sessions, setSessions] = useState([]);
  const recognitionRef = useRef(null);

  useEffect(() => {
    fetchSessions();
    setupSpeechRecognition();
  }, []);

  const setupSpeechRecognition = () => {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = true;
      recognitionRef.current.interimResults = true;

      recognitionRef.current.onresult = (event) => {
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript;
        }
        setTranscript(transcript);
        setQuestion(transcript);
      };

      recognitionRef.current.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        toast.error(`Speech recognition error: ${event.error}`);
        setIsRecording(false);
      };
    }
  };

  const fetchSessions = async () => {
    try {
      const response = await axios.get(`${API}/sessions`);
      setSessions(response.data.slice(0, 10));
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    }
  };

  const handleProviderChange = (e) => {
    const newProvider = e.target.value;
    setProvider(newProvider);
    setModel(MODELS[newProvider][0]);
  };

  const handlePasteClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText();
      setQuestion(text);
      toast.success('Text pasted from clipboard!');
    } catch (error) {
      toast.error('Failed to read clipboard. Please paste manually.');
    }
  };

  const toggleRecording = () => {
    if (!recognitionRef.current) {
      toast.error('Speech recognition not supported in this browser');
      return;
    }

    if (isRecording) {
      recognitionRef.current.stop();
      setIsRecording(false);
    } else {
      recognitionRef.current.start();
      setIsRecording(true);
      setTranscript('');
    }
  };

  const captureScreen = async (type) => {
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { mediaSource: 'screen' }
      });

      const video = document.createElement('video');
      video.srcObject = stream;
      video.play();

      await new Promise(resolve => {
        video.onloadedmetadata = resolve;
      });

      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0);

      const imageDataUrl = canvas.toDataURL('image/png');
      stream.getTracks().forEach(track => track.stop());

      // Send to OCR
      toast.info(`Processing ${type}...`);
      const response = await axios.post(`${API}/ocr-image`, {
        image_base64: imageDataUrl
      });

      setQuestion(response.data.extracted_text);
      setActiveTab('text');
      toast.success('Text extracted successfully!');
    } catch (error) {
      console.error('Screen capture error:', error);
      toast.error('Failed to capture screen. Please try again.');
    }
  };

  const generateSolution = async () => {
    if (!question.trim()) {
      toast.error('Please enter a question!');
      return;
    }

    setLoading(true);
    setSolution('');

    try {
      const response = await axios.post(`${API}/solve-code`, {
        question,
        model_provider: provider,
        model_name: model
      });

      setSolution(response.data.solution);
      toast.success('Solution generated!');
      fetchSessions();
    } catch (error) {
      console.error('Generation error:', error);
      toast.error('Failed to generate solution. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const copySolution = () => {
    navigator.clipboard.writeText(solution);
    toast.success('Solution copied to clipboard!');
  };

  return (
    <div className="app-container">
      {/* Header */}
      <header className="app-header">
        <div className="header-content">
          <div className="logo">
            <Code2 className="logo-icon" />
            <h1>Assessify</h1>
          </div>
          <p className="tagline">AI-Powered Coding Interview Assistant</p>
        </div>
      </header>

      <div className="main-content">
        {/* Left Panel - Input */}
        <div className="input-panel">
          <div className="panel-card">
            <div className="card-header">
              <Sparkles className="header-icon" />
              <h2>Ask Your Question</h2>
            </div>

            {/* Tabs */}
            <div className="tabs">
              <button
                className={`tab ${activeTab === 'text' ? 'active' : ''}`}
                onClick={() => setActiveTab('text')}
              >
                📝 Text
              </button>
              <button
                className={`tab ${activeTab === 'screenshot' ? 'active' : ''}`}
                onClick={() => setActiveTab('screenshot')}
              >
                📸 Screenshot
              </button>
              <button
                className={`tab ${activeTab === 'voice' ? 'active' : ''}`}
                onClick={() => setActiveTab('voice')}
              >
                🎤 Voice
              </button>
              <button
                className={`tab ${activeTab === 'scan' ? 'active' : ''}`}
                onClick={() => setActiveTab('scan')}
              >
                🖥️ Scan
              </button>
            </div>

            {/* Tab Content */}
            <div className="tab-content">
              {activeTab === 'text' && (
                <div className="text-input-section">
                  <textarea
                    className="question-input"
                    placeholder="Paste or type your coding question here...\n\nExample: Write a function to find the longest palindromic substring in a given string."
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    rows={10}
                  />
                  <button className="btn-secondary" onClick={handlePasteClipboard}>
                    📋 Paste from Clipboard
                  </button>
                </div>
              )}

              {activeTab === 'screenshot' && (
                <div className="capture-section">
                  <button className="capture-btn" onClick={() => captureScreen('Screenshot')}>
                    <Image size={48} />
                    <div className="capture-text">Capture Screenshot</div>
                    <div className="capture-hint">Click to capture specific area</div>
                  </button>
                </div>
              )}

              {activeTab === 'voice' && (
                <div className="voice-section">
                  <button
                    className={`record-btn ${isRecording ? 'recording' : ''}`}
                    onClick={toggleRecording}
                  >
                    {isRecording ? <MicOff size={20} /> : <Mic size={20} />}
                    {isRecording ? 'Stop Recording' : 'Start Recording'}
                  </button>
                  <div className="transcript-box">
                    {transcript || 'Transcript will appear here...'}
                  </div>
                </div>
              )}

              {activeTab === 'scan' && (
                <div className="capture-section">
                  <button className="capture-btn" onClick={() => captureScreen('Full Screen')}>
                    <Scan size={48} />
                    <div className="capture-text">Scan Full Screen</div>
                    <div className="capture-hint">Captures entire screen with OCR</div>
                  </button>
                </div>
              )}
            </div>

            {/* Model Selection */}
            <div className="model-section">
              <div className="model-header">
                <h3>AI Model</h3>
              </div>
              <div className="model-selectors">
                <select className="model-select" value={provider} onChange={handleProviderChange}>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="gemini">Google Gemini</option>
                  <option value="deepseek">DeepSeek</option>
                </select>
                <select className="model-select" value={model} onChange={(e) => setModel(e.target.value)}>
                  {MODELS[provider].map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Generate Button */}
            <button
              className="btn-primary"
              onClick={generateSolution}
              disabled={loading || !question.trim()}
            >
              {loading ? (
                <>
                  <Loader2 className="spinner" size={20} />
                  Generating Solution...
                </>
              ) : (
                <>
                  <Sparkles size={20} />
                  Generate Solution
                </>
              )}
            </button>
          </div>

          {/* Recent Sessions */}
          {sessions.length > 0 && (
            <div className="panel-card sessions-card">
              <h3>Recent Sessions</h3>
              <div className="sessions-list">
                {sessions.map((session, idx) => (
                  <div key={idx} className="session-item" onClick={() => {
                    setQuestion(session.question);
                    setSolution(session.solution);
                    setProvider(session.model_provider);
                    setModel(session.model_name);
                  }}>
                    <div className="session-question">{session.question.slice(0, 60)}...</div>
                    <div className="session-meta">
                      {session.model_provider} · {session.model_name}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right Panel - Solution */}
        <div className="solution-panel">
          <div className="panel-card">
            <div className="card-header">
              <CheckCircle2 className="header-icon" />
              <h2>Solution</h2>
              {solution && (
                <button className="btn-copy" onClick={copySolution}>
                  <Copy size={16} />
                  Copy
                </button>
              )}
            </div>

            <div className="solution-content">
              {loading ? (
                <div className="loading-state">
                  <Loader2 className="spinner large" size={48} />
                  <p>Generating your solution...</p>
                </div>
              ) : solution ? (
                <pre className="solution-text">{solution}</pre>
              ) : (
                <div className="empty-state">
                  <Code2 size={64} className="empty-icon" />
                  <h3>No Solution Yet</h3>
                  <p>Ask a question and generate a solution to see it here!</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
    
  );
}

export default App;

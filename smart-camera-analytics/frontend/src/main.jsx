import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'

// Global CSS - industrial dark theme with neon accents
const style = document.createElement('style')
style.textContent = `
  :root {
    --bg:         #0a0b0f;
    --sidebar:    #0d0f14;
    --card:       #111318;
    --border:     #1e2028;
    --text:       #e8e9ef;
    --muted:      #52556a;
    --accent:     #00ff9d;
    --accent-bg:  #00ff9d0d;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'DM Sans', system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }

  a { color: inherit; }

  ::-webkit-scrollbar { width: 4px; height: 4px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--muted); }

  input, select, textarea {
    outline: none;
    font-family: inherit;
  }
  input:focus, select:focus, textarea:focus {
    border-color: var(--accent) !important;
  }

  button { font-family: inherit; }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
  }
`
document.head.appendChild(style)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>
)

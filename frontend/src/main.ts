import "./index.css";
import { marked } from "marked";

// Types
interface ResearchSession {
  id: string;
  query: string;
  createdAt: string;
  status: "running" | "completed" | "error";
  rawMarkdown?: string;
  logs: string[];
  activeAgent: string | null;
  elapsedTime?: string;
}

// Global Application State
let activeSessionId: string | null = null;
let eventSource: EventSource | null = null;
let timerInterval: any = null;
let timerSeconds = 0;
let sessions: ResearchSession[] = [];

// DOM Elements cache
const els = {
  viewHero: document.getElementById("view-hero") as HTMLElement,
  viewPipeline: document.getElementById("view-pipeline") as HTMLElement,
  viewReport: document.getElementById("view-report") as HTMLElement,
  queryInput: document.getElementById("research-query-input") as HTMLTextAreaElement,
  btnStartResearch: document.getElementById("btn-start-research") as HTMLButtonElement,
  btnNewResearch: document.getElementById("btn-new-research") as HTMLButtonElement,
  btnCancelPipeline: document.getElementById("btn-cancel-pipeline") as HTMLButtonElement,
  btnCopyReport: document.getElementById("btn-copy-report") as HTMLButtonElement,
  btnCopyText: document.getElementById("btn-copy-text") as HTMLElement,
  btnRestartFromReport: document.getElementById("btn-restart-from-report") as HTMLButtonElement,
  historyContainer: document.getElementById("history-container") as HTMLElement,
  pipelineQueryDisplay: document.getElementById("pipeline-query-display") as HTMLElement,
  activeAgentDisplay: document.getElementById("active-agent-display") as HTMLElement,
  pipelineTimer: document.getElementById("pipeline-timer") as HTMLElement,
  consoleStream: document.getElementById("console-stream") as HTMLElement,
  toolPillsList: document.getElementById("tool-pills-list") as HTMLElement,
  reportBodyContainer: document.getElementById("report-body-container") as HTMLElement,
  reportDateDisplay: document.getElementById("report-date-display") as HTMLElement,
  toastWrapper: document.getElementById("toast-wrapper") as HTMLElement,
  svgCanvas: document.getElementById("dag-svg-canvas") as unknown as SVGSVGElement,
  dagGraphView: document.getElementById("dag-graph-view") as HTMLElement
};

// Agents index configuration
const AGENT_ORDER = [
  "clarifier",
  "planner",
  "searcher",
  "analyzer",
  "reasoner",
  "synthesizer",
  "formatter"
];

// Initialize Application
document.addEventListener("DOMContentLoaded", () => {
  loadSessions();
  setupEventListeners();
  drawEdges();
  
  // Re-draw edges dynamically on resize to keep SVG links perfectly aligned
  window.addEventListener("resize", () => {
    drawEdges();
  });
});

// Load sessions from localStorage
function loadSessions() {
  const localStorageData = localStorage.getItem("research_sessions_v1");
  if (localStorageData) {
    try {
      sessions = JSON.parse(localStorageData);
    } catch (e) {
      console.error("Failed to parse sessions from localStorage, resetting console catalog.", e);
      sessions = [];
    }
  }
  renderHistory();
}

// Save sessions catalog to localStorage
function saveSessions() {
  localStorage.setItem("research_sessions_v1", JSON.stringify(sessions));
}

// Setup Keyboard & Click binding
function setupEventListeners() {
  // Submit research on click
  els.btnStartResearch.addEventListener("click", () => {
    executeResearch();
  });

  // Submit on Ctrl+Enter
  els.queryInput.addEventListener("keydown", (e: KeyboardEvent) => {
    if (e.ctrlKey && e.key === "Enter") {
      e.preventDefault();
      executeResearch();
    }
  });

  // New Research Button
  els.btnNewResearch.addEventListener("click", () => {
    switchToView("hero");
  });

  // Cancel Pipeline running
  els.btnCancelPipeline.addEventListener("click", () => {
    cancelActivePipeline();
  });

  // Copy Markdown Clipboard action
  els.btnCopyReport.addEventListener("click", () => {
    copyMarkdownToClipboard();
  });

  // Start new review from completed report
  els.btnRestartFromReport.addEventListener("click", () => {
    switchToView("hero");
  });
}

// Navigation between screens
function switchToView(view: "hero" | "pipeline" | "report") {
  els.viewHero.classList.remove("active");
  els.viewPipeline.classList.remove("active");
  els.viewReport.classList.remove("active");

  if (view === "hero") {
    els.viewHero.classList.add("active");
    els.queryInput.value = "";
    els.queryInput.focus();
  } else if (view === "pipeline") {
    els.viewPipeline.classList.add("active");
  } else if (view === "report") {
    els.viewReport.classList.add("active");
    // Repainting edge nodes safely to clean graphics memory
    clearTimeout(edgeDrawTimeout);
  }
}

// Generate Toast Alert Notification
function triggerToast(message: string, type: "success" | "info" | "warn" | "error" = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  
  // Custom Icon Selection
  let iconMarkup = "";
  if (type === "success") {
    iconMarkup = `<svg class="toast-icon success" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>`;
  } else if (type === "error") {
    iconMarkup = `<svg class="toast-icon error" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>`;
  } else if (type === "warn") {
    iconMarkup = `<svg class="toast-icon warn" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>`;
  } else {
    iconMarkup = `<svg class="toast-icon info" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>`;
  }

  toast.innerHTML = `
    ${iconMarkup}
    <span class="toast-message">${message}</span>
  `;

  els.toastWrapper.appendChild(toast);

  // Smooth discard animation timeout
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(40px)";
    setTimeout(() => {
      toast.remove();
    }, 400);
  }, 4000);
}

// Sidepanel database list renderer
function renderHistory() {
  const sortedSessions = [...sessions].sort((a,b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  
  if (sortedSessions.length === 0) {
    els.historyContainer.innerHTML = `<li class="history-empty">No past research sessions</li>`;
    return;
  }

  els.historyContainer.innerHTML = sortedSessions.map(session => {
    const formattedTime = new Date(session.createdAt).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
    
    return `
      <li class="history-item ${activeSessionId === session.id ? 'active' : ''}" data-id="${session.id}">
        <div class="history-item-header">
          <span class="history-item-time">${formattedTime}</span>
          <span class="history-item-status ${session.status}"></span>
        </div>
        <span class="history-item-query" title="${session.query}">${escapeHTML(session.query)}</span>
      </li>
    `;
  }).join("");

  // Attach click delegate binders
  document.querySelectorAll(".history-item").forEach(item => {
    item.addEventListener("click", (e) => {
      const id = (e.currentTarget as HTMLElement).getAttribute("data-id");
      if (id) loadSessionById(id);
    });
  });
}

// Click Session inside history menu
function loadSessionById(id: string) {
  const session = sessions.find(s => s.id === id);
  if (!session) return;

  // Halt any running session stream first
  if (eventSource && activeSessionId !== id) {
    cancelActivePipeline(false);
  }

  activeSessionId = id;
  renderHistory();

  if (session.status === "completed" && session.rawMarkdown) {
    displayMarkdownReport(session);
  } else if (session.status === "running") {
    // Restore visual graph container
    restoreRunningSessionUI(session);
  } else {
    // Render error status dashboard summary
    restoreFailedSessionUI(session);
  }
}

// Setup running pipeline view using stored data parameters
function restoreRunningSessionUI(session: ResearchSession) {
  switchToView("pipeline");
  els.pipelineQueryDisplay.textContent = session.query;
  els.activeAgentDisplay.textContent = session.activeAgent || "Unavailable";

  // Repaint logs
  els.consoleStream.innerHTML = "";
  session.logs.forEach(log => {
    appendConsoleLine(log);
  });

  // Calculate elapsed
  els.pipelineTimer.textContent = session.elapsedTime || "00:00";
  
  resetNodeStates();
  
  // Set current node to active, and preceding to complete
  if (session.activeAgent) {
    const activeIdx = AGENT_ORDER.indexOf(session.activeAgent);
    AGENT_ORDER.forEach((agent, idx) => {
      const node = document.getElementById(`node-${agent}`);
      if (node) {
        if (idx < activeIdx) {
          node.className = "dag-node agent-node completed";
        } else if (idx === activeIdx) {
          node.className = "dag-node agent-node active";
        } else {
          node.className = "dag-node agent-node";
        }
      }
    });
  }

  drawEdges();
}

// Setup aborted or error session view
function restoreFailedSessionUI(session: ResearchSession) {
  switchToView("pipeline");
  els.pipelineQueryDisplay.textContent = session.query;
  els.activeAgentDisplay.textContent = "Pipeline Terminated";
  els.pipelineTimer.textContent = "Error";
  
  els.consoleStream.innerHTML = "";
  session.logs.forEach(log => {
    appendConsoleLine(log);
  });
  appendConsoleLine("Error: Pipeline ended with unfinished reviews. Click 'New Research' to start again.");

  resetNodeStates();
  
  // Render current active node in red error highlights
  if (session.activeAgent) {
    const activeNode = document.getElementById(`node-${session.activeAgent}`);
    if (activeNode) activeNode.className = "dag-node agent-node error";
  }

  drawEdges();
}

// Start Stream Execution Request
function executeResearch() {
  const query = els.queryInput.value.trim();
  if (!query) {
    triggerToast("Inquiry query input cannot be empty.", "warn");
    return;
  }

  let pass = localStorage.getItem("research_app_pass");
  if (!pass) {
    pass = prompt("Please enter the access password to run research queries:");
    if (!pass) return;
    localStorage.setItem("research_app_pass", pass);
  }

  // Create unique Session record
  const newSessionId = "session_" + Date.now();
  const session: ResearchSession = {
    id: newSessionId,
    query: query,
    createdAt: new Date().toISOString(),
    status: "running",
    logs: ["Initializing connection to Google ADK system...", "Registering sequential agent nodes (Total: 7)..."],
    activeAgent: "clarifier"
  };

  sessions.push(session);
  activeSessionId = newSessionId;
  saveSessions();
  renderHistory();

  // Reset graph states, parameters, and timer counters
  resetNodeStates();
  els.pipelineQueryDisplay.textContent = query;
  els.consoleStream.innerHTML = "";
  els.toolPillsList.innerHTML = `<span class="empty-shelf shadow-none text-xs text-gray-500">None invoked yet</span>`;
  els.activeAgentDisplay.textContent = "clarifier";
  
  switchToView("pipeline");
  drawEdges();

  // Start clock counter
  startPipelineTimer();

  // Establish SSE Streaming interface
  const encodedQuery = encodeURIComponent(query);
  const streamUrl = `/api/research/stream?query=${encodedQuery}&session_id=${newSessionId}&pass=${encodeURIComponent(pass)}`;
  
  appendConsoleLine("Initial system validation OK.", "system-log-line");
  appendConsoleLine("Requesting real-time SSE stream...", "system-log-line text-indigo-400");
  
  eventSource = new EventSource(streamUrl);

  // Agent Start trigger
  eventSource.addEventListener("agent_start", (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      updateAgentStatus(data.agent, "active");
    } catch (err) {
      console.error(err);
    }
  });

  // Agent character streamed output payload
  eventSource.addEventListener("agent_output", (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      appendConsoleLine(`${data.text}`, "agent-output-block");
    } catch (err) {
      console.error(err);
    }
  });

  // Tool function execution event
  eventSource.addEventListener("tool_call", (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      invokeToolVisual(data.agent, data.tool);
    } catch (err) {
      console.error(err);
    }
  });

  // Agent Finish trigger
  eventSource.addEventListener("agent_end", (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      updateAgentStatus(data.agent, "completed");
    } catch (err) {
      console.error(err);
    }
  });

  // Flow synthesis finished successfully
  eventSource.addEventListener("pipeline_complete", (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      completePipelineSuccess(data.report);
    } catch (err) {
      console.error(err);
    }
  });

  // Encountered exception
  eventSource.addEventListener("error_event", (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data);
      if (data.message && data.message.includes("Unauthorized")) {
        localStorage.removeItem("research_app_pass");
      }
      terminatePipelineError(data.message);
    } catch (err) {
      console.error(err);
    }
  });

  // Generic SSE stream closed/error listener
  eventSource.onerror = (err) => {
    console.error("SSE Connection dropped or channel parsed invalid parameters.", err);
    // Real-time server streaming can close cleanly after data completion, don't trigger error state arbitrarily if report exists
    const currentSession = sessions.find(s => s.id === activeSessionId);
    if (currentSession && currentSession.status === "running") {
      terminatePipelineError("Standard gateway timeout or stream disconnected prematurely.");
    }
  };
}

// Start visual elapsed elapsed timer
function startPipelineTimer() {
  clearInterval(timerInterval);
  timerSeconds = 0;
  els.pipelineTimer.textContent = "00:00";
  
  timerInterval = setInterval(() => {
    timerSeconds++;
    const min = Math.floor(timerSeconds / 60).toString().padStart(2, "0");
    const sec = (timerSeconds % 60).toString().padStart(2, "0");
    const display = `${min}:${sec}`;
    els.pipelineTimer.textContent = display;

    // Cache to local session parameter live state
    const cur = sessions.find(s => s.id === activeSessionId);
    if (cur) {
      cur.elapsedTime = display;
      saveSessions();
    }
  }, 1000);
}

function stopPipelineTimer() {
  clearInterval(timerInterval);
}

// Reset graph visual attributes to ground zero state
function resetNodeStates() {
  // Reset agents
  AGENT_ORDER.forEach(agent => {
    const node = document.getElementById(`node-${agent}`);
    if (node) {
      node.className = "dag-node agent-node";
    }
  });

  // Reset tools
  document.querySelectorAll(".tool-node").forEach(tool => {
    tool.classList.remove("active-flash");
  });

  // Reset root
  const rootNode = document.getElementById("node-root");
  if (rootNode) rootNode.classList.remove("active", "completed", "error");
}

// Append real-time activity log to console visual block
function appendConsoleLine(text: string, customClass: string = "") {
  const line = document.createElement("div");
  if (customClass) {
    line.className = customClass;
  } else {
    line.className = "system-log-line";
  }
  line.textContent = text;
  
  els.consoleStream.appendChild(line);
  els.consoleStream.scrollTop = els.consoleStream.scrollHeight;

  // Append history record to persistent state session JSON
  const current = sessions.find(s => s.id === activeSessionId);
  if (current) {
    current.logs.push(text);
    saveSessions();
  }
}

// Pipeline running node status changes
function updateAgentStatus(agentName: string, state: "active" | "completed") {
  const node = document.getElementById(`node-${agentName}`);
  if (!node) return;

  const currentSession = sessions.find(s => s.id === activeSessionId);

  if (state === "active") {
    // Mark previous completed agents correctly (ensure cascade complete)
    const activeIdx = AGENT_ORDER.indexOf(agentName);
    AGENT_ORDER.forEach((agent, idx) => {
      const otherNode = document.getElementById(`node-${agent}`);
      if (otherNode) {
        if (idx < activeIdx) {
          otherNode.className = "dag-node agent-node completed";
        }
      }
    });

    node.className = "dag-node agent-node active";
    els.activeAgentDisplay.textContent = agentName;
    appendConsoleLine(`Agent [${agentName}] transitions to active.`, "system-log-line text-indigo-400");
    
    if (currentSession) {
      currentSession.activeAgent = agentName;
      saveSessions();
    }
  } else if (state === "completed") {
    node.className = "dag-node agent-node completed";
    appendConsoleLine(`Agent [${agentName}] completed successfully.`, "system-log-line text-emerald-400");
  }

  // Draw edges again to paint highlighted path lines
  drawEdges();
}

// Flash visual nodes when specific tool completes tasking parameters
function invokeToolVisual(agentName: string, toolName: string) {
  // Multi-agent tool selectors mapped: searcher filter/extract and analyzer filter/extract have separate divs
  let toolSelector = `node-tool-${toolName}`;
  if (toolName === "filter_papers") {
    toolSelector = agentName === "searcher" ? "node-tool-filter_papers_s" : "node-tool-filter_papers_a";
  } else if (toolName === "extract_abstracts") {
    toolSelector = agentName === "searcher" ? "node-tool-extract_abstracts_s" : "node-tool-extract_abstracts_a";
  }

  const toolNode = document.getElementById(toolSelector);
  if (toolNode) {
    toolNode.classList.add("active-flash");
    appendConsoleLine(`[Tool Call] ${agentName} invoked ${toolName}.`, "system-log-line text-purple-400");
    
    // Smooth pulse removal
    setTimeout(() => {
      toolNode.classList.remove("active-flash");
    }, 1200);
  }

  // Inject a small sliding activity pill under the output visualizer
  const container = els.toolPillsList;
  const emptyPlaceholder = container.querySelector(".empty-shelf");
  if (emptyPlaceholder) {
    emptyPlaceholder.remove();
  }

  const pill = document.createElement("span");
  pill.className = "tool-badge-pill";
  pill.textContent = toolName;
  container.appendChild(pill);
  container.scrollLeft = container.scrollWidth;

  // Trigger transient dynamic edge flow animation
  pulseEdgeAnimation(agentName, toolSelector);
}

// Complete Pipeline success transition
function completePipelineSuccess(markdownText: string) {
  stopPipelineTimer();
  
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

  // Mark all agents completed
  AGENT_ORDER.forEach(agent => {
    const node = document.getElementById(`node-${agent}`);
    if (node) node.className = "dag-node agent-node completed";
  });

  const rootNode = document.getElementById("node-root");
  if (rootNode) rootNode.className = "dag-node root-node completed";

  appendConsoleLine("pipeline_complete: Full literature review compiled successfully.", "system-log-line text-emerald-400");
  drawEdges();

  const currentSession = sessions.find(s => s.id === activeSessionId);
  if (currentSession) {
    currentSession.status = "completed";
    currentSession.rawMarkdown = markdownText;
    saveSessions();
    renderHistory();
    
    // Display Report (switches view with burst animation)
    setTimeout(() => {
      displayMarkdownReport(currentSession);
      triggerToast("Literature research pipeline completed successfully!", "success");
    }, 1500);
  }
}

// Terminate pipeline in error state
function terminatePipelineError(errorMessage: string) {
  stopPipelineTimer();
  
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

  const currentSession = sessions.find(s => s.id === activeSessionId);
  if (currentSession) {
    currentSession.status = "error";
    saveSessions();
    renderHistory();
  }

  appendConsoleLine(`Pipeline failed: ${errorMessage}`, "system-log-line text-rose-400");
  triggerToast(`Execution failed: ${errorMessage}`, "error");

  // Highlight current active node in red error glows
  if (currentSession && currentSession.activeAgent) {
    const node = document.getElementById(`node-${currentSession.activeAgent}`);
    if (node) {
      node.className = "dag-node agent-node error";
    }
  }
  
  drawEdges();
}

// User Action Cancel Pipeline Button
function cancelActivePipeline(triggerUINotify: boolean = true) {
  if (!eventSource) return;

  eventSource.close();
  eventSource = null;
  stopPipelineTimer();

  const currentSession = sessions.find(s => s.id === activeSessionId);
  if (currentSession) {
    currentSession.status = "error";
    appendConsoleLine("Pipeline halted: Ingestion flow closed by user.", "system-log-line text-rose-400");
    saveSessions();
    renderHistory();
  }

  if (currentSession && currentSession.activeAgent) {
    const node = document.getElementById(`node-${currentSession.activeAgent}`);
    if (node) {
      node.className = "dag-node agent-node error";
    }
  }

  drawEdges();

  if (triggerUINotify) {
    triggerToast("Research pipeline halted by user.", "warn");
  }
}

// Format markdown compile and present
function displayMarkdownReport(session: ResearchSession) {
  switchToView("report");

  els.reportDateDisplay.textContent = new Date(session.createdAt).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric"
  });

  // Render using marked npm module
  const rawHtml = marked.parse(session.rawMarkdown || "# Empty Literature Review Report") as string;
  
  // Style PubMed Citations elegantly via regular expression replacing (PMID: 1234567 -> custom template wrapper)
  const stylizedCitationHtml = rawHtml.replace(/\[PMID:\s*(\d+)\]/gi, (match, pmid) => {
    return `<span class="pmid-citation" title="PubMed cross-reference registry record index: ${pmid}">PMID: ${pmid}</span>`;
  });

  els.reportBodyContainer.innerHTML = stylizedCitationHtml;
}

// Clipboard copying literature review raw markdown contents
function copyMarkdownToClipboard() {
  const currentSession = sessions.find(s => s.id === activeSessionId);
  if (!currentSession || !currentSession.rawMarkdown) {
    triggerToast("No report text available to copy.", "error");
    return;
  }

  navigator.clipboard.writeText(currentSession.rawMarkdown).then(() => {
    els.btnCopyText.textContent = "Copied!";
    triggerToast("Markdown report copied to clipboard.", "success");
    
    // Smooth reset label
    setTimeout(() => {
      els.btnCopyText.textContent = "Copy Markdown";
    }, 2000);
  }).catch(err => {
    console.error("Clipboard write blocked", err);
    triggerToast("Failed to write clipboard contents.", "error");
  });
}

// Visual DAG edge connector calculations
let edgeDrawTimeout: any = null;
function drawEdges() {
  if (!els.svgCanvas || els.viewPipeline.className.indexOf("active") === -1) {
    return;
  }

  // Clear outline
  els.svgCanvas.innerHTML = "";

  const container = els.dagGraphView;
  const containerRect = container.getBoundingClientRect();

  const svgW = containerRect.width;
  const svgH = containerRect.height;
  els.svgCanvas.setAttribute("width", svgW.toString());
  els.svgCanvas.setAttribute("height", svgH.toString());

  // Define marker arrows definition in SVG
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  defs.innerHTML = `
    <marker id="arrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="rgba(255,255,255,0.15)" />
    </marker>
    <marker id="arrow-active" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#818cf8" />
    </marker>
    <marker id="arrow-completed" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 1 L 10 5 L 0 9 z" fill="#34d399" />
    </marker>
  `;
  els.svgCanvas.appendChild(defs);

  // Connection Builder helper
  const createEdge = (parentEl: HTMLElement, childEl: HTMLElement, type: "tree" | "flow", isActive: boolean = false, isCompleted: boolean = false) => {
    const parentRect = parentEl.getBoundingClientRect();
    const childRect = childEl.getBoundingClientRect();

    let x1 = 0, y1 = 0, x2 = 0, y2 = 0;

    if (type === "tree") {
      // Top down connections (Parent center bottom to Child center top)
      x1 = (parentRect.left + parentRect.width / 2) - containerRect.left;
      y1 = parentRect.bottom - containerRect.top;
      x2 = (childRect.left + childRect.width / 2) - containerRect.left;
      y2 = childRect.top - containerRect.top;
    } else {
      // Left-to-right sequential steps connections (Left agent node right-center to Right agent node left-center)
      x1 = parentRect.right - containerRect.left;
      y1 = (parentRect.top + parentRect.height / 2) - containerRect.top;
      x2 = childRect.left - containerRect.left;
      y2 = (childRect.top + childRect.height / 2) - containerRect.top;
    }

    // Bezier control parameters
    let pathAttr = "";
    if (type === "tree") {
      const midY = y1 + (y2 - y1) * 0.45;
      pathAttr = `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`;
    } else {
      const midX = x1 + (x2 - x1) * 0.5;
      pathAttr = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
    }

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", pathAttr);
    
    // State-based Styling mapping
    let strokeColor = "rgba(255, 255, 255, 0.08)";
    let markerId = "arrow";
    let isDashed = type === "flow";

    if (isCompleted) {
      strokeColor = "#34d399";
      markerId = "arrow-completed";
      isDashed = false;
    } else if (isActive) {
      strokeColor = "#818cf8";
      markerId = "arrow-active";
    }

    path.setAttribute("stroke", strokeColor);
    path.setAttribute("stroke-width", isActive ? "2" : "1.3");
    path.setAttribute("fill", "none");
    path.setAttribute("marker-end", `url(#${markerId})`);
    
    if (isDashed) {
      path.setAttribute("stroke-dasharray", "4,4");
    }

    els.svgCanvas.appendChild(path);

    // Dynamic crawling overlay traveling dot path if connection is active
    if (isActive) {
      const animatedPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
      animatedPath.setAttribute("d", pathAttr);
      animatedPath.setAttribute("stroke", "#a78bfa");
      animatedPath.setAttribute("stroke-width", "2.5");
      animatedPath.setAttribute("fill", "none");
      animatedPath.className.baseVal = "dag-edge-animated";
      els.svgCanvas.appendChild(animatedPath);
    }
  };

  const currentSession = sessions.find(s => s.id === activeSessionId);
  const activeAgent = currentSession?.activeAgent || null;
  const activeIdx = activeAgent ? AGENT_ORDER.indexOf(activeAgent) : -1;

  // 1. Root center connections down to all 7 agent nodes (Tree hierarchy)
  const rootNode = document.getElementById("node-root");
  if (rootNode) {
    AGENT_ORDER.forEach((agent, idx) => {
      const agentNode = document.getElementById(`node-${agent}`);
      if (agentNode) {
        const isCompleted = idx < activeIdx || currentSession?.status === "completed";
        const isActive = idx === activeIdx && currentSession?.status === "running";
        createEdge(rootNode, agentNode, "tree", isActive, isCompleted);
      }
    });
  }

  // 2. Horizontal step connections between successive agents (clarifier -> planner -> ...)
  for (let i = 0; i < AGENT_ORDER.length - 1; i++) {
    const agentA = document.getElementById(`node-${AGENT_ORDER[i]}`);
    const agentB = document.getElementById(`node-${AGENT_ORDER[i+1]}`);
    if (agentA && agentB) {
      const isCompleted = (i + 1) < activeIdx || currentSession?.status === "completed";
      const isActive = i === activeIdx && currentSession?.status === "running"; // show flow exiting active
      createEdge(agentA, agentB, "flow", isActive, isCompleted);
    }
  }

  // 3. Searcher tools mapping (Level 3 tree links under Column 3)
  const searcherNode = document.getElementById("node-searcher");
  if (searcherNode) {
    const searcherTools = [
      "node-tool-search_arxiv",
      "node-tool-search_pubmed",
      "node-tool-search_openalex",
      "node-tool-filter_papers_s",
      "node-tool-rank_papers",
      "node-tool-extract_abstracts_s",
      "node-tool-traverse_citations"
    ];

    searcherTools.forEach(toolId => {
      const toolEl = document.getElementById(toolId);
      if (toolEl) {
        const isSearchCompleted = activeIdx > AGENT_ORDER.indexOf("searcher") || currentSession?.status === "completed";
        const isSearchActive = activeAgent === "searcher" && currentSession?.status === "running";
        createEdge(searcherNode, toolEl, "tree", isSearchActive, isSearchCompleted);
      }
    });
  }

  // 4. Analyzer tools mapping (Level 3 tree links under Column 4)
  const analyzerNode = document.getElementById("node-analyzer");
  if (analyzerNode) {
    const analyzerTools = [
      "node-tool-filter_papers_a",
      "node-tool-extract_abstracts_a"
    ];

    analyzerTools.forEach(toolId => {
      const toolEl = document.getElementById(toolId);
      if (toolEl) {
        const isAnalyzerCompleted = activeIdx > AGENT_ORDER.indexOf("analyzer") || currentSession?.status === "completed";
        const isAnalyzerActive = activeAgent === "analyzer" && currentSession?.status === "running";
        createEdge(analyzerNode, toolEl, "tree", isAnalyzerActive, isAnalyzerCompleted);
      }
    });
  }
}

// Spark transient dot traveling along edge when tool fires
function pulseEdgeAnimation(agentName: string, toolNodeId: string) {
  const agentEl = document.getElementById(`node-${agentName}`);
  const toolEl = document.getElementById(toolNodeId);
  const container = els.dagGraphView;

  if (!agentEl || !toolEl || !els.svgCanvas) return;

  const containerRect = container.getBoundingClientRect();
  const parentRect = agentEl.getBoundingClientRect();
  const childRect = toolEl.getBoundingClientRect();

  const x1 = (parentRect.left + parentRect.width / 2) - containerRect.left;
  const y1 = parentRect.bottom - containerRect.top;
  const x2 = (childRect.left + childRect.width / 2) - containerRect.left;
  const y2 = childRect.top - containerRect.top;

  const midY = y1 + (y2 - y1) * 0.45;
  const pathAttr = `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`;

  // Spawn an overlay particle traveling along this spec
  const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  dot.setAttribute("r", "5");
  dot.setAttribute("fill", "#c084fc");
  
  const animateMotion = document.createElementNS("http://www.w3.org/2000/svg", "animateMotion");
  animateMotion.setAttribute("path", pathAttr);
  animateMotion.setAttribute("dur", "0.8s");
  animateMotion.setAttribute("repeatCount", "1");
  animateMotion.setAttribute("fill", "freeze");

  dot.appendChild(animateMotion);
  els.svgCanvas.appendChild(dot);

  // Discard dot after arrival
  setTimeout(() => {
    dot.remove();
  }, 900);
}

// Utility text escape
function escapeHTML(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

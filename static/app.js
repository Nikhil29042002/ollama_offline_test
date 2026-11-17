const log = document.getElementById("log");
const box = document.getElementById("box");
const form = document.getElementById("form");
const send = document.getElementById("send");
const error = document.getElementById("error");
const status = document.getElementById("status");
const history = [];

function addMessage(role, text) {
  const el = document.createElement("div");
  el.className = "msg " + (role === "user" ? "user" : "model");
  el.textContent = text;
  log.append(el);
  log.scrollTop = log.scrollHeight;
  return el;
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status");
    const data = await response.json();
    if (data.ready) {
      status.textContent = "llama3.2:3b ready";
      status.classList.remove("down");
    } else {
      status.textContent = "llama3.2:3b not running";
      status.classList.add("down");
    }
  } catch (err) {
    status.textContent = "chat server not running";
    status.classList.add("down");
  }
}

refreshStatus();
setInterval(refreshStatus, 8000);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = box.value.trim();
  if (!text) return;
  error.textContent = "";
  box.value = "";
  addMessage("user", text);
  history.push({ role: "user", content: text });
  const body = addMessage("model", "Thinking...");
  send.disabled = true;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history }),
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || ("Request failed (" + response.status + ")"));
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    let answer = "";
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      pending += decoder.decode(chunk.value, { stream: true });
      const lines = pending.split(/\r?\n/);
      pending = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const data = JSON.parse(line);
        if (data.error) throw new Error(data.error);
        const token = (data.message && data.message.content) || "";
        if (token) {
          answer += token;
          body.textContent = answer;
          log.scrollTop = log.scrollHeight;
        }
      }
    }
    if (!answer) body.textContent = "(No reply from the model.)";
    history.push({ role: "assistant", content: answer });
  } catch (err) {
    body.remove();
    const message = err.message || String(err);
    error.textContent = message === "Failed to fetch"
      ? "The chat server stopped. Run python chat_server.py, then refresh this page."
      : message;
    history.pop();
  } finally {
    send.disabled = false;
    box.focus();
  }
});

box.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

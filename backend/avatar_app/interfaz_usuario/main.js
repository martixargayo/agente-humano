const form = document.getElementById("chat-form");
const input = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const messages = document.getElementById("messages");

function renderMessages(items) {
  messages.innerHTML = "";
  for (const item of items) {
    const row = document.createElement("div");
    row.className = `message ${item.role}`;
    row.textContent = item.text ?? "";
    messages.appendChild(row);
  }
  messages.scrollTop = messages.scrollHeight;
}

async function loadCanonicalHistory() {
  const response = await fetch("/api/avatar/interfaz-usuario/history");
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `HTTP ${response.status}`);
  }
  const data = await response.json();
  renderMessages(Array.isArray(data.items) ? data.items : []);
}

async function sendMessage(message) {
  const response = await fetch("/api/avatar/interfaz-usuario/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(errorText || `HTTP ${response.status}`);
  }

  return response.json();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;

  input.value = "";
  sendBtn.disabled = true;

  try {
    await sendMessage(message);
    await loadCanonicalHistory();
  } catch (error) {
    const row = document.createElement("div");
    row.className = "message assistant";
    row.textContent = `Error: ${error.message}`;
    messages.appendChild(row);
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
});

loadCanonicalHistory().catch((error) => {
  const row = document.createElement("div");
  row.className = "message assistant";
  row.textContent = `Error: ${error.message}`;
  messages.appendChild(row);
});

setInterval(() => {
  loadCanonicalHistory().catch(() => {});
}, 2000);

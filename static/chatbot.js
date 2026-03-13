const chatHistory = [];

function appendMessage(kind, text) {
    const chatbox = document.getElementById("chatbox");
    const wrapper = document.createElement("div");
    wrapper.className = kind === "user" ? "user-msg" : "bot-msg";

    const bubble = document.createElement("span");
    bubble.textContent = text;

    wrapper.appendChild(bubble);
    chatbox.appendChild(wrapper);
    chatbox.scrollTop = chatbox.scrollHeight;
}

function setInputDisabled(disabled) {
    const input = document.getElementById("msg");
    const button = document.querySelector(".chat-input button");
    input.disabled = disabled;
    button.disabled = disabled;
}

function send() {
    const input = document.getElementById("msg");
    const msg = (input.value || "").trim();

    if (!msg) return;

    appendMessage("user", msg);

    const context = chatHistory.slice(-12);
    chatHistory.push({ role: "user", content: msg });

    input.value = "";
    setInputDisabled(true);

    // Simple typing indicator
    appendMessage("bot", "Typing...");
    const typingIndex = document.getElementById("chatbox").children.length - 1;

    fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, history: context })
    })
        .then(res => res.json())
        .then(data => {
            const chatbox = document.getElementById("chatbox");
            const typingEl = chatbox.children[typingIndex];
            if (typingEl) typingEl.remove();

            const reply = (data && data.reply) ? String(data.reply) : "Sorry, I didn't catch that.";
            appendMessage("bot", reply);
            chatHistory.push({ role: "assistant", content: reply });
        })
        .catch(() => {
            const chatbox = document.getElementById("chatbox");
            const typingEl = chatbox.children[typingIndex];
            if (typingEl) typingEl.remove();
            appendMessage("bot", "Sorry, something went wrong. Please try again.");
        })
        .finally(() => {
            setInputDisabled(false);
            input.focus();
        });
}

document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("msg");
    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            send();
        }
    });

    appendMessage("bot", "Hi, I'm MindGuard. How are you feeling today?");
    input.focus();
});

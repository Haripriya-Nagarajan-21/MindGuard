(() => {
    const fab = document.getElementById("mgChatFab");
    const panel = document.getElementById("mgChatPanel");
    const closeBtn = document.getElementById("mgChatClose");
    const messages = document.getElementById("mgChatMessages");
    const form = document.getElementById("mgChatForm");
    const input = document.getElementById("mgChatText");
    const chips = document.getElementById("mgChatChips");
    const badge = document.getElementById("mgChatBadge");

    if (!fab || !panel || !closeBtn || !messages || !form || !input) {
        return;
    }

    const history = [];
    let hasUnread = false;

    function setBadgeVisible(visible) {
        if (!badge) return;
        badge.style.opacity = visible ? "1" : "0";
        badge.style.transform = visible ? "scale(1)" : "scale(0.7)";
    }

    function setOpen(open) {
        panel.classList.toggle("is-open", open);
        fab.setAttribute("aria-expanded", open ? "true" : "false");
        panel.setAttribute("aria-hidden", open ? "false" : "true");

        if (open) {
            hasUnread = false;
            setBadgeVisible(false);
            setTimeout(() => input.focus(), 0);
        }
    }

    function append(kind, text) {
        const row = document.createElement("div");
        row.className = kind === "user" ? "mg-msg mg-msg-user" : "mg-msg mg-msg-bot";

        const bubble = document.createElement("div");
        bubble.className = "mg-bubble";
        bubble.textContent = text;

        row.appendChild(bubble);
        messages.appendChild(row);
        messages.scrollTop = messages.scrollHeight;
    }

    function typingOn() {
        const row = document.createElement("div");
        row.className = "mg-msg mg-msg-bot mg-typing";
        row.setAttribute("data-typing", "1");

        const bubble = document.createElement("div");
        bubble.className = "mg-bubble";
        bubble.textContent = "Typing...";

        row.appendChild(bubble);
        messages.appendChild(row);
        messages.scrollTop = messages.scrollHeight;
    }

    function typingOff() {
        const el = messages.querySelector("[data-typing='1']");
        if (el) el.remove();
    }

    function setDisabled(disabled) {
        input.disabled = disabled;
        const send = panel.querySelector(".mg-chat-send");
        if (send) send.disabled = disabled;
    }

    function buildContextText() {
        const ctx = window.MG_CHAT_CONTEXT;
        if (!ctx || typeof ctx !== "object") return "";

        const parts = [];
        if (ctx.page) parts.push(`page=${ctx.page}`);
        if (ctx.prediction) parts.push(`prediction=${ctx.prediction}`);
        if (typeof ctx.wellness_score === "number") parts.push(`wellness_score=${ctx.wellness_score}/100`);
        if (Array.isArray(ctx.driver_labels) && ctx.driver_labels.length) {
            parts.push(`top_drivers=${ctx.driver_labels.slice(0, 3).join(", ")}`);
        }

        return parts.length ? `Context: ${parts.join(" | ")}` : "";
    }

    async function sendMessage(text) {
        const msg = String(text || "").trim();
        if (!msg) return;

        append("user", msg);
        history.push({ role: "user", content: msg });

        const contextText = buildContextText();
        const contextHistory = history.slice(-12);
        if (contextText) {
            contextHistory.unshift({ role: "assistant", content: contextText });
        }

        setDisabled(true);
        typingOn();

        try {
            const res = await fetch("/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: msg, history: contextHistory }),
            });
            const data = await res.json();
            const reply = data && data.reply ? String(data.reply) : "Sorry, I didn't catch that.";
            typingOff();
            append("bot", reply);
            history.push({ role: "assistant", content: reply });

            if (!panel.classList.contains("is-open")) {
                hasUnread = true;
                setBadgeVisible(true);
            }
        } catch {
            typingOff();
            append("bot", "Sorry, something went wrong. Please try again.");
        } finally {
            setDisabled(false);
            input.focus();
        }
    }

    fab.addEventListener("click", () => setOpen(!panel.classList.contains("is-open")));
    closeBtn.addEventListener("click", () => setOpen(false));
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") setOpen(false);
    });

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const msg = input.value;
        input.value = "";
        sendMessage(msg);
    });

    if (chips) {
        chips.addEventListener("click", (event) => {
            const target = event.target;
            if (!(target instanceof HTMLElement)) return;
            if (!target.classList.contains("mg-chip")) return;

            const prompt = target.getAttribute("data-chip") || target.textContent || "";
            setOpen(true);
            sendMessage(prompt);
        });
    }

    setBadgeVisible(false);

    // First message
    append("bot", "Hi, I'm MindGuard. What would you like help with today?");
})();


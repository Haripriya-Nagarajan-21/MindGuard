function send() {
    let msg = document.getElementById("msg").value;

    if (msg.trim() === "") return;

    let chatbox = document.getElementById("chatbox");

    // User message
    chatbox.innerHTML += `
        <div class="user-msg">
            <span>${msg}</span>
        </div>
    `;

    fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg })
    })
    .then(res => res.json())
    .then(data => {
        chatbox.innerHTML += `
            <div class="bot-msg">
                <span>${data.reply}</span>
            </div>
        `;
        chatbox.scrollTop = chatbox.scrollHeight;
    });

    document.getElementById("msg").value = "";
}
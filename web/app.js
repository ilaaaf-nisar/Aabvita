(() => {
  const conversation = document.getElementById("conversation");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("message");
  const sendButton = document.getElementById("send-button");
  const newChatButton = document.getElementById("new-chat");
  const settingsDialog = document.getElementById("settings-dialog");
  const settingsButton = document.getElementById("open-settings");
  const toast = document.getElementById("toast");
  const welcomeMarkup = conversation.innerHTML;
  const settingsKeys = [
    "persist_profile",
    "share_profile_context",
    "share_medical_context",
  ];
  const settingInputs = [...document.querySelectorAll("[data-setting]")];
  const preferencePrefix = "my-coach-preference-";
  const sessionStorageKey = "my-coach-session-id";
  let messageList = null;
  let toastTimer = null;
  let busy = false;

  function getSessionId() {
    try {
      const saved = localStorage.getItem(sessionStorageKey);
      if (saved && /^[0-9a-f-]{36}$/i.test(saved)) return saved;
      const created = crypto.randomUUID();
      localStorage.setItem(sessionStorageKey, created);
      return created;
    } catch {
      return crypto.randomUUID();
    }
  }

  const sessionId = getSessionId();

  function readPreferences() {
    return Object.fromEntries(settingsKeys.map((key) => {
      try {
        return [key, localStorage.getItem(preferencePrefix + key) === "true"];
      } catch {
        return [key, false];
      }
    }));
  }

  function currentPreferences() {
    return Object.fromEntries(settingsKeys.map((key) => [
      key,
      settingInputs.find((element) => element.dataset.setting === key)?.checked ?? false,
    ]));
  }

  function setPreferences(preferences) {
    settingInputs.forEach((element) => {
      element.checked = Boolean(preferences[element.dataset.setting]);
    });
  }

  async function postJson(path, payload) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || "The request could not be completed.");
    }
    return data;
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("visible"), 3200);
  }

  function ensureMessageList() {
    if (!messageList) {
      conversation.replaceChildren();
      messageList = document.createElement("div");
      messageList.className = "message-list";
      conversation.append(messageList);
    }
    return messageList;
  }

  function addMessage(role, text, metadata = {}) {
    const list = ensureMessageList();
    const row = document.createElement("article");
    row.className = `message ${role}`;

    if (role === "assistant") {
      const avatar = document.createElement("span");
      avatar.className = "message-avatar";
      avatar.setAttribute("aria-hidden", "true");
      avatar.innerHTML = '<svg viewBox="0 0 32 32" fill="none"><path d="M16 4c-1.2 5.6-3.9 8.3-9.5 9.5 5.6 1.2 8.3 3.9 9.5 9.5 1.2-5.6 3.9-8.3 9.5-9.5C19.9 12.3 17.2 9.6 16 4Z" fill="currentColor"/></svg>';
      row.append(avatar);
    }

    const content = document.createElement("div");
    content.className = "message-content";
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.textContent = text;
    content.append(bubble);

    row.append(content);
    list.append(row);
    conversation.scrollTop = conversation.scrollHeight;
  }

  function addTypingIndicator() {
    const list = ensureMessageList();
    const row = document.createElement("article");
    row.className = "message assistant";
    row.id = "typing-indicator";
    const avatar = document.createElement("span");
    avatar.className = "message-avatar";
    avatar.setAttribute("aria-hidden", "true");
    avatar.textContent = "✳";
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.setAttribute("aria-label", "Aabvita is thinking");
    bubble.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
    row.append(avatar, bubble);
    list.append(row);
    conversation.scrollTop = conversation.scrollHeight;
  }

  function removeTypingIndicator() {
    document.getElementById("typing-indicator")?.remove();
  }

  async function sendMessage(text) {
    const message = text.trim();
    if (!message || busy) return;

    busy = true;
    sendButton.disabled = true;
    input.disabled = true;
    addMessage("user", message);
    input.value = "";
    input.style.height = "auto";
    addTypingIndicator();

    try {
      const data = await postJson("/api/chat", {
        session_id: sessionId,
        message,
        ...currentPreferences(),
      });
      removeTypingIndicator();
      addMessage("assistant", data.answer);
    } catch (error) {
      removeTypingIndicator();
      addMessage(
        "assistant",
        `I couldn't complete that just now. ${error.message} Please try again.`,
      );
    } finally {
      busy = false;
      sendButton.disabled = false;
      input.disabled = false;
      input.focus();
    }
  }

  async function savePreferences() {
    const preferences = currentPreferences();
    try {
      settingsKeys.forEach((key) => {
        localStorage.setItem(preferencePrefix + key, String(preferences[key]));
      });
    } catch {
      showToast("Your browser couldn't save these preference choices.");
    }

    try {
      await postJson("/api/privacy", {
        session_id: sessionId,
        ...preferences,
      });
      showToast(preferences.persist_profile
        ? "Your profile can now be remembered on this device."
        : "Your saved profile was removed from this device.");
    } catch (error) {
      showToast(`Privacy setting wasn't updated: ${error.message}`);
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void sendMessage(input.value);
  });

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  document.querySelectorAll(".suggestion").forEach((button) => {
    button.addEventListener("click", () => {
      void sendMessage(button.dataset.prompt || "");
    });
  });

  settingInputs.forEach((element) => {
    element.addEventListener("change", () => {
      const key = element.dataset.setting;
      settingInputs.forEach((peer) => {
        if (peer.dataset.setting === key) peer.checked = element.checked;
      });
      void savePreferences();
    });
  });

  settingsButton.addEventListener("click", () => settingsDialog.showModal());

  newChatButton.addEventListener("click", async () => {
    if (busy) return;
    try {
      await postJson("/api/reset", { session_id: sessionId });
      messageList = null;
      conversation.innerHTML = welcomeMarkup;
      document.querySelectorAll(".suggestion").forEach((button) => {
        button.addEventListener("click", () => {
          void sendMessage(button.dataset.prompt || "");
        });
      });
      showToast("Conversation and saved profile cleared.");
    } catch (error) {
      showToast(`Couldn't clear this conversation: ${error.message}`);
    }
  });

  setPreferences(readPreferences());
  void postJson("/api/privacy", {
    session_id: sessionId,
    ...currentPreferences(),
  }).catch((error) => showToast(`Couldn't apply privacy settings: ${error.message}`));
})();

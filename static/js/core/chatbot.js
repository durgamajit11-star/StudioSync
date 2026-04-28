// ===============================
// SHARED CHATBOT WIDGET
// ===============================

function initializeChatbotWidget() {
    const container = document.getElementById('chatbot-container');
    const chatWindow = document.getElementById('chatWindow');
    const chatToggle = document.getElementById('chatToggle');
    const chatCloseBtn = document.getElementById('chatCloseBtn');
    const chatClearBtn = document.getElementById('chatClearBtn');
    const chatInput = document.getElementById('chatInput');
    const chatBody = document.getElementById('chatBody');
    const chatSendBtn = document.getElementById('chatSendBtn');

    if (!container || !chatWindow || !chatBody || !chatInput || !chatSendBtn) {
        return;
    }

    if (container.dataset.chatbotInitialized === '1') {
        return;
    }
    container.dataset.chatbotInitialized = '1';

    const role = (container.dataset.chatbotRole || document.body?.dataset?.role || 'USER').toUpperCase();
    const messagesUrlByRole = {
        USER: container.dataset.chatbotUserUrl || '/chatbot/messages/user/',
        STUDIO: container.dataset.chatbotStudioUrl || '/chatbot/messages/studio/',
        ADMIN: container.dataset.chatbotAdminUrl || '/chatbot/messages/admin/'
    };
    const messagesUrl = messagesUrlByRole[role] || container.dataset.chatbotUrl || '/chatbot/messages/';
    const clearUrl = container.dataset.chatbotClearUrl || '/chatbot/clear/';
    let historyLoaded = false;
    let sending = false;

    const roleSuggestions = {
        USER: [
            'What can I do on this platform?',
            'How do bookings work?',
            'How do payments and refunds work?'
        ],
        STUDIO: [
            'How do I manage my portfolio and studio profile?',
            'How do I handle booking approvals and schedule updates?',
            'How can I track earnings and client reviews?'
        ],
        ADMIN: [
            'How do I verify and moderate studio accounts?',
            'How can I monitor bookings and payment flow?',
            'What are key admin dashboard actions today?'
        ]
    };

    function getCsrfToken() {
        const cookie = document.cookie.split('; ').find((row) => row.startsWith('csrftoken='));
        return cookie ? decodeURIComponent(cookie.split('=')[1]) : '';
    }

    function toggleChat() {
        chatWindow.classList.toggle('active');
        if (window.innerWidth <= 576 && chatWindow.classList.contains('active')) {
            chatWindow.style.bottom = 'auto';
            // ensure the chat window fits within the viewport on small screens
            const safeTop = 12; // px from top
            const safeBottom = 12; // px from bottom
            const available = Math.max(window.innerHeight - safeTop - safeBottom, 200);
            chatWindow.style.top = safeTop + 'px';
            chatWindow.style.maxHeight = available + 'px';
            // limit chat body so header + input remain visible
            const headerHeight = chatWindow.querySelector('.chat-header')?.offsetHeight || 64;
            const inputHeight = chatWindow.querySelector('.chat-input')?.offsetHeight || 66;
            const bodyMax = Math.max(available - headerHeight - inputHeight - 32, 120);
            chatBody.style.maxHeight = bodyMax + 'px';
        } else {
            chatWindow.style.bottom = '100px';
            chatWindow.style.top = 'auto';
            chatWindow.style.maxHeight = '';
            chatBody.style.maxHeight = '';
        }

        if (chatWindow.classList.contains('active') && !historyLoaded) {
            loadHistory();
        }
    }

    function scrollToBottom() {
        chatBody.scrollTop = chatBody.scrollHeight;
    }

    function createMessageElement(className, text) {
        const message = document.createElement('div');
        message.className = className;
        message.textContent = text;
        return message;
    }

    function appendMessage(className, text) {
        const message = createMessageElement(className, text);
        chatBody.appendChild(message);
        scrollToBottom();
    }

    function showTyping() {
        removeTyping();
        const typing = document.createElement('div');
        typing.className = 'bot-message typing';
        typing.id = 'typingIndicator';
        typing.innerHTML = 'Typing<span>.</span><span>.</span><span>.</span>';
        chatBody.appendChild(typing);
        scrollToBottom();
    }

    function removeTyping() {
        const typing = document.getElementById('typingIndicator');
        if (typing) {
            typing.remove();
        }
    }

    function setDisabled(disabled) {
        chatInput.disabled = disabled;
        chatSendBtn.disabled = disabled;
        if (chatClearBtn) {
            chatClearBtn.disabled = disabled;
        }
    }

    function addSuggestionButtons(prompts) {
        const suggestions = document.createElement('div');
        suggestions.className = 'chat-suggestions mt-2 d-flex flex-wrap gap-2';
        prompts.forEach((prompt) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'btn btn-sm btn-outline-secondary chat-suggestion';
            button.dataset.prompt = prompt;
            button.textContent = prompt;
            suggestions.appendChild(button);
        });
        chatBody.appendChild(suggestions);
    }

    function renderStarterQuestions() {
        chatBody.appendChild(createMessageElement('bot-message', 'Hello! Ask me anything about StudioSync.'));
        addSuggestionButtons(roleSuggestions[role] || roleSuggestions.USER);
    }

    function renderHistory(messages) {
        chatBody.innerHTML = '';
        renderStarterQuestions();
        if (!messages.length) {
            scrollToBottom();
            return;
        }

        // Deduplicate messages by (text + timestamp + is_user)
        const seen = new Set();
        const uniqueMessages = messages.filter((entry) => {
            const key = `${entry.message}|${entry.timestamp}|${entry.is_user}`;
            if (seen.has(key)) {
                return false; // Skip duplicate
            }
            seen.add(key);
            return true;
        });

        uniqueMessages.forEach((entry) => {
            const className = entry.is_user ? 'user-message' : 'bot-message';
            appendMessage(className, entry.message || '');
        });
    }

    async function loadHistory() {
        try {
            const response = await fetch(messagesUrl, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin'
            });
            if (!response.ok) return;
            const data = await response.json();
            renderHistory(Array.isArray(data.messages) ? data.messages : []);
            historyLoaded = true;
        } catch (error) {
            console.error('Unable to load chatbot history', error);
        }
    }

    async function sendMessage(messageOverride) {
        const message = (messageOverride || chatInput.value || '').trim();
        if (!message || sending) return;

        sending = true;
        setDisabled(true);
        chatInput.value = '';
        appendMessage('user-message', message);
        showTyping();

        try {
            const response = await fetch(messagesUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'same-origin',
                body: JSON.stringify({ message })
            });

            const data = await response.json();
            removeTyping();

            if (!response.ok) {
                appendMessage('bot-message', data.error || 'Sorry, I could not answer that right now.');
                return;
            }

            appendMessage('bot-message', data.bot_response || 'I am here to help with StudioSync.');
            if (data.policy_notice) {
                appendMessage('bot-policy-message', data.policy_notice);
            }
            historyLoaded = true;
        } catch (error) {
            removeTyping();
            appendMessage('bot-message', 'Connection problem. Please try again.');
            console.error('Chatbot send failed', error);
        } finally {
            sending = false;
            setDisabled(false);
            chatInput.focus();
        }
    }

    async function clearHistory() {
        if (!confirm('Clear chat history?')) return;

        try {
            const response = await fetch(clearUrl, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'same-origin'
            });

            if (response.ok) {
                historyLoaded = false;
                renderHistory([]);
            }
        } catch (error) {
            console.error('Unable to clear chat history', error);
        }
    }

    chatToggle?.addEventListener('click', toggleChat);
    chatCloseBtn?.addEventListener('click', toggleChat);
    chatSendBtn.addEventListener('click', () => sendMessage());
    chatInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            sendMessage();
        }
    });

    chatBody.addEventListener('click', (event) => {
        const suggestion = event.target.closest('.chat-suggestion');
        if (!suggestion) return;
        sendMessage(suggestion.dataset.prompt || suggestion.textContent || '');
    });

    chatClearBtn?.addEventListener('click', clearHistory);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeChatbotWidget, { once: true });
} else {
    initializeChatbotWidget();
}

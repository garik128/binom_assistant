// Отображение списка чатов с пагинацией
function renderChatsList() {
    const chatsList = document.getElementById('chatsList');
    const showMoreBtn = document.getElementById('showMoreChatsBtn');
    if (!chatsList) return;

    chatsList.innerHTML = '';

    // Используем filteredChats если есть (поиск), иначе все чаты
    const chatsToDisplay = chatState.filteredChats.length > 0 ? chatState.filteredChats : chatState.chats;
    const displayChats = chatsToDisplay.slice(0, chatState.displayedCount);

    if (displayChats.length === 0) {
        chatsList.innerHTML = '<div class="no-chats">Нет чатов</div>';
        if (showMoreBtn) showMoreBtn.style.display = 'none';
        return;
    }

    displayChats.forEach(chat => {
        const chatItem = document.createElement('div');
        chatItem.className = `chat-item${chat.id === chatState.currentChatId ? ' active' : ''}`;
        chatItem.dataset.chatId = chat.id;

        chatItem.innerHTML = `
            <div class="chat-item-content" onclick="switchToChat(${chat.id})">
                <div class="chat-item-title" ondblclick="editChatTitle(${chat.id}, event)">${escapeHtml(chat.title)}</div>
                <div class="chat-item-meta">${formatChatDate(chat.updated_at)} | ${chat.message_count} сообщ.</div>
            </div>
            <button class="chat-item-delete" onclick="deleteChat(${chat.id}, event)" title="Удалить чат">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                </svg>
            </button>
        `;

        chatsList.appendChild(chatItem);
    });

    // Показываем/скрываем кнопку "Показать еще"
    if (showMoreBtn) {
        if (chatsToDisplay.length > chatState.displayedCount) {
            showMoreBtn.style.display = 'flex';
        } else {
            showMoreBtn.style.display = 'none';
        }
    }
}

// Показать еще чатов
function showMoreChats() {
    chatState.displayedCount += chatState.chatsPerPage;
    renderChatsList();
}

// Поиск по чатам
function searchChats(query) {
    const lowerQuery = query.toLowerCase().trim();

    if (!lowerQuery) {
        // Если поиск пустой - показываем все чаты
        chatState.filteredChats = [];
        chatState.displayedCount = chatState.chatsPerPage;
        renderChatsList();
        return;
    }

    // Фильтруем чаты по title
    chatState.filteredChats = chatState.chats.filter(chat =>
        chat.title.toLowerCase().includes(lowerQuery)
    );

    // Сбрасываем счетчик отображаемых
    chatState.displayedCount = chatState.chatsPerPage;
    renderChatsList();
}

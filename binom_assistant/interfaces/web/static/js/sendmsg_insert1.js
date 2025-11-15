
    // Создаем чат, если его еще нет
    if (!chatState.currentChatId) {
        await createNewChat();
    }

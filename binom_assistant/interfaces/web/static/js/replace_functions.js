// Новая версия startNewChat - вызывает createNewChat из БД
async function startNewChat() {
    await createNewChat();
}

// Новая версия switchChat - вызывает switchToChat из БД
async function switchChat(chatId) {
    await switchToChat(chatId);
}

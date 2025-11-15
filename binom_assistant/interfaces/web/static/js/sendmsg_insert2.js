
        // Сохраняем сообщения в БД
        if (chatState.currentChatId) {
            await saveMessagesToDB([
                {role: 'user', content: message},
                {role: 'assistant', content: data.response}
            ]);
        }

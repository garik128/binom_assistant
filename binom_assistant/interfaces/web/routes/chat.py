"""
API роуты для чата с AI.
"""
from fastapi import APIRouter, HTTPException, Depends
import logging
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatMessage,
    ModelsListResponse,
    ModelInfo,
    TokenUsage,
    TemplateCreate,
    TemplateUpdate,
    TemplateResponse,
    TemplateListResponse
)
from services.ai_service import get_ai_service
from services.ai_agent import get_agent_service
from services.ai_agent.category_prompts import get_available_categories
from services.ai_agent.prompt_manager import get_prompt_manager
from storage.database.base import get_session_factory
from storage.database.models import ChatSession, ChatMessage as DBChatMessage, ChatTemplate

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(get_current_user)])

# Dependency для получения сессии БД
def get_db():
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@router.post("/chat/send", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """
    Отправка сообщения в чат и получение ответа от AI.

    Args:
        request: Запрос с сообщением и параметрами

    Returns:
        Ответ от AI с информацией о токенах
    """
    try:
        # Если use_modules=True - используем агента с модулями
        if request.use_modules:
            agent_service = get_agent_service()

            # Ограничиваем историю контекста
            context_limit = request.context_limit or 10
            limited_history = request.chat_history[-context_limit:] if request.chat_history else []

            # Формируем историю в формате OpenAI API
            chat_history = []
            for msg in limited_history:
                chat_history.append({
                    "role": msg.role,
                    "content": msg.content
                })

            logger.info(
                f"Agent analysis request: category={request.modules_category}, "
                f"model={request.model or 'default'}, "
                f"message={request.message[:100]}, history_size={len(chat_history)}"
            )

            # Запускаем анализ через агента
            result = await agent_service.analyze(
                user_query=request.message,
                category=request.modules_category,
                chat_history=chat_history,
                model=request.model
            )

            # Возвращаем в формате ChatResponse (без токенов, т.к. агент сам управляет вызовами)
            return ChatResponse(
                response=result,
                model=request.model or "agent-mode",
                usage=TokenUsage(
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0
                )
            )

        # Обычный чат без модулей
        ai_service = get_ai_service()

        # Ограничиваем историю контекста
        context_limit = request.context_limit or 10
        limited_history = request.chat_history[-context_limit:] if request.chat_history else []

        # Формируем список сообщений для API
        messages = []

        # Добавляем историю
        for msg in limited_history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # Добавляем текущее сообщение пользователя
        messages.append({
            "role": "user",
            "content": request.message
        })

        # Логируем запрос
        logger.info(
            f"Chat request received: model={request.model or 'default'}, "
            f"messages={len(messages)}, "
            f"max_tokens={request.max_tokens}, "
            f"use_modules={request.use_modules}"
        )

        # Получаем ответ от AI
        result = await ai_service.generate_response(
            messages=messages,
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system_prompt=request.system_prompt
        )

        # Формируем ответ
        return ChatResponse(
            response=result["response"],
            model=result["model"],
            usage=TokenUsage(**result["usage"])
        )

    except ValueError as e:
        logger.error(f"Validation error in chat request: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing chat request: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/chat/models", response_model=ModelsListResponse)
async def get_models():
    """
    Получение списка доступных AI моделей.

    Returns:
        Список моделей с информацией о них
    """
    try:
        ai_service = get_ai_service()
        models_data = await ai_service.get_available_models()

        # Преобразуем в схемы
        models = [ModelInfo(**model) for model in models_data]

        return ModelsListResponse(models=models)

    except Exception as e:
        logger.error(f"Error fetching models: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch models")


@router.get("/chat/agent-categories")
async def get_agent_categories():
    """
    Получение списка доступных категорий агентов.

    Returns:
        Словарь с категориями и их описаниями
    """
    try:
        categories = get_available_categories()
        return {"categories": categories}

    except Exception as e:
        logger.error(f"Error fetching agent categories: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch agent categories")


@router.get("/chat/agent-category/{category_id}/details")
async def get_category_details(category_id: str):
    """
    Получение детальной информации о модулях категории.

    Args:
        category_id: ID категории (например, "critical_alerts")

    Returns:
        Детальная информация о модулях категории
    """
    try:
        from services.ai_agent.modules_spec_parser import get_spec_parser
        from services.ai_agent.modules_metadata import get_modules_by_category

        # Получаем метаданные модулей из category
        modules_in_category = get_modules_by_category(category_id)

        # Получаем детальную информацию из спецификации
        spec_parser = get_spec_parser()

        result = []
        for module_id in modules_in_category:
            spec_info = spec_parser.get_module_info(module_id)
            if spec_info:
                result.append(spec_info)

        return {"category_id": category_id, "modules": result}

    except Exception as e:
        logger.error(f"Error fetching category details: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch category details")


# === История чатов ===

@router.post("/chat/new")
async def create_chat(db: Session = Depends(get_db)):
    """
    Создание нового чата.
    
    Returns:
        Информация о созданном чате
    """
    try:
        chat = ChatSession(title="Новый чат")
        db.add(chat)
        db.commit()
        db.refresh(chat)
        
        return chat.to_dict()
    except Exception as e:
        logger.error(f"Error creating chat: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create chat")


@router.get("/chat/list")
async def list_chats(db: Session = Depends(get_db)):
    """
    Получение списка всех чатов.
    
    Returns:
        Список чатов с базовой информацией
    """
    try:
        chats = db.query(ChatSession).order_by(ChatSession.updated_at.desc()).all()
        return {"chats": [chat.to_dict() for chat in chats]}
    except Exception as e:
        logger.error(f"Error listing chats: {e}")
        raise HTTPException(status_code=500, detail="Failed to list chats")


@router.get("/chat/{chat_id}")
async def get_chat(chat_id: int, db: Session = Depends(get_db)):
    """
    Получение чата с историей сообщений.
    
    Args:
        chat_id: ID чата
        
    Returns:
        Информация о чате и его сообщения
    """
    try:
        chat = db.query(ChatSession).filter(ChatSession.id == chat_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        # Получаем сообщения
        messages = [msg.to_dict() for msg in chat.messages]
        
        result = chat.to_dict()
        result['messages'] = messages
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chat: {e}")
        raise HTTPException(status_code=500, detail="Failed to get chat")


@router.delete("/chat/{chat_id}")
async def delete_chat(chat_id: int, db: Session = Depends(get_db)):
    """
    Удаление чата и всех его сообщений.

    Args:
        chat_id: ID чата

    Returns:
        Статус удаления
    """
    try:
        chat = db.query(ChatSession).filter(ChatSession.id == chat_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        db.delete(chat)
        db.commit()

        return {"status": "deleted", "chat_id": chat_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting chat: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete chat")


@router.delete("/chat/all")
async def delete_all_chats(db: Session = Depends(get_db)):
    """
    Удаление всех чатов и их сообщений.

    Returns:
        Статус удаления и количество удаленных чатов
    """
    try:
        # Считаем количество чатов перед удалением
        total_chats = db.query(ChatSession).count()

        # Удаляем все чаты (сообщения удалятся каскадно)
        db.query(ChatSession).delete()
        db.commit()

        return {
            "status": "deleted",
            "total_deleted": total_chats
        }
    except Exception as e:
        logger.error(f"Error deleting all chats: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete all chats")


@router.put("/chat/{chat_id}/title")
async def update_chat_title(
    chat_id: int, 
    title: str,
    db: Session = Depends(get_db)
):
    """
    Обновление заголовка чата.
    
    Args:
        chat_id: ID чата
        title: Новый заголовок
        
    Returns:
        Обновленная информация о чате
    """
    try:
        chat = db.query(ChatSession).filter(ChatSession.id == chat_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        chat.title = title
        chat.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(chat)
        
        return chat.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating chat title: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update chat title")


@router.post("/chat/{chat_id}/messages")
async def add_messages(
    chat_id: int,
    messages: List[ChatMessage],
    db: Session = Depends(get_db)
):
    """
    Добавление сообщений в чат.
    Используется для сохранения истории после отправки сообщения.
    
    Args:
        chat_id: ID чата
        messages: Список сообщений для добавления
        
    Returns:
        Статус операции
    """
    try:
        chat = db.query(ChatSession).filter(ChatSession.id == chat_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        # Добавляем сообщения
        for msg in messages:
            db_message = DBChatMessage(
                chat_id=chat_id,
                role=msg.role,
                content=msg.content
            )
            db.add(db_message)
        
        # Обновляем title при первом сообщении пользователя
        if len(chat.messages) == 0 and messages:
            first_user_message = next((m for m in messages if m.role == 'user'), None)
            if first_user_message:
                # Генерируем title из первых 50-60 символов
                content = first_user_message.content.strip()
                if len(content) <= 10:
                    chat.title = content
                else:
                    chat.title = content[:60] + ('...' if len(content) > 60 else '')
        
        chat.updated_at = datetime.utcnow()
        db.commit()

        return {"status": "success", "messages_added": len(messages)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding messages: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to add messages")


# === Шаблоны промптов ===

@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(db: Session = Depends(get_db)):
    """
    Получение списка всех шаблонов.

    Returns:
        Список шаблонов отсортированных от новых к старым
    """
    try:
        templates = db.query(ChatTemplate).order_by(ChatTemplate.created_at.desc()).all()
        return TemplateListResponse(templates=[TemplateResponse(**t.to_dict()) for t in templates])
    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to list templates")


@router.post("/templates", response_model=TemplateResponse)
async def create_template(template: TemplateCreate, db: Session = Depends(get_db)):
    """
    Создание нового шаблона.

    Args:
        template: Данные для создания шаблона

    Returns:
        Информация о созданном шаблоне
    """
    try:
        db_template = ChatTemplate(
            title=template.title,
            prompt=template.prompt,
            icon=template.icon
        )
        db.add(db_template)
        db.commit()
        db.refresh(db_template)

        return TemplateResponse(**db_template.to_dict())
    except Exception as e:
        logger.error(f"Error creating template: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create template")


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: int, db: Session = Depends(get_db)):
    """
    Получение шаблона по ID.

    Args:
        template_id: ID шаблона

    Returns:
        Информация о шаблоне
    """
    try:
        template = db.query(ChatTemplate).filter(ChatTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        return TemplateResponse(**template.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting template: {e}")
        raise HTTPException(status_code=500, detail="Failed to get template")


@router.put("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    template: TemplateUpdate,
    db: Session = Depends(get_db)
):
    """
    Обновление шаблона.

    Args:
        template_id: ID шаблона
        template: Данные для обновления

    Returns:
        Обновленная информация о шаблоне
    """
    try:
        db_template = db.query(ChatTemplate).filter(ChatTemplate.id == template_id).first()
        if not db_template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Обновляем только те поля, которые переданы
        if template.title is not None:
            db_template.title = template.title
        if template.prompt is not None:
            db_template.prompt = template.prompt
        if template.icon is not None:
            db_template.icon = template.icon

        db_template.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(db_template)

        return TemplateResponse(**db_template.to_dict())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating template: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update template")


@router.delete("/templates/{template_id}")
async def delete_template(template_id: int, db: Session = Depends(get_db)):
    """
    Удаление шаблона.

    Args:
        template_id: ID шаблона

    Returns:
        Статус удаления
    """
    try:
        template = db.query(ChatTemplate).filter(ChatTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        db.delete(template)
        db.commit()

        return {"status": "deleted", "template_id": template_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting template: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete template")


# === Управление системными промптами агентов ===

@router.get("/chat/agent-prompts/{category_id}")
async def get_agent_prompt(category_id: str):
    """
    Получение системного промпта для категории агента.

    Args:
        category_id: ID категории (например, "critical_alerts")

    Returns:
        {
            "category_id": str,
            "current_prompt": str,  # Текущий промпт (кастомный или дефолтный)
            "default_prompt": str,  # Дефолтный промпт
            "is_custom": bool       # Используется ли кастомный промпт
        }
    """
    try:
        prompt_manager = get_prompt_manager()

        # Получаем текущий и дефолтный промпты
        current_prompt = prompt_manager.get_prompt(category_id)
        default_prompt = prompt_manager.get_default_prompt(category_id)
        is_custom = prompt_manager.is_custom(category_id)

        return {
            "category_id": category_id,
            "current_prompt": current_prompt,
            "default_prompt": default_prompt,
            "is_custom": is_custom
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting agent prompt: {e}")
        raise HTTPException(status_code=500, detail="Failed to get agent prompt")


@router.put("/chat/agent-prompts/{category_id}")
async def update_agent_prompt(category_id: str, request: dict):
    """
    Обновление системного промпта для категории агента.

    Args:
        category_id: ID категории
        request: {"prompt": str}  # Новый текст промпта

    Returns:
        {"status": "updated", "category_id": str, "is_custom": true}
    """
    try:
        if "prompt" not in request:
            raise HTTPException(status_code=400, detail="Missing 'prompt' field")

        new_prompt = request["prompt"]

        if not new_prompt or not isinstance(new_prompt, str):
            raise HTTPException(status_code=400, detail="Invalid prompt value")

        prompt_manager = get_prompt_manager()
        prompt_manager.update_prompt(category_id, new_prompt)

        return {
            "status": "updated",
            "category_id": category_id,
            "is_custom": True
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent prompt: {e}")
        raise HTTPException(status_code=500, detail="Failed to update agent prompt")


@router.post("/chat/agent-prompts/{category_id}/reset")
async def reset_agent_prompt(category_id: str):
    """
    Сброс системного промпта к дефолтному значению.

    Args:
        category_id: ID категории

    Returns:
        {"status": "reset", "category_id": str, "is_custom": false}
    """
    try:
        prompt_manager = get_prompt_manager()
        prompt_manager.reset_to_default(category_id)

        return {
            "status": "reset",
            "category_id": category_id,
            "is_custom": False
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error resetting agent prompt: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset agent prompt")

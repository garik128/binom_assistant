"""
ORM модели для базы данных
"""
import json
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    Date, Numeric, Text, ForeignKey, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship, validates
from .base import Base


class Campaign(Base):
    """
    Модель кампании
    """
    __tablename__ = 'campaigns'

    internal_id = Column(Integer, primary_key=True, autoincrement=True)
    binom_id = Column(Integer, nullable=False, unique=True)
    current_name = Column(String(255), nullable=False)
    group_name = Column(String(255))
    ts_id = Column(Integer, nullable=True, index=True)  # Добавлено: связь с Traffic Source
    ts_name = Column(String(255))
    domain_name = Column(String(255))
    is_cpl_mode = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    status = Column(String(20), default='active')
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    daily_stats = relationship("CampaignStatsDaily", back_populates="campaign", cascade="all, delete-orphan")
    weekly_stats = relationship("StatWeekly", back_populates="campaign", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="campaign", cascade="all, delete-orphan")
    name_changes = relationship("NameChange", back_populates="campaign", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Campaign {self.binom_id}: {self.current_name}>"

    def to_dict(self):
        """Преобразует модель в словарь"""
        return {
            'internal_id': self.internal_id,
            'binom_id': self.binom_id,
            'current_name': self.current_name,
            'group_name': self.group_name,
            'ts_name': self.ts_name,
            'domain_name': self.domain_name,
            'is_cpl_mode': self.is_cpl_mode,
            'is_active': self.is_active,
            'status': self.status,
            'first_seen': self.first_seen.isoformat() if self.first_seen else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
        }


class CampaignStatsDaily(Base):
    """
    Модель дневной статистики кампаний
    """
    __tablename__ = 'campaign_stats_daily'

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey('campaigns.internal_id', ondelete='CASCADE'), nullable=False)
    date = Column(Date, nullable=False)

    # Основные метрики
    clicks = Column(Integer, default=0)
    leads = Column(Integer, default=0)
    cost = Column(Numeric(10, 2), default=0)
    revenue = Column(Numeric(10, 2), default=0)

    # Производные метрики
    roi = Column(Numeric(10, 2))
    cr = Column(Numeric(10, 4))
    cpc = Column(Numeric(10, 4))
    approve = Column(Numeric(10, 2))  # Процент апрува от Binom API (формула: a_leads/(a_leads+h_leads+r_leads)*100)

    # Лиды по статусам
    a_leads = Column(Integer, default=0)
    h_leads = Column(Integer, default=0)
    r_leads = Column(Integer, default=0)

    # Дополнительно
    lead_price = Column(Numeric(10, 2))
    profit = Column(Numeric(10, 2))
    epc = Column(Numeric(10, 4))

    # Мета
    snapshot_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    campaign = relationship("Campaign", back_populates="daily_stats")

    # Уникальность
    __table_args__ = (
        UniqueConstraint('campaign_id', 'date', name='unique_campaign_date'),
    )

    @validates('cost', 'revenue')
    def validate_positive_money(self, key, value):
        """
        Валидация стоимости и дохода - не могут быть отрицательными

        Args:
            key: имя поля
            value: значение

        Returns:
            Проверенное значение

        Raises:
            ValueError: если значение отрицательное
        """
        if value is not None and value < 0:
            raise ValueError(f"{key} не может быть отрицательным: {value}")
        return value

    @validates('clicks', 'leads', 'a_leads', 'h_leads', 'r_leads')
    def validate_counts(self, key, value):
        """
        Валидация счетчиков - не могут быть отрицательными

        Args:
            key: имя поля
            value: значение

        Returns:
            Проверенное значение

        Raises:
            ValueError: если значение отрицательное
        """
        if value is not None and value < 0:
            raise ValueError(f"{key} не может быть отрицательным: {value}")
        return value

    @validates('cr')
    def validate_cr(self, key, value):
        """
        Валидация Conversion Rate
        CR хранится в процентах (0-100)
        Формула: (leads / clicks) * 100

        Args:
            key: имя поля
            value: значение

        Returns:
            Проверенное значение

        Raises:
            ValueError: если значение выходит за допустимые границы
        """
        if value is not None:
            # CR хранится в процентах: 0-100
            if value < 0:
                raise ValueError(f"CR не может быть отрицательным: {value}")
            if value > 100:
                raise ValueError(f"CR не может быть больше 100%: {value}")
        return value

    @validates('roi')
    def validate_roi(self, key, value):
        """
        Валидация ROI - только минимальная граница
        ROI хранится в процентах (-100 до бесконечности)

        ВАЖНО: Верхняя граница не проверяется, т.к. в Binom могут быть
        ошибки данных с ROI = 1000000%, которые не должны ломать систему.
        Такие аномалии обрабатываются в алертах и AI-анализе.

        Args:
            key: имя поля
            value: значение

        Returns:
            Проверенное значение

        Raises:
            ValueError: если ROI меньше -100% (полная потеря + долг)
        """
        if value is not None:
            # Минимум -100% (полная потеря)
            # Теоретически может быть меньше при дополнительных расходах,
            # но это уже критическая ошибка
            if value < -100:
                raise ValueError(f"ROI не может быть меньше -100%: {value}")
        return value

    @validates('approve')
    def validate_approve(self, key, value):
        """
        Валидация процента апрува - от 0 до 100%

        Args:
            key: имя поля
            value: значение

        Returns:
            Проверенное значение

        Raises:
            ValueError: если значение вне диапазона 0-100
        """
        if value is not None:
            if value < 0:
                raise ValueError(f"Approve не может быть отрицательным: {value}")
            if value > 100:
                raise ValueError(f"Approve не может быть больше 100%: {value}")
        return value

    def __repr__(self):
        return f"<CampaignStatsDaily {self.campaign_id} on {self.date}>"

    def to_dict(self):
        """Преобразует модель в словарь"""
        return {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'date': self.date.isoformat() if self.date else None,
            'clicks': self.clicks,
            'leads': self.leads,
            'cost': float(self.cost) if self.cost else 0,
            'revenue': float(self.revenue) if self.revenue else 0,
            'roi': float(self.roi) if self.roi else None,
            'cr': float(self.cr) if self.cr else None,
            'cpc': float(self.cpc) if self.cpc else None,
            'approve': float(self.approve) if self.approve else None,
            'a_leads': self.a_leads,
            'h_leads': self.h_leads,
            'r_leads': self.r_leads,
        }


class StatPeriod(Base):
    """
    Модель агрегированной статистики за период
    Сохраняются данные из первого запроса get_campaigns()
    без дневной разбивки (экономия 270 запросов к API)
    """
    __tablename__ = 'stats_period'

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey('campaigns.internal_id', ondelete='CASCADE'), nullable=False)

    # Период данных (1=сегодня, 3=7дней, 4=14дней, 12=произвольный)
    period_type = Column(String(20), nullable=False)  # 'today', '7days', '14days', '30days', 'custom'
    period_start = Column(Date)
    period_end = Column(Date)

    # Основные метрики (агрегированные за период)
    clicks = Column(Integer, default=0)
    leads = Column(Integer, default=0)
    cost = Column(Numeric(10, 2), default=0)
    revenue = Column(Numeric(10, 2), default=0)

    # Производные метрики
    roi = Column(Numeric(10, 2))
    cr = Column(Numeric(10, 4))
    cpc = Column(Numeric(10, 4))
    approve = Column(Numeric(10, 2))  # Процент апрува от Binom API (формула: a_leads/(a_leads+h_leads+r_leads)*100)

    # Лиды по статусам
    a_leads = Column(Integer, default=0)
    h_leads = Column(Integer, default=0)
    r_leads = Column(Integer, default=0)

    # Дополнительно
    lead_price = Column(Numeric(10, 2))
    profit = Column(Numeric(10, 2))
    epc = Column(Numeric(10, 4))

    # Мета
    snapshot_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    campaign = relationship("Campaign", foreign_keys=[campaign_id])

    # Уникальность: одна кампания + один период + одно время снимка (можно обновлять)
    __table_args__ = (
        UniqueConstraint('campaign_id', 'period_type', 'period_start', 'period_end', name='unique_campaign_period'),
    )

    def __repr__(self):
        return f"<StatPeriod {self.campaign_id} {self.period_type}>"

    def to_dict(self):
        """Преобразует модель в словарь"""
        return {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'period_type': self.period_type,
            'period_start': self.period_start.isoformat() if self.period_start else None,
            'period_end': self.period_end.isoformat() if self.period_end else None,
            'clicks': self.clicks,
            'leads': self.leads,
            'cost': float(self.cost) if self.cost else 0,
            'revenue': float(self.revenue) if self.revenue else 0,
            'roi': float(self.roi) if self.roi else None,
            'cr': float(self.cr) if self.cr else None,
            'cpc': float(self.cpc) if self.cpc else None,
            'approve': float(self.approve) if self.approve else None,
            'a_leads': self.a_leads,
            'h_leads': self.h_leads,
            'r_leads': self.r_leads,
            'profit': float(self.profit) if self.profit else None,
            'epc': float(self.epc) if self.epc else None,
        }


class StatWeekly(Base):
    """
    Модель недельной статистики
    """
    __tablename__ = 'stats_weekly'

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey('campaigns.internal_id', ondelete='CASCADE'), nullable=False)
    week_start = Column(Date, nullable=False)
    week_end = Column(Date, nullable=False)

    # Суммарные метрики
    total_clicks = Column(Integer, default=0)
    total_leads = Column(Integer, default=0)
    total_cost = Column(Numeric(10, 2), default=0)
    total_revenue = Column(Numeric(10, 2), default=0)
    total_profit = Column(Numeric(10, 2), default=0)

    # Средние метрики
    avg_roi = Column(Numeric(10, 2))
    avg_cr = Column(Numeric(10, 4))
    avg_cpc = Column(Numeric(10, 4))
    avg_approve = Column(Numeric(10, 2))

    # Лиды
    total_a_leads = Column(Integer, default=0)
    total_h_leads = Column(Integer, default=0)
    total_r_leads = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    campaign = relationship("Campaign", back_populates="weekly_stats")

    # Уникальность
    __table_args__ = (
        UniqueConstraint('campaign_id', 'week_start', name='unique_campaign_week'),
    )

    def __repr__(self):
        return f"<StatWeekly {self.campaign_id} week {self.week_start}>"


class Alert(Base):
    """
    Модель алерта
    """
    __tablename__ = 'alerts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey('campaigns.internal_id', ondelete='CASCADE'), nullable=False)
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), default='medium')

    details = Column(JSON)
    first_detected = Column(DateTime, nullable=False)
    last_checked = Column(DateTime, nullable=False)

    is_active = Column(Boolean, default=True)
    resolved_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    campaign = relationship("Campaign", back_populates="alerts")

    def __repr__(self):
        return f"<Alert {self.alert_type} for campaign {self.campaign_id}>"


class NameChange(Base):
    """
    Модель изменения имени кампании
    """
    __tablename__ = 'name_changes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    campaign_id = Column(Integer, ForeignKey('campaigns.internal_id', ondelete='CASCADE'), nullable=False)
    old_name = Column(String(255))
    new_name = Column(String(255), nullable=False)
    changed_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    campaign = relationship("Campaign", back_populates="name_changes")

    def __repr__(self):
        return f"<NameChange {self.campaign_id}: {self.old_name} -> {self.new_name}>"


class SystemCache(Base):
    """
    Модель системного кэша
    """
    __tablename__ = 'system_cache'

    key = Column(String(100), primary_key=True)
    value = Column(Text)
    expires_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<SystemCache {self.key}>"

    def get_value(self):
        """Получает значение, пытаясь распарсить JSON"""
        try:
            return json.loads(self.value)
        except:
            return self.value

    def set_value(self, value):
        """Устанавливает значение, сериализуя в JSON если нужно"""
        if isinstance(value, (dict, list)):
            self.value = json.dumps(value)
        else:
            self.value = str(value)


class TrafficSource(Base):
    """
    Источник трафика (TrafficStars, Exoclick и т.д.)

    ВАЖНО: name может меняться в Binom!
    - Поле name хранит ТЕКУЩЕЕ название
    - Никаких unique constraint на name
    - Поиск/идентификация ТОЛЬКО по id
    """
    __tablename__ = 'traffic_sources'

    id = Column(Integer, primary_key=True)  # ID из Binom - ГЛАВНЫЙ ключ!
    name = Column(String(255), nullable=False, index=True)  # Может меняться!
    status = Column(Boolean, default=True, index=True)

    # Настройки
    ts_integration_id = Column(Integer)
    postback_url = Column(Text)
    external_param_name = Column(String(100))  # e_name
    external_param_value = Column(String(100))  # e_value

    # Счетчики
    total_campaigns = Column(Integer, default=0)

    # Временные метки
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<TrafficSource {self.id}: {self.name}>"


class TrafficSourceStatsDaily(Base):
    """Дневная статистика по источнику трафика"""
    __tablename__ = 'traffic_source_stats_daily'

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_id = Column(Integer, ForeignKey('traffic_sources.id'), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)

    # Основные метрики
    clicks = Column(Integer, default=0)
    cost = Column(Numeric(10, 2), default=0)
    leads = Column(Integer, default=0)
    revenue = Column(Numeric(10, 2), default=0)

    # Производные
    roi = Column(Numeric(10, 2))
    cr = Column(Numeric(10, 4))
    cpc = Column(Numeric(10, 4))

    # Лиды по статусам
    a_leads = Column(Integer, default=0)
    h_leads = Column(Integer, default=0)
    r_leads = Column(Integer, default=0)
    approve = Column(Numeric(10, 2))

    # Служебные
    active_campaigns = Column(Integer, default=0)  # сколько кампаний использует
    snapshot_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('ts_id', 'date', name='unique_ts_date'),
    )

    def __repr__(self):
        return f"<TSStatsDaily {self.ts_id} on {self.date}>"


class AffiliateNetwork(Base):
    """
    Партнерская сеть

    ВАЖНО: name может меняться в Binom!
    - Поле name хранит ТЕКУЩЕЕ название
    - Никаких unique constraint на name
    - Поиск/идентификация ТОЛЬКО по id
    """
    __tablename__ = 'affiliate_networks'

    id = Column(Integer, primary_key=True)  # ID из Binom - ГЛАВНЫЙ ключ!
    name = Column(String(255), nullable=False, index=True)  # Может меняться!
    status = Column(Boolean, default=True, index=True)

    # Настройки
    postback_url = Column(Text)
    offer_url_template = Column(Text)

    # Счетчики
    total_offers = Column(Integer, default=0)

    # Временные метки
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<AffiliateNetwork {self.id}: {self.name}>"


class NetworkStatsDaily(Base):
    """Дневная статистика по партнерке"""
    __tablename__ = 'network_stats_daily'

    id = Column(Integer, primary_key=True, autoincrement=True)
    network_id = Column(Integer, ForeignKey('affiliate_networks.id'), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)

    # Основные метрики
    clicks = Column(Integer, default=0)
    leads = Column(Integer, default=0)
    revenue = Column(Numeric(10, 2), default=0)
    cost = Column(Numeric(10, 2), default=0)

    # Статусы лидов
    a_leads = Column(Integer, default=0)
    h_leads = Column(Integer, default=0)
    r_leads = Column(Integer, default=0)

    # Производные
    approve = Column(Numeric(10, 2))
    roi = Column(Numeric(10, 2))
    profit = Column(Numeric(10, 2))

    # Служебные
    active_offers = Column(Integer, default=0)
    snapshot_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('network_id', 'date', name='unique_network_date'),
    )

    def __repr__(self):
        return f"<NetworkStatsDaily {self.network_id} on {self.date}>"


class Offer(Base):
    """
    Оффер

    ВАЖНО: name может меняться в Binom!
    - Поле name хранит ТЕКУЩЕЕ название
    - Никаких unique constraint на name
    - Поиск/идентификация ТОЛЬКО по id
    """
    __tablename__ = 'offers'

    id = Column(Integer, primary_key=True)  # ID из Binom - ГЛАВНЫЙ ключ!
    name = Column(String(255), nullable=False, index=True)  # Может меняться!
    network_id = Column(Integer, ForeignKey('affiliate_networks.id'), nullable=True)

    # Параметры
    geo = Column(String(100), index=True)
    payout = Column(Numeric(10, 2))
    currency = Column(String(10), default='usd')
    url = Column(Text)

    # Группировка
    group_id = Column(Integer)
    group_name = Column(String(255))

    # Статус
    status = Column(Boolean, default=True, index=True)
    is_banned = Column(Boolean, default=False)

    # Временные метки
    first_seen = Column(DateTime, nullable=False)
    last_seen = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Offer {self.id}: {self.name}>"


class OfferStatsDaily(Base):
    """Дневная статистика по офферу"""
    __tablename__ = 'offer_stats_daily'

    id = Column(Integer, primary_key=True, autoincrement=True)
    offer_id = Column(Integer, ForeignKey('offers.id'), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)

    # Основные метрики
    clicks = Column(Integer, default=0)
    leads = Column(Integer, default=0)
    revenue = Column(Numeric(10, 2), default=0)
    cost = Column(Numeric(10, 2), default=0)

    # Статусы лидов
    a_leads = Column(Integer, default=0)
    h_leads = Column(Integer, default=0)
    r_leads = Column(Integer, default=0)

    # Производные
    cr = Column(Numeric(10, 4))
    approve = Column(Numeric(10, 2))
    epc = Column(Numeric(10, 4))
    roi = Column(Numeric(10, 2))

    # Служебные
    snapshot_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('offer_id', 'date', name='unique_offer_date'),
    )

    def __repr__(self):
        return f"<OfferStatsDaily {self.offer_id} on {self.date}>"


class ModuleConfig(Base):
    """
    Конфигурация модулей аналитики.
    Хранит настройки каждого модуля.
    """
    __tablename__ = 'module_configs'

    module_id = Column(String(100), primary_key=True)
    enabled = Column(Boolean, default=True)
    schedule = Column(String(100), nullable=True)
    alerts_enabled = Column(Boolean, default=False)  # Генерация алертов (по умолчанию выключена)
    timeout_seconds = Column(Integer, default=30)
    cache_ttl_seconds = Column(Integer, default=3600)
    params = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    runs = relationship("ModuleRun", back_populates="config", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ModuleConfig {self.module_id}>"


class ModuleRun(Base):
    """
    История запусков модулей.
    Сохраняет результаты каждого выполнения.
    """
    __tablename__ = 'module_runs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_id = Column(String(100), ForeignKey('module_configs.module_id'), nullable=False)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False)
    results = Column(JSON, nullable=True)
    params = Column(JSON, nullable=True)  # параметры запуска модуля
    error = Column(Text, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    config = relationship("ModuleConfig", back_populates="runs")

    def __repr__(self):
        return f"<ModuleRun {self.module_id} at {self.started_at}>"


class ModuleCache(Base):
    """
    Кэш результатов модулей.
    Позволяет не перезапускать модули с одинаковыми параметрами.
    """
    __tablename__ = 'module_cache'

    id = Column(Integer, primary_key=True, autoincrement=True)
    module_id = Column(String(100), nullable=False, index=True)
    cache_key = Column(String(200), nullable=False)
    data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint('module_id', 'cache_key', name='unique_module_cache'),
    )

    def __repr__(self):
        return f"<ModuleCache {self.module_id}:{self.cache_key}>"


class BackgroundTask(Base):
    """
    Модель для отслеживания фоновых задач.
    Используется для мониторинга прогресса длительных операций.
    """
    __tablename__ = 'background_tasks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_type = Column(String(50), nullable=False, index=True)  # 'data_collection', 'module_run', etc
    status = Column(String(20), nullable=False, default='pending')  # pending, running, completed, failed
    progress = Column(Integer, default=0)  # 0-100
    progress_message = Column(String(500))  # текущее действие
    result = Column(JSON, nullable=True)  # результат выполнения
    error = Column(Text, nullable=True)  # текст ошибки
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<BackgroundTask {self.id}: {self.task_type} - {self.status}>"

    def to_dict(self):
        """Преобразует модель в словарь"""
        return {
            'id': self.id,
            'task_type': self.task_type,
            'status': self.status,
            'progress': self.progress,
            'progress_message': self.progress_message,
            'result': self.result,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class AppSettings(Base):
    """
    Модель для хранения настроек приложения.

    Приоритет значений (cascading):
    1. БД (app_settings) - если есть запись
    2. .env файл - если нет в БД
    3. Hardcoded defaults - если нигде нет
    """
    __tablename__ = 'app_settings'

    key = Column(String(100), primary_key=True)
    value = Column(String(500), nullable=False)
    value_type = Column(String(20), nullable=False, default='string')  # 'int', 'float', 'bool', 'string', 'json'
    category = Column(String(50), nullable=False, index=True)  # 'collector', 'schedule', 'filters', 'ai', etc
    description = Column(String(500))
    is_editable = Column(Boolean, default=True)
    min_value = Column(Numeric(10, 2), nullable=True)  # минимальное значение для числовых настроек
    max_value = Column(Numeric(10, 2), nullable=True)  # максимальное значение для числовых настроек
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    @validates('value')
    def validate_value(self, key, value):
        """Валидация значения на основе типа и диапазона"""
        if self.value_type == 'int':
            int_value = int(value)
            if self.min_value is not None and int_value < self.min_value:
                raise ValueError(f"Value {int_value} is less than minimum {self.min_value}")
            if self.max_value is not None and int_value > self.max_value:
                raise ValueError(f"Value {int_value} is greater than maximum {self.max_value}")
        elif self.value_type == 'float':
            float_value = float(value)
            if self.min_value is not None and float_value < self.min_value:
                raise ValueError(f"Value {float_value} is less than minimum {self.min_value}")
            if self.max_value is not None and float_value > self.max_value:
                raise ValueError(f"Value {float_value} is greater than maximum {self.max_value}")
        return value

    def __repr__(self):
        return f"<AppSettings {self.key}={self.value} ({self.value_type})>"

    def to_dict(self):
        """Преобразует модель в словарь"""
        return {
            'key': self.key,
            'value': self.get_typed_value(),
            'value_raw': self.value,
            'value_type': self.value_type,
            'category': self.category,
            'description': self.description,
            'is_editable': self.is_editable,
            'min_value': float(self.min_value) if self.min_value is not None else None,
            'max_value': float(self.max_value) if self.max_value is not None else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def get_typed_value(self):
        """Возвращает значение правильного типа"""
        if self.value_type == 'int':
            return int(self.value)
        elif self.value_type == 'float':
            return float(self.value)
        elif self.value_type == 'bool':
            return self.value.lower() in ('true', '1', 'yes')
        elif self.value_type == 'json':
            import json
            return json.loads(self.value)
        else:
            return self.value

class ChatSession(Base):
    """
    Модель сессии чата с AI
    """
    __tablename__ = 'chat_sessions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False, default='Новый чат')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Связи
    messages = relationship("ChatMessage", back_populates="chat", cascade="all, delete-orphan", order_by="ChatMessage.created_at")

    def __repr__(self):
        return f"<ChatSession {self.id}: {self.title}>"

    def to_dict(self):
        """Преобразует модель в словарь"""
        return {
            'id': self.id,
            'title': self.title,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'message_count': len(self.messages) if self.messages else 0,
        }


class ChatMessage(Base):
    """
    Модель сообщения в чате
    """
    __tablename__ = 'chat_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(Integer, ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user' или 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Связи
    chat = relationship("ChatSession", back_populates="messages")

    def __repr__(self):
        return f"<ChatMessage {self.id} ({self.role}): {self.content[:50]}...>"

    def to_dict(self):
        """Преобразует модель в словарь"""
        return {
            'id': self.id,
            'chat_id': self.chat_id,
            'role': self.role,
            'content': self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class ChatTemplate(Base):
    """
    Модель шаблона промпта для чата
    """
    __tablename__ = 'chat_templates'

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    prompt = Column(Text, nullable=False)
    icon = Column(String(50), nullable=False, default='message')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ChatTemplate {self.id}: {self.title}>"

    def to_dict(self):
        """Преобразует модель в словарь"""
        return {
            'id': self.id,
            'title': self.title,
            'prompt': self.prompt,
            'icon': self.icon,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

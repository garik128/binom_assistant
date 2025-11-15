"""
Тест валидаторов ORM моделей

Проверяет что валидация данных работает корректно:
- cost, revenue >= 0
- clicks, leads >= 0
- CR в диапазоне [0, 1.0]
- ROI в диапазоне [-100, 10000]
- approve в диапазоне [0, 100]

Использование:
    python binom_assistant/storage/database/test_validators.py
"""
import sys
from pathlib import Path
from datetime import datetime, date

# Добавляем корневую папку проекта в PYTHONPATH
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "binom_assistant"))

from storage.database import StatDaily, Campaign
from storage.database.base import Base, get_engine, get_session_factory
from sqlalchemy.exc import StatementError


def test_positive_validators():
    """
    Тест валидаторов положительных значений
    """
    print("\n" + "="*60)
    print("ТЕСТ 1: Валидаторы положительных значений")
    print("="*60)

    factory = get_session_factory()
    session = factory()

    try:
        # Создаем тестовую кампанию
        campaign = Campaign(
            binom_id=999999,
            current_name="Test Campaign",
            first_seen=datetime.now(),
            last_seen=datetime.now()
        )
        session.add(campaign)
        session.flush()

        # Тест 1.1: Отрицательный cost
        print("\n[ТЕСТ 1.1] Попытка создать запись с отрицательным cost...")
        try:
            stat = StatDaily(
                campaign_id=campaign.internal_id,
                date=date.today(),
                cost=-100,  # Отрицательное значение
                snapshot_time=datetime.now()
            )
            session.add(stat)
            session.flush()
            print("  [FAIL] FAIL: Не выбросило исключение для отрицательного cost")
            return False
        except ValueError as e:
            print(f"  [OK] PASS: {e}")
            session.rollback()

        # Тест 1.2: Отрицательный revenue
        print("\n[ТЕСТ 1.2] Попытка создать запись с отрицательным revenue...")
        try:
            stat = StatDaily(
                campaign_id=campaign.internal_id,
                date=date.today(),
                revenue=-50,  # Отрицательное значение
                snapshot_time=datetime.now()
            )
            session.add(stat)
            session.flush()
            print("  [FAIL] FAIL: Не выбросило исключение для отрицательного revenue")
            return False
        except ValueError as e:
            print(f"  [OK] PASS: {e}")
            session.rollback()

        # Тест 1.3: Отрицательные clicks
        print("\n[ТЕСТ 1.3] Попытка создать запись с отрицательными clicks...")
        try:
            stat = StatDaily(
                campaign_id=campaign.internal_id,
                date=date.today(),
                clicks=-10,  # Отрицательное значение
                snapshot_time=datetime.now()
            )
            session.add(stat)
            session.flush()
            print("  [FAIL] FAIL: Не выбросило исключение для отрицательных clicks")
            return False
        except ValueError as e:
            print(f"  [OK] PASS: {e}")
            session.rollback()

        # Тест 1.4: Отрицательные leads
        print("\n[ТЕСТ 1.4] Попытка создать запись с отрицательными leads...")
        try:
            stat = StatDaily(
                campaign_id=campaign.internal_id,
                date=date.today(),
                leads=-5,  # Отрицательное значение
                snapshot_time=datetime.now()
            )
            session.add(stat)
            session.flush()
            print("  [FAIL] FAIL: Не выбросило исключение для отрицательных leads")
            return False
        except ValueError as e:
            print(f"  [OK] PASS: {e}")
            session.rollback()

        print("\n[OK] ВСЕ ТЕСТЫ ПОЛОЖИТЕЛЬНЫХ ЗНАЧЕНИЙ ПРОШЛИ\n")
        return True

    finally:
        session.rollback()
        session.close()


def test_cr_validator():
    """
    Тест валидатора CR (Conversion Rate)
    """
    print("\n" + "="*60)
    print("ТЕСТ 2: Валидатор CR (Conversion Rate)")
    print("="*60)

    factory = get_session_factory()
    session = factory()

    try:
        # Создаем тестовую кампанию
        campaign = Campaign(
            binom_id=999998,
            current_name="Test Campaign CR",
            first_seen=datetime.now(),
            last_seen=datetime.now()
        )
        session.add(campaign)
        session.flush()

        # Тест 2.1: CR > 100 (%)
        print("\n[ТЕСТ 2.1] Попытка создать запись с CR > 100%...")
        try:
            stat = StatDaily(
                campaign_id=campaign.internal_id,
                date=date.today(),
                cr=150,  # 150% - нереально (CR хранится в процентах 0-100)
                snapshot_time=datetime.now()
            )
            session.add(stat)
            session.flush()
            print("  [FAIL] FAIL: Не выбросило исключение для CR > 100")
            return False
        except ValueError as e:
            print(f"  [OK] PASS: {e}")
            session.rollback()

        # Тест 2.2: Отрицательный CR
        print("\n[ТЕСТ 2.2] Попытка создать запись с отрицательным CR...")
        try:
            stat = StatDaily(
                campaign_id=campaign.internal_id,
                date=date.today(),
                cr=-0.1,  # Отрицательный
                snapshot_time=datetime.now()
            )
            session.add(stat)
            session.flush()
            print("  [FAIL] FAIL: Не выбросило исключение для отрицательного CR")
            return False
        except ValueError as e:
            print(f"  [OK] PASS: {e}")
            session.rollback()

        # Тест 2.3: Корректный CR
        print("\n[ТЕСТ 2.3] Создание записи с корректным CR (0.05 = 5%)...")
        stat = StatDaily(
            campaign_id=campaign.internal_id,
            date=date.today(),
            cr=0.05,  # 5% - нормально
            snapshot_time=datetime.now()
        )
        session.add(stat)
        session.flush()
        print(f"  [OK] PASS: CR = {stat.cr}")
        session.rollback()

        print("\n[OK] ВСЕ ТЕСТЫ CR ПРОШЛИ\n")
        return True

    finally:
        session.rollback()
        session.close()


def test_roi_validator():
    """
    Тест валидатора ROI
    """
    print("\n" + "="*60)
    print("ТЕСТ 3: Валидатор ROI")
    print("="*60)

    factory = get_session_factory()
    session = factory()

    try:
        # Создаем тестовую кампанию
        campaign = Campaign(
            binom_id=999997,
            current_name="Test Campaign ROI",
            first_seen=datetime.now(),
            last_seen=datetime.now()
        )
        session.add(campaign)
        session.flush()

        # Тест 3.1: ROI < -100%
        print("\n[ТЕСТ 3.1] Попытка создать запись с ROI < -100%...")
        try:
            stat = StatDaily(
                campaign_id=campaign.internal_id,
                date=date.today(),
                roi=-150,  # Меньше -100%
                snapshot_time=datetime.now()
            )
            session.add(stat)
            session.flush()
            print("  [FAIL] FAIL: Не выбросило исключение для ROI < -100%")
            return False
        except ValueError as e:
            print(f"  [OK] PASS: {e}")
            session.rollback()

        # Тест 3.2: Экстремально большой ROI (ошибка в Binom)
        print("\n[ТЕСТ 3.2] Создание записи с экстремально большим ROI (1000000%)...")
        stat = StatDaily(
            campaign_id=campaign.internal_id,
            date=date.today(),
            roi=1000000,  # Ошибка в Binom - не должно ломать систему
            snapshot_time=datetime.now()
        )
        session.add(stat)
        session.flush()
        print(f"  [OK] PASS: ROI = {stat.roi}% (аномалия принята, будет обработана в алертах)")
        session.rollback()

        # Тест 3.3: Корректный ROI
        print("\n[ТЕСТ 3.3] Создание записи с корректным ROI (250%)...")
        stat = StatDaily(
            campaign_id=campaign.internal_id,
            date=date.today(),
            roi=250,  # 250% - нормально
            snapshot_time=datetime.now()
        )
        session.add(stat)
        session.flush()
        print(f"  [OK] PASS: ROI = {stat.roi}%")
        session.rollback()

        print("\n[OK] ВСЕ ТЕСТЫ ROI ПРОШЛИ\n")
        return True

    finally:
        session.rollback()
        session.close()


def test_approve_validator():
    """
    Тест валидатора Approve
    """
    print("\n" + "="*60)
    print("ТЕСТ 4: Валидатор Approve")
    print("="*60)

    factory = get_session_factory()
    session = factory()

    try:
        # Создаем тестовую кампанию
        campaign = Campaign(
            binom_id=999996,
            current_name="Test Campaign Approve",
            first_seen=datetime.now(),
            last_seen=datetime.now()
        )
        session.add(campaign)
        session.flush()

        # Тест 4.1: Approve > 100%
        print("\n[ТЕСТ 4.1] Попытка создать запись с Approve > 100%...")
        try:
            stat = StatDaily(
                campaign_id=campaign.internal_id,
                date=date.today(),
                approve=150,  # Больше 100%
                snapshot_time=datetime.now()
            )
            session.add(stat)
            session.flush()
            print("  [FAIL] FAIL: Не выбросило исключение для Approve > 100%")
            return False
        except ValueError as e:
            print(f"  [OK] PASS: {e}")
            session.rollback()

        # Тест 4.2: Отрицательный Approve
        print("\n[ТЕСТ 4.2] Попытка создать запись с отрицательным Approve...")
        try:
            stat = StatDaily(
                campaign_id=campaign.internal_id,
                date=date.today(),
                approve=-10,  # Отрицательный
                snapshot_time=datetime.now()
            )
            session.add(stat)
            session.flush()
            print("  [FAIL] FAIL: Не выбросило исключение для отрицательного Approve")
            return False
        except ValueError as e:
            print(f"  [OK] PASS: {e}")
            session.rollback()

        # Тест 4.3: Корректный Approve
        print("\n[ТЕСТ 4.3] Создание записи с корректным Approve (75%)...")
        stat = StatDaily(
            campaign_id=campaign.internal_id,
            date=date.today(),
            approve=75,  # 75% - нормально
            snapshot_time=datetime.now()
        )
        session.add(stat)
        session.flush()
        print(f"  [OK] PASS: Approve = {stat.approve}%")
        session.rollback()

        print("\n[OK] ВСЕ ТЕСТЫ APPROVE ПРОШЛИ\n")
        return True

    finally:
        session.rollback()
        session.close()


def main():
    """
    Основная функция запуска тестов
    """
    print("\n" + "="*70)
    print(" "*15 + "ТЕСТИРОВАНИЕ ВАЛИДАТОРОВ ORM")
    print("="*70)

    results = []

    # Запускаем все тесты
    results.append(("Положительные значения", test_positive_validators()))
    results.append(("CR (Conversion Rate)", test_cr_validator()))
    results.append(("ROI (Return on Investment)", test_roi_validator()))
    results.append(("Approve (процент апрува)", test_approve_validator()))

    # Итоги
    print("\n" + "="*70)
    print(" "*25 + "ИТОГИ ТЕСТИРОВАНИЯ")
    print("="*70)

    passed = 0
    failed = 0

    for name, result in results:
        status = "[OK] PASS" if result else "[FAIL] FAIL"
        print(f"{status}: {name}")
        if result:
            passed += 1
        else:
            failed += 1

    print("\n" + "="*70)
    print(f"Пройдено: {passed}/{len(results)}")
    print(f"Провалено: {failed}/{len(results)}")
    print("="*70 + "\n")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

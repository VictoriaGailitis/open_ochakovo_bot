"""One-off local provisioning of the two review accounts. Never exposed over HTTP."""
import argparse
import json
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path

from .app import Store
from .practice import MSK, Practice, provision_mentor, provision_practice
from .staff_auth import provision_account


def create_accounts(store, output):
    if output.exists():
        issued = json.loads(output.read_text())
        with store.transaction() as db:
            for account in issued:
                row = db.execute('SELECT user_id FROM staff_credentials WHERE login=?', (account['login'],)).fetchone()
                if not row or row['user_id'] != account['userId']:
                    raise ValueError('Файл выданных данных не соответствует базе. Проверьте путь --db.')
        return issued
    issued = [
        {'userId': 'staff:praktikant', 'role': 'intern', 'login': 'praktikant', 'password': secrets.token_urlsafe(15), 'name': 'Анна Петрова'},
        {'userId': 'staff:nastavnik', 'role': 'mentor', 'login': 'nastavnik', 'password': secrets.token_urlsafe(15), 'name': 'Елена Смирнова'},
    ]
    with store.transaction() as db:
        for account in issued:
            provision_account(db, user_id=account['userId'], login=account['login'], password=account['password'], role=account['role'])
            # These are review accounts; no self-registration or fictitious consent record.
            db.execute('UPDATE users SET profile=? WHERE id=?', (json.dumps({'fullName': account['name']}, ensure_ascii=False), account['userId']))
        mid = provision_mentor(db, user_id=issued[1]['userId'], name=issued[1]['name'], position='Ведущий специалист лаборатории',
                               contact='mentor@example.org', about='Помогу разобраться с задачами и методами исследования.', office_hours='Пн–пт, 09:00–17:00')
        today = datetime.now(MSK).date()
        start, end = today - timedelta(days=7), today + timedelta(days=28)
        pid = provision_practice(db, user_id=issued[0]['userId'], title='Лаборатория и качество', department='Лаборатория',
                                 start_date=start.isoformat(), end_date=end.isoformat(), mentor_id=mid, status='active',
                                 coordinator={'name': 'Координатор практики', 'contact': 'practice@example.org'},
                                 arrival='Главная проходная, 09:00. Наставник встретит у входа.',
                                 documents=[{'title': 'Отчёт по практике', 'status': 'В подготовке'}])
        service = Practice({})
        for i, title in enumerate(('Познакомиться с лабораторией', 'Освоить правила безопасности', 'Разобрать метод исследования', 'Провести исследование вместе', 'Представить результаты команде')):
            service.dispatch(db, issued[1]['userId'], 'POST', f'/api/practice/{pid}/goals', {
                'title': title, 'description': 'Обсудить и выполнить вместе с наставником.',
                'criteria': 'Объяснить последовательность действий и обсудить результат.',
                'dueDate': (today + timedelta(days=3 + i * 5)).isoformat(), 'clientKey': f'issued-goal-{i}'})
        rows = db.execute('SELECT id FROM practice_goals WHERE practice_id=? ORDER BY due_date', (pid,)).fetchall()
        for row in rows[:2]:
            db.execute("UPDATE practice_goals SET status='approved' WHERE id=?", (row['id'],))
        db.execute("UPDATE practice_goals SET status='in_progress' WHERE id=?", (rows[2]['id'],))
        meeting = datetime.now(MSK).replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=1)
        service.dispatch(db, issued[1]['userId'], 'POST', f'/api/practice/{pid}/meetings', {
            'title': 'Сверим, как идут дела', 'startsAt': meeting.isoformat(), 'endsAt': (meeting + timedelta(minutes=30)).isoformat(),
            'location': 'Лаборатория, 2 этаж', 'agenda': 'Первые результаты, вопросы и план на неделю.', 'clientKey': 'issued-first-meeting'})
    output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(issued, f, ensure_ascii=False, indent=2)
    return issued


def main():
    parser = argparse.ArgumentParser(description='Создать два тестовых аккаунта практики без регистрации')
    parser.add_argument('--db', required=True)
    args = parser.parse_args()
    db_path = Path(args.db).resolve()
    result = create_accounts(Store(db_path), db_path.with_name(db_path.stem + '-issued-accounts.json'))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

"""Create private Compose configuration without echoing secrets or overwriting it."""
import argparse
import getpass
import os
from pathlib import Path
import re
import secrets


def main():
    parser = argparse.ArgumentParser(description='Настройка размещения VK Mini App')
    parser.add_argument('--domain', required=True, help='Домен без https:// и пути')
    parser.add_argument('--app-id', required=True, help='Числовой ID приложения VK')
    args = parser.parse_args()
    domain = args.domain.lower().strip()
    labels = domain.split('.')
    if (len(domain) > 253 or len(labels) < 2 or
            all(label.isdigit() for label in labels) or
            not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels)):
        parser.error('Нужен публичный DNS-домен, например mini.example.ru (кириллический домен — в punycode).')
    if not re.fullmatch(r'[1-9][0-9]*', args.app_id):
        parser.error('ID приложения должен быть положительным целым числом.')
    path = Path(__file__).resolve().parent.parent / '.env.production'
    if path.exists():
        parser.error('.env.production уже существует. Измените его вручную; файл не перезаписан.')
    secret = getpass.getpass('Защищённый ключ приложения VK (ввод скрыт): ').strip()
    if not secret or any(char in secret for char in "'\r\n\x00"):
        parser.error('Ключ пуст или содержит недопустимые символы.')
    content = (
        '# Private server configuration. Do not commit or share.\n'
        f"APP_DOMAIN='{domain}'\nVK_APP_ID='{args.app_id}'\n"
        f"VK_APP_SECRET='{secret}'\nADMIN_TOKEN='{secrets.token_urlsafe(32)}'\n"
    )
    # Exclusive create also prevents a race from replacing an existing config.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as file:
        file.write(content)
    print(f'Создан {path} (права 600). HR-ключ сгенерирован и сохранён в ADMIN_TOKEN.')
    print('Запуск: docker compose --env-file .env.production up -d --build')
    print(f'URL для всех платформ в настройках VK: https://{domain}/')


if __name__ == '__main__':
    main()

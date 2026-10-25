// Read-only deployment checks; no real launch parameters or credentials needed.
const target = process.argv[2];
if (!target) {
  console.error('Использование: npm run check:deployment -- https://mini.example.ru');
  process.exit(1);
}

function check(condition, message) {
  if (!condition) throw new Error(message);
  console.log(`✓ ${message}`);
}

try {
  const base = new URL(target);
  if (base.username || base.password || base.search || base.hash || base.pathname !== '/')
    throw new Error('Укажите только корень сайта без ключей, query-параметров и пути.');
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(base.hostname);
  if (base.protocol !== 'https:' && !(local && base.protocol === 'http:'))
    throw new Error('Для внешнего размещения нужен HTTPS.');
  const request = (path, options = {}) => fetch(new URL(path, base), {
    redirect: 'error',
    signal: AbortSignal.timeout(15000),
    ...options,
  });
  const post = (body) => request('/api/auth', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Origin: base.origin },
    body: JSON.stringify(body),
  });

  const health = await request('/api/health');
  const healthStatus = await health.json();
  check(health.ok && healthStatus.ok === true && healthStatus.database === 'postgresql', 'API отвечает из PostgreSQL');
  const config = await request('/api/config');
  const settings = await config.json();
  check(config.ok && settings.devAuth === false, 'Демонстрационный вход выключен');
  check(settings.vkConfigured === true, 'Сервер видит настройки VK');

  const demo = await post({ devUserId: 'deployment-check' });
  check(demo.status === 403 && (await demo.json()).code === 'dev_auth_disabled', 'Публичный демовход запрещён');
  const invalid = await post({ launchParams: `vk_app_id=1&vk_user_id=1&vk_ts=${Math.floor(Date.now() / 1000)}&sign=invalid` });
  check(invalid.status === 401 && (await invalid.json()).code === 'invalid_launch', 'Поддельная подпись VK отклонена');
  check((await request('/api/bootstrap')).status === 401, 'Профиль закрыт без входа');
  const retired = await request('/api/admin/applications');
  check(retired.status === 410 && (await retired.json()).code === 'admin_api_retired', 'Общий HR-ключ выведен из эксплуатации');
  const adminLogin = await request('/admin/login/');
  check(adminLogin.ok && (adminLogin.headers.get('content-type') ?? '').includes('text/html'), 'Персональный кабинет Django доступен');

  const page = await request('/');
  check(page.ok && (page.headers.get('content-type') ?? '').includes('text/html'), 'HTML приложения доступен');
  check(!['deny', 'sameorigin'].includes((page.headers.get('x-frame-options') ?? '').toLowerCase()), 'Нет X-Frame-Options, блокирующего iframe VK');
  check(!page.headers.get('content-security-policy')?.includes('frame-ancestors'), 'Нет CSP frame-ancestors, требующего отдельной проверки для VK');
  const html = await page.text();
  const assets = [...html.matchAll(/(?:src|href)="([^"\s]+\.(?:js|css))"/g)].map(match => match[1]);
  check(assets.length > 0, 'HTML ссылается на собранные JS/CSS');
  for (const path of assets) {
    if (new URL(path, base).origin !== base.origin) throw new Error('Неожиданный внешний JS/CSS');
    const response = await request(path);
    const mime = response.headers.get('content-type') ?? '';
    check(response.ok && /javascript|text\/css/.test(mime), `Ресурс доступен: ${path}`);
    await response.body?.cancel();
  }
  console.log('Размещение проверено. Реальный вход и VK Bridge проверьте открытием приложения внутри VK.');
} catch (error) {
  console.error(`Ошибка проверки: ${error.message}`);
  process.exitCode = 1;
}

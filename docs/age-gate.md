# Регистрация с 18 лет

Профиль регистрируется только с 18 лет. Возраст считается по календарной дате Москвы; ровно в день 18-летия доступ открывается. Дата 29 февраля в невисокосном году достигает очередного возраста 1 марта. Клиент останавливает регистрацию после выбора даты рождения, до отправки профиля. Сервер повторяет проверку и возвращает `age_restricted`. Введённая дата не считается подтверждённой проверкой личности.

## Экран

**Наше знакомство ещё впереди**

«Мне тоже жаль, что пока не получится познакомиться. Практика и регистрация доступны с 18 лет. Возвращайся, когда исполнится 18 — откроем твой путь к делу вместе».

«До встречи!» возвращает к приветствию. «Ошибка в дате рождения?» возвращает к заполненной форме и фокусирует дату; исправление не создаёт постоянный бан. Новый профиль несовершеннолетнего не сохраняется; неудачная попытка изменить дату существующего профиля не заменяет сохранённые данные.

## Иллюстрация

Файл: `public/assets/mascot-sad.png`. Создан встроенным `imagegen` из существующего маскота `public/assets/eb811.png`, с прозрачным фоном. Исходный ассет сохранён без изменений.

Финальный промпт:

> Use case: precise-object-edit. Asset type: transparent mascot illustration for an age-18 registration restriction screen in an existing mobile app. Input image 1 is the exact existing mascot reference sheet, not a layout to preserve. Create ONE single full-body character, no sheet, matching this same red bottle opener mascot precisely: silver metal bottle-opener head with the characteristic double opening, cream round face, glossy red handle body, black arms and legs, cream gloves and cream/red sneakers, softly rendered high-quality 3D plastic and metal. Change only pose and expression: gently sad and wistful, eyes slightly downcast, a small downturned mouth, shoulders relaxed, both gloved hands resting together in front of the handle. Kind and hopeful, not distressed, no tears. Keep all iconic shapes, materials, colors and proportions recognizably identical to the supplied character. Center full body vertically with small transparent padding, entire feet and opener visible. Genuine transparent background/alpha, no checkerboard baked in, no text, no badges, no other objects, no ground plane or colored backdrop. Polished clean edges, no extra limbs.

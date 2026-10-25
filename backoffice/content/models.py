from django.core.exceptions import ValidationError
from django.db import models
GAME_KINDS = [(key, label) for key, label in [('shift', 'Разберись в смене'), ('signal', 'Сигнал → действие'), ('movement', 'Передай движение'), ('lab', 'Лабораторный детектив'), ('delivery', 'Собери и доставь'), ('history', 'История')]]
ASSET_KINDS = [(key, key) for key in ('automation', 'mechanics', 'laboratory', 'warehouse', 'shift', 'general')]

class Named(models.Model):
    id = models.SlugField(primary_key=True, max_length=128, allow_unicode=False)
    title = models.CharField('Название', max_length=200)

    class Meta:
        abstract = True

    def __str__(self):
        return self.title

class SpriteAsset(Named):
    kind = models.CharField('Категория', max_length=30, choices=ASSET_KINDS, default='general')
    width = models.PositiveIntegerField('Ширина в сцене', default=96)
    height = models.PositiveIntegerField('Высота в сцене', default=96)
    pixel_width = models.PositiveIntegerField(default=192, editable=False)
    pixel_height = models.PositiveIntegerField(default=192, editable=False)
    mime_type = models.CharField(max_length=50, default='image/png', editable=False)
    source_path = models.CharField(max_length=300, blank=True, editable=False)
    content = models.BinaryField(blank=True, default=bytes, editable=False)
    digest = models.CharField(max_length=64, blank=True, editable=False)
    active = models.BooleanField('Доступен', default=True)

    class Meta:
        verbose_name = 'Игровой спрайт'
        verbose_name_plural = 'Игровые спрайты'

class SpriteModule(Named):
    kind = models.CharField('Категория', max_length=30, choices=ASSET_KINDS, default='general')
    width = models.PositiveIntegerField('Ширина', default=96)
    height = models.PositiveIntegerField('Высота', default=96)
    slots = models.JSONField('Слоты композиции', default=list)
    active = models.BooleanField('Доступен', default=True)

    class Meta:
        verbose_name = 'Модуль сцены'
        verbose_name_plural = 'Модули сцен'

class GameFamily(Named):
    id = models.CharField(primary_key=True, max_length=20, choices=GAME_KINDS)
    description = models.TextField('Описание', blank=True)
    preview_sprite = models.ForeignKey(SpriteAsset, on_delete=models.PROTECT, null=True, blank=True, verbose_name='Спрайт карточки')
    position = models.PositiveIntegerField('Порядок', default=0)
    active = models.BooleanField('Показывать', default=True)

    class Meta:
        ordering = ('position', 'id')
        verbose_name = 'Семейство игр'
        verbose_name_plural = 'Семейства игр'

class RuleSet(Named):
    game = models.CharField('Механика', max_length=20, choices=GAME_KINDS)
    definition = models.JSONField('Закрытые правила оценки', default=dict)
    notes = models.TextField('Комментарий редактора', blank=True)

    class Meta:
        verbose_name = 'Приватное правило'
        verbose_name_plural = 'Приватные правила оценки'

class LevelDefinition(Named):
    family = models.ForeignKey(GameFamily, on_delete=models.PROTECT, verbose_name='Игра')
    level = models.PositiveIntegerField('Номер уровня', default=1)
    description = models.TextField('Задача')
    direction = models.CharField('Профнаправление', max_length=100)
    points = models.PositiveIntegerField('Баллы за первое прохождение', default=30)
    duration = models.CharField('Ориентировочное время', max_length=60, default='3–5 мин')
    offer_id = models.CharField('ID карьерного предложения', max_length=128, blank=True)
    demo = models.BooleanField('Учебная модель', default=True)
    explanation = models.TextField('Пояснение после прохождения', blank=True)
    career_explanation = models.TextField('Объяснение карьерного перехода', blank=True, default='', help_text='Необязательный текст после успешной игры: как выполненная задача связана с карьерным направлением. Изменение попадёт в мини-приложение после новой публикации.')
    puzzle = models.JSONField('Конструктор задачи', default=dict)
    presentation = models.JSONField('Оформление и роли спрайтов', default=dict)
    rule_set = models.ForeignKey(RuleSet, on_delete=models.PROTECT, null=True, blank=True, verbose_name='Приватная оценка')
    fixtures = models.JSONField('Проверочные решения', default=dict)
    status = models.CharField('Статус', max_length=20, choices=[('draft', 'Черновик'), ('published', 'Опубликован'), ('archived', 'Архив')], default='draft', editable=False)
    published_version = models.PositiveIntegerField(default=0, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('family__position', 'level', 'id')
        verbose_name = 'Игровой уровень'
        verbose_name_plural = 'Конструктор уровней'
        permissions = [('publish_leveldefinition', 'Может проверять и публиковать игровые уровни')]

class LevelVersion(models.Model):
    level = models.ForeignKey(LevelDefinition, on_delete=models.PROTECT, related_name='versions')
    version = models.PositiveIntegerField()
    public_snapshot = models.JSONField()
    private_rule = models.JSONField(null=True, blank=True)
    fixtures = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=('level', 'version'), name='content_level_version_unique')]
        verbose_name = 'Опубликованная версия уровня'
        verbose_name_plural = 'Версии уровней'

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Опубликованный снимок неизменяем. Создайте новую публикацию.')
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.level_id} · v{self.version}'

class LevelObject(models.Model):
    level = models.ForeignKey(LevelDefinition, on_delete=models.CASCADE, related_name='scene_objects', verbose_name='Уровень')
    key = models.SlugField('ID экземпляра', max_length=128)
    sprite = models.ForeignKey(SpriteAsset, on_delete=models.PROTECT, null=True, blank=True, verbose_name='Спрайт')
    module = models.ForeignKey(SpriteModule, on_delete=models.PROTECT, null=True, blank=True, verbose_name='Модуль')
    binding = models.CharField('Роль игрового объекта', max_length=128, blank=True, help_text='Например source, gear, sample:a, batch:a. Пусто — декоративный объект.')
    slot_values = models.JSONField('Спрайты в слотах модуля', default=dict, blank=True)
    x = models.FloatField(default=0)
    y = models.FloatField(default=0)
    width = models.FloatField(default=96)
    height = models.FloatField(default=96)
    rotation = models.FloatField(default=0)
    layer = models.IntegerField(default=0)

    class Meta:
        ordering = ('layer', 'id')
        constraints = [models.UniqueConstraint(fields=('level', 'key'), name='content_object_key_unique')]
        verbose_name = 'Объект сцены'
        verbose_name_plural = 'Объекты сцены'

    def clean(self):
        if bool(self.sprite_id) == bool(self.module_id):
            raise ValidationError('Выберите один спрайт или один модуль.')
        if self.width <= 0 or self.height <= 0 or abs(self.layer) > 100:
            raise ValidationError('Проверьте размеры и слой.')

    def __str__(self):
        return self.key

class CareerOffer(Named):
    direction = models.CharField('Направление', max_length=100)
    type = models.CharField('Тип', max_length=100, default='Практика')
    location = models.CharField('Место', max_length=300)
    schedule = models.CharField('График', max_length=300)
    pay = models.CharField('Оплата', max_length=300, blank=True)
    description = models.TextField('Описание')
    tasks = models.JSONField('Задачи', default=list)
    requirements = models.JSONField('Требования', default=list)
    deadline = models.CharField('Срок отклика', max_length=500, blank=True)
    demo = models.BooleanField('Демонстрационное предложение', default=True)
    published = models.BooleanField('Опубликовано', default=False)
    archived = models.BooleanField('Архив', default=False)

    class Meta:
        verbose_name = 'Карьерное предложение'
        verbose_name_plural = 'Карьерные предложения'

class PointReward(Named):
    description = models.TextField('Описание')
    cost = models.PositiveIntegerField('Стоимость в баллах')
    stock = models.PositiveIntegerField('Всего доступно')
    demo = models.BooleanField('Демонстрационная награда', default=True)
    published = models.BooleanField('Опубликовано', default=False)
    archived = models.BooleanField('Архив', default=False)

    class Meta:
        verbose_name = 'Награда за баллы'
        verbose_name_plural = 'Каталог мерча и наград'

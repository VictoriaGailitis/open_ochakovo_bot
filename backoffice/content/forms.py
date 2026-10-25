import hashlib
import json
from django import forms
from django.core.exceptions import ValidationError
from backoffice.core.models import Material, MaterialMedia
from .models import *
from .widgets import ConstructorWidget
from . import schemas, services
from .validation import require, finite

FIELD_LABELS={'id':'Постоянный ID','title':'Название','description':'Описание','category':'Категория','audience':'Аудитория','published':'Опубликовано','demo':'Учебный пример','archived':'В архиве','filename':'Имя файла','mime_type':'Формат файла','size':'Размер файла','created':'Создано','created_at':'Создано','updated_at':'Изменено','version':'Версия','points':'Баллы','digest':'Контрольная сумма','pixel_width':'Ширина файла, пикс.','pixel_height':'Высота файла, пикс.','x':'Координата X','y':'Координата Y','rotation':'Поворот','layer':'Слой'}

class ContentForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        from unfold.widgets import UnfoldAdminTextInputWidget
        for name,field in self.fields.items():
            if name in FIELD_LABELS:field.label=FIELD_LABELS[name]
            if name in ('id','title','filename') and isinstance(field,forms.CharField):field.widget=UnfoldAdminTextInputWidget(attrs=field.widget.attrs)
            if name=='category':field.choices=[('company','О компании'),('video','Видео'),('practice','Практика'),('stories','Истории сотрудников')]
            if name=='audience':field.choices=[('candidate','Кандидаты'),('staff','Сотрудники'),('all','Все')]

class LevelForm(ContentForm):
    expected_updated = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = LevelDefinition
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        game = self.data.get('family') or getattr(self.instance, 'family_id', None) or self.initial.get('family') or 'signal'
        self.fields['puzzle'].widget = ConstructorWidget(schemas.PUZZLES.get(game, schemas.PUZZLES['signal']))
        self.fields['presentation'].widget = ConstructorWidget(schemas.PRESENTATION)
        self.fields['fixtures'].widget = ConstructorWidget(schemas.obj(positive=schemas.arr(schemas.SOLUTIONS.get(game, schemas.SOLUTIONS['signal'])), negative=schemas.arr(schemas.SOLUTIONS.get(game, schemas.SOLUTIONS['signal']))))
        self.fields['puzzle'].help_text = 'Публичные условия задачи. Для смены механики сначала выберите семейство при создании. Все поля проверяются перед публикацией.'
        self.fields['fixtures'].help_text = 'Нужен хотя бы один решающий пример и один отвергаемый. Они доступны только редакторам и подтверждают решаемость при публикации.'
        if self.instance.pk and LevelDefinition.objects.filter(pk=self.instance.pk).exists():
            self.fields['id'].disabled = True
            self.fields['family'].disabled = True
            self.fields['expected_updated'].initial = self.instance.updated_at.isoformat()

    def clean(self):
        data = super().clean()
        current = LevelDefinition.objects.filter(pk=self.instance.pk).first()
        if current:
            require(data.get('expected_updated') == current.updated_at.isoformat(), 'Черновик уровня изменён в другой вкладке. Обновите страницу.')
        if data.get('points', 0) < 1:
            self.add_error('points', 'От 1 до 1000 баллов.')
        if data.get('presentation'):
            services.validate_presentation(data['presentation'])
        return data

class RuleForm(ContentForm):

    class Meta:
        model = RuleSet
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        game = self.data.get('game') or self.instance.game or self.initial.get('game') or 'history'
        self.fields['definition'].widget = ConstructorWidget(schemas.RULES.get(game, schemas.obj()))
        self.fields['game'].choices = [c for c in GAME_KINDS if c[0] in schemas.RULES]
        self.fields['definition'].help_text = 'Ответы находятся только на сервере. Изменение правила применяется лишь к следующей публикации уровня.'

    def clean(self):
        data = super().clean()
        rule = data.get('definition', {})
        require(isinstance(rule,dict),'Правило должно быть структурой полей.')
        if rule.get('game') != data.get('game'):
            self.add_error('definition', 'Поле game правила должно совпадать с механикой.')
        return data

class ModuleForm(ContentForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        import copy
        schema = copy.deepcopy(schemas.SLOTS)
        schema['items']['properties']['spriteId'] = schemas.enum(*SpriteAsset.objects.filter(active=True).values_list('id', flat=True)) if SpriteAsset.objects.filter(active=True).exists() else schemas.text()
        self.fields['slots'].widget = ConstructorWidget(schema)

    class Meta:
        model = SpriteModule
        fields = '__all__'
        widgets = {'slots': ConstructorWidget(schemas.SLOTS)}

    def clean(self):
        data=super().clean()
        require(all(type(data.get(k)) is int and 1<=data[k]<=4096 for k in ('width','height')),'Размеры модуля: 1–4096.')
        return data

    def clean_slots(self):
        slots = self.cleaned_data['slots']
        require(isinstance(slots, list) and 1 <= len(slots) <= 100, 'Добавьте 1–100 слотов.')
        ids = set()
        for slot in slots:
            require(isinstance(slot, dict) and isinstance(slot.get('id'), str) and slot['id'] and (slot['id'] not in ids), 'ID слотов должны различаться.')
            ids.add(slot['id'])
            require(SpriteAsset.objects.filter(pk=slot.get('spriteId'), active=True).exists(), 'Выберите существующий спрайт.')
            require(all((finite(slot.get(k)) for k in ('x', 'y', 'width', 'height'))) and slot['width'] > 0 and (slot['height'] > 0), 'Проверьте геометрию слота.')
            require(finite(slot.get('rotation', 0)) and type(slot.get('layer', 0)) is int and (abs(slot.get('layer', 0)) <= 100), 'Проверьте слой и поворот.')
            require(isinstance(slot.get('role', ''), str), 'Роль должна быть текстом.')
        return slots

class ObjectForm(ContentForm):

    class Meta:
        model = LevelObject
        fields = '__all__'
        widgets = {'slot_values': ConstructorWidget(schemas.mapping(schemas.text()))}

    def clean(self):
        data = super().clean()
        require(all((finite(data.get(k, 0)) for k in ('x', 'y', 'width', 'height', 'rotation'))), 'Координаты должны быть конечными числами.')
        require(isinstance(data.get('slot_values',{}),dict) and all(isinstance(v,str) for v in data.get('slot_values',{}).values()),'Переопределения слотов: ID слота → ID спрайта.')
        return data

class AssetForm(ContentForm):
    upload = forms.FileField(label='Загрузить спрайт PNG / JPEG / WebP', required=False)

    class Meta:
        model = SpriteAsset
        fields = ('id', 'title', 'kind', 'width', 'height', 'active')

    def clean(self):
        data = super().clean()
        require(all(type(data.get(k)) is int and 1<=data[k]<=4096 for k in ('width','height')),'Размеры спрайта: 1–4096.')
        upload = data.get('upload')
        self.image = None
        if upload:
            self.image = services.image_upload(upload)
        if not self.instance.pk or not SpriteAsset.objects.filter(pk=self.instance.pk).exists():
            require(upload, 'Загрузите файл спрайта.')
        services.ensure_asset_mutable(self.instance, data=self.image[0] if self.image else None, width=data.get('width'), height=data.get('height'), active=data.get('active'))
        return data

    def save(self, commit=True):
        asset = super().save(False)
        if self.image:
            asset.content, asset.mime_type, asset.pixel_width, asset.pixel_height = self.image
            asset.digest = hashlib.sha256(asset.content).hexdigest()
            asset.source_path = ''
        if commit:
            asset.save()
        return asset

class MaterialForm(ContentForm):
    blocks_editor = forms.JSONField(label='Блоки материала', widget=ConstructorWidget(schemas.BLOCKS))
    quiz = forms.JSONField(label='Конструктор теста', required=False, widget=ConstructorWidget(schemas.QUIZ), help_text='Порядок вопросов и вариантов меняется кнопкой «Выше». Правильный ответ — ID варианта. Очистите тест, если награда не нужна.')
    without_quiz = forms.BooleanField(label='Материал без теста', required=False)
    expected_version = forms.IntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Material
        fields = ('id', 'title', 'description', 'category', 'audience', 'published', 'demo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        block_schema = dict(schemas.BLOCKS)
        block_schema['media'] = [{'id': m.pk, 'kind': m.mime_type.split('/')[0]} for m in MaterialMedia.objects.all()]
        self.fields['blocks_editor'].widget = ConstructorWidget(block_schema)
        self.fields['blocks_editor'].help_text = 'Загрузите файл в разделе «Медиа материалов», затем выберите его ID в блоке. Заголовки, текст, изображения и видео можно переставлять кнопкой «Выше».'
        self.fields['blocks_editor'].initial = json.loads(self.instance.blocks) if self.instance.blocks else [{'type': 'text', 'text': ''}]
        if self.instance.pk and Material.objects.filter(pk=self.instance.pk).exists():
            self.fields['id'].disabled = True
            self.fields['expected_version'].initial = self.instance.version
            snapshot = self.instance.materialversion_set.filter(version=self.instance.version).first()
            value = json.loads(snapshot.snapshot) if snapshot else {}
            self.fields['quiz'].initial = value.get('quiz') or {'points': 5, 'questions': []}
            self.fields['without_quiz'].initial = not value.get('quiz')
        else:
            self.fields['quiz'].initial = {'points': 5, 'questions': []}

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        current = Material.objects.filter(pk=self.instance.pk).first()
        if current:
            require(data.get('expected_version') == current.version, 'Материал изменён в другой вкладке. Обновите страницу.')
        body = {k: data[k] for k in ('id', 'title', 'description', 'category', 'audience')}
        body.update(published=bool(data['published']), demo=bool(data['demo']), blocks=data['blocks_editor'], quiz=None if data.get('without_quiz') else data.get('quiz'))
        self.value = services.material_value(body)
        self.expected = data.get('expected_version')
        return data

class MediaForm(ContentForm):
    upload = forms.FileField(label='Изображение или видео (до 50 МБ)', required=True)

    class Meta:
        model = MaterialMedia
        fields = ('id', 'audience')

    def clean(self):
        data = super().clean()
        upload = data.get('upload')
        if not upload:
            return data
        require(0 < upload.size <= 50 * 1024 * 1024, 'Максимум 50 МБ.')
        content = upload.read()
        mime = upload.content_type
        if mime.startswith('image/'):
            upload.seek(0)
            content, mime, _, _ = services.image_upload(upload, 50 * 1024 * 1024)
        else:
            valid = mime == 'video/mp4' and len(content) >= 12 and (content[4:8] == b'ftyp') or (mime == 'video/webm' and content.startswith(b'\x1aE\xdf\xa3'))
            require(valid, 'Разрешены PNG, JPEG, WebP, MP4 и WebM. Содержимое должно соответствовать формату.')
        self.file_content, self.file_mime, self.file_name = (content, mime, upload.name[:200])
        return data

    def save(self, commit=True):
        instance = super().save(False)
        instance.content = self.file_content
        instance.mime_type = self.file_mime
        instance.filename = self.file_name
        instance.size = len(self.file_content)
        if commit:
            instance.save()
        return instance

class OfferForm(ContentForm):

    class Meta:
        model = CareerOffer
        fields = '__all__'
        widgets = {key: ConstructorWidget(schemas.arr(schemas.text())) for key in ('tasks', 'requirements')}

    def clean(self):
        data = super().clean()
        for key in ('tasks', 'requirements'):
            require(isinstance(data.get(key), list) and all((isinstance(x, str) and x.strip() and (len(x) <= 2000) for x in data[key])), 'Задачи и требования должны быть списками текста.')
        return data

class RewardForm(ContentForm):

    class Meta:
        model = PointReward
        fields = '__all__'

    def clean(self):
        data = super().clean()
        require(data.get('cost', 0) > 0, 'Стоимость должна быть положительной.')
        from backoffice.core.models import RewardExchange
        require(data.get('stock', 0) >= RewardExchange.objects.filter(reward=self.instance.pk).count(), 'Всего доступно не может быть меньше числа уже оформленных обменов.')
        return data

#!/usr/bin/env python3
"""Export installed Django ORM/admin metadata, never database records.

Run with .venv/bin/python scripts/export-admin-schema.py. The sole output path is
fixed below; model defaults and callable choices are represented, never invoked.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs' / 'django-models.json'
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backoffice.settings')


def reference(value):
    module = getattr(value, '__module__', type(value).__module__)
    name = getattr(value, '__qualname__', getattr(value, '__name__', type(value).__qualname__))
    return module + '.' + name


def schema_value(value):
    """Serialize declarations only, without evaluating expressions or factories."""
    from django.db.models.fields import NOT_PROVIDED
    from django.utils.choices import CallableChoiceIterator

    if value is NOT_PROVIDED:
        return {'kind': 'not_provided'}
    if value is None or type(value) in (str, int, float, bool):
        return value
    if isinstance(value, bytes):
        return {'kind': 'binary_literal', 'length': len(value)}
    if isinstance(value, CallableChoiceIterator):
        return {'kind': 'callable_choices', 'reference': reference(value.func), 'executed': False}
    if isinstance(value, dict):
        return {str(key): schema_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [schema_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((schema_value(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    if callable(value):
        return {'kind': 'callable_reference', 'reference': reference(value), 'executed': False}
    if hasattr(value, 'deconstruct'):
        return {'kind': 'deconstruct', 'definition': schema_value(value.deconstruct())}
    return {'kind': 'object', 'type': reference(type(value))}


def reject_sql(execute, sql, params, many, context):
    raise RuntimeError('Schema export must not execute SQL or read database rows.')


def export_schema():
    import django
    from django.db import connection

    # Also guard app/admin initialization: future AppConfig changes must not turn
    # a schema export into a database query or silently include live records.
    with connection.execute_wrapper(reject_sql):
        django.setup()
        from django.apps import apps
        from django.contrib import admin

        models = []
        for model in sorted(apps.get_models(include_auto_created=True), key=lambda item: item._meta.label_lower):
            meta = model._meta
            registered = admin.site._registry.get(model)
            fields, relationships = [], []
            for field in meta.local_fields:
                item = {
                    'name': field.name,
                    'column': field.column,
                    'type': field.get_internal_type(),
                    'primaryKey': field.primary_key,
                    'null': field.null,
                    'blank': field.blank,
                    'unique': field.unique,
                    'indexed': field.db_index,
                    'editable': field.editable,
                    'autoCreated': bool(field.auto_created),
                    'default': schema_value(field.default),
                    'dbDefault': schema_value(field.db_default),
                    'validators': schema_value(field.validators),
                }
                if field.max_length is not None:
                    item['maxLength'] = field.max_length
                if field.choices is not None:
                    item['choices'] = schema_value(field.choices)
                for attr in ('max_digits', 'decimal_places', 'auto_now', 'auto_now_add', 'db_collation'):
                    if hasattr(field, attr):
                        item[attr] = schema_value(getattr(field, attr))
                if field.is_relation:
                    relation = {
                        'field': field.name,
                        'column': field.column,
                        'targetModel': field.related_model._meta.label_lower,
                        'targetTable': field.related_model._meta.db_table,
                        'targetField': field.target_field.name,
                        'targetColumn': field.target_field.column,
                        'onDelete': reference(field.remote_field.on_delete),
                        'relatedName': field.remote_field.related_name,
                        'dbConstraint': field.db_constraint,
                        'oneToOne': field.one_to_one,
                        'manyToOne': field.many_to_one,
                    }
                    item['relationship'] = relation
                    relationships.append(relation)
                fields.append(item)
            for field in meta.local_many_to_many:
                relationships.append({
                    'field': field.name,
                    'manyToMany': True,
                    'targetModel': field.related_model._meta.label_lower,
                    'throughModel': field.remote_field.through._meta.label_lower,
                    'throughTable': field.remote_field.through._meta.db_table,
                    'throughFields': schema_value(field.remote_field.through_fields),
                    'symmetrical': field.remote_field.symmetrical,
                    'relatedName': field.remote_field.related_name,
                })
            entry = {
                'model': meta.label,
                'modelKey': meta.label_lower,
                'app': meta.app_label,
                'table': meta.db_table,
                'managed': meta.managed,
                'proxy': meta.proxy,
                'autoCreated': bool(meta.auto_created),
                'fields': fields,
                'relationships': relationships,
                'constraints': schema_value(meta.constraints),
                'uniqueTogether': schema_value(meta.unique_together),
                'indexes': schema_value(meta.indexes),
                'ordering': schema_value(meta.ordering),
                'defaultPermissions': list(meta.default_permissions),
                'customPermissions': schema_value(meta.permissions),
                'admin': {'registered': registered is not None},
            }
            if registered:
                entry['admin'].update({
                    'class': reference(type(registered)),
                    'framework': 'Unfold' if any(cls.__module__.startswith('unfold') for cls in type(registered).__mro__) else 'Django',
                    'formClass': reference(registered.form),
                    'listDisplay': schema_value(registered.list_display),
                    'listDisplayMethod': reference(type(registered).get_list_display),
                    'listFilter': schema_value(registered.list_filter),
                    'searchFields': schema_value(registered.search_fields),
                    'readonlyFields': schema_value(registered.readonly_fields),
                    'dynamicReadonlyFields': type(registered).get_readonly_fields is not admin.ModelAdmin.get_readonly_fields,
                    'fields': schema_value(registered.fields),
                    'fieldsets': schema_value(registered.fieldsets),
                    'actions': schema_value(registered.actions),
                    'inlines': [{
                        'class': reference(cls),
                        'model': cls.model._meta.label_lower,
                        'fields': schema_value(cls.fields),
                        'readonlyFields': schema_value(cls.readonly_fields),
                    } for cls in registered.inlines],
                    'permissionMethods': {
                        name: reference(getattr(type(registered), name))
                        for name in ('has_view_permission', 'has_add_permission', 'has_change_permission', 'has_delete_permission')
                    },
                })
            models.append(entry)
        return {
            'manifestVersion': 1,
            'status': 'implemented',
            'kind': 'Django ORM metadata only',
            'backend': 'PostgreSQL',
            'adminFramework': 'Django Unfold',
            'scope': 'All installed ORM models including Django auth/admin/session/contenttypes and auto-created M2M tables; django_migrations is framework storage, not an ORM model.',
            'safety': {
                'databaseQueries': 0,
                'dataRowsIncluded': False,
                'defaultCallablesExecuted': False,
                'privateRulesAnswersTokensIncluded': False,
                'callables': 'Symbolic references only; never invoked.',
            },
            'generator': 'scripts/export-admin-schema.py',
            'sources': [
                'backoffice/core/models.py', 'backoffice/content/models.py', 'backoffice/operations/models.py',
                'backoffice/content/admin.py', 'backoffice/operations/admin.py', 'backoffice/settings.py',
            ],
            'counts': {
                'models': len(models),
                'tables': len({model['table'] for model in models if not model['proxy']}),
                'registeredModels': sum(model['admin']['registered'] for model in models),
                'fields': sum(len(model['fields']) for model in models),
            },
            'models': models,
        }


def main():
    if len(sys.argv) != 1:
        raise SystemExit('Usage: .venv/bin/python scripts/export-admin-schema.py (fixed docs/django-models.json output)')
    if OUTPUT.is_symlink() or not OUTPUT.parent.resolve().is_relative_to(ROOT):
        raise SystemExit('Refusing a manifest path outside the repository or a symlink target.')
    manifest = export_schema()
    OUTPUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Exported docs/django-models.json: ' + json.dumps(manifest['counts']))


if __name__ == '__main__':
    main()

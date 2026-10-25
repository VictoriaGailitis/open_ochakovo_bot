from django.core.management.base import BaseCommand
from backoffice.content.seed import seed_content
class Command(BaseCommand):
    help='Импортирует начальный контент без перезаписи редакторских изменений.'
    def handle(self,*args,**options):self.stdout.write(str(seed_content()))

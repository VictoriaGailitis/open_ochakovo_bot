"""Run the Django/PostgreSQL API and Unfold administration server."""
import argparse
import os
from django.core.management import execute_from_command_line


def main():
    parser=argparse.ArgumentParser(description='Очаково: Django API и Unfold admin (PostgreSQL)')
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=3001)
    args=parser.parse_args()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','backoffice.settings')
    execute_from_command_line(['manage.py','runserver',f'{args.host}:{args.port}','--noreload'])


if __name__=='__main__':main()

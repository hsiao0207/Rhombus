"""
Delete datasets older than DATASET_RETENTION_HOURS, with their versions and files.

docker-compose runs it every hour in the `cleanup` service, so storage on the server
stays bounded and uploaded data is not kept longer than needed.

    uv run python manage.py cleanup_datasets              # use DATASET_RETENTION_HOURS
    uv run python manage.py cleanup_datasets --hours 1    # anything older than an hour
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand

from datasets.services import dataset_service


class Command(BaseCommand):
    help = "Delete datasets older than the retention period, with their files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=float,
            default=settings.DATASET_RETENTION_HOURS,
            help="Delete datasets uploaded more than this many hours ago.",
        )

    def handle(self, *args, hours, **options):
        datasets, leftovers = dataset_service.delete_expired_datasets(
            older_than=timedelta(hours=hours)
        )
        self.stdout.write(
            f"Deleted {datasets} dataset(s) older than {hours:g} h "
            f"and {leftovers} leftover folder(s)."
        )

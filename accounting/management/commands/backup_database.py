import os
import sys
import subprocess
import tempfile
from datetime import datetime

from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Backup the PostgreSQL database using pg_dump"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=os.path.join(settings.BASE_DIR, "backups"),
            help="Directory to store backup files",
        )

    def handle(self, *args, **options):
        output_dir = options["output_dir"]
        os.makedirs(output_dir, exist_ok=True)

        db_settings = settings.DATABASES["default"]
        db_name = db_settings["NAME"]
        db_host = db_settings.get("HOST", "localhost")
        db_port = db_settings.get("PORT", "5432")
        db_user = db_settings.get("USER", "")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"paroll_backup_{timestamp}.sql.gz"
        output_path = os.path.join(output_dir, filename)

        env = os.environ.copy()
        if "PASSWORD" in db_settings:
            env["PGPASSWORD"] = db_settings["PASSWORD"]

        cmd = [
            "pg_dump",
            "-h", db_host,
            "-p", str(db_port),
        ]
        if db_user:
            cmd.extend(["-U", db_user])
        cmd.extend(["-F", "c", db_name])

        try:
            with open(output_path, "wb") as f:
                result = subprocess.run(
                    cmd, env=env, stdout=f, stderr=subprocess.PIPE, timeout=600
                )
            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS(f"Backup created: {output_path}"))
                self._cleanup_old_backups(output_dir, keep=14)
            else:
                self.stderr.write(f"pg_dump failed: {result.stderr.decode()}")
                sys.exit(1)
        except FileNotFoundError:
            self.stderr.write("pg_dump not found. Install PostgreSQL client tools.")
            sys.exit(1)
        except subprocess.TimeoutExpired:
            self.stderr.write("Backup timed out after 10 minutes.")
            sys.exit(1)

    def _cleanup_old_backups(self, directory, keep=14):
        files = sorted(
            [f for f in os.listdir(directory) if f.endswith(".sql.gz")],
            reverse=True,
        )
        for f in files[keep:]:
            os.remove(os.path.join(directory, f))
            self.stdout.write(f"Removed old backup: {f}")

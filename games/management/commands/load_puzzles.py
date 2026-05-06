import csv
import io

import requests
from django.core.management import BaseCommand
import zstandard as zstd

from games.models import Puzzle


class Command(BaseCommand):
    help = "Descarga puzles de Lichess online y los guarda en BBDD"

    # De aquí se sacan los puzles
    LICHESS_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10000, help="Limite de puzles a importar")

    def handle(self, *args, **options):
        limit = options["limit"]

        self.stdout.write(self.style.WARNING("Limpiando la tabla de puzles actual..."))
        Puzzle.objects.all().delete()

        puzzles_to_create = []
        count = 0

        self.stdout.write(self.style.SUCCESS(f"Conectando a Lichess"))

        try:
            response = requests.get(self.LICHESS_URL)
            response.raise_for_status()

            decompressor = zstd.ZstdDecompressor()

            stream_reader = decompressor.stream_reader(response.raw)
            text_stream = io.TextIOWrapper(stream_reader, encoding="UTF-8")

            csv_reader = csv.DictReader(text_stream)

            for row in csv_reader:
                if count >= limit:
                    break

                puzzles_to_create.append(
                    Puzzle(
                        lichess_id=row["PuzzleId"],
                        fen=row["FEN"],
                        moves=row["Moves"],
                        rating=int(row["Rating"]),
                        themes=row["Themes"]
                    )
                )
                count += 1

            self.stdout.write(self.style.WARNING(f"Insertando {count} puzles"))

            Puzzle.objects.bulk_create(puzzles_to_create, batch_size=2000)
            self.stdout.write(self.style.SUCCESS(f"Se han importado {count} puzles"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error importando puzles: {str(e)}"))
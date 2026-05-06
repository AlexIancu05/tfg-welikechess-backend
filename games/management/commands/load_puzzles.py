import csv
import io
import requests
from django.core.management import BaseCommand
import zstandard as zstd
from games.models import Puzzle


class Command(BaseCommand):
    help = "Descarga puzles de Lichess en streaming y los guarda en BBDD"

    LICHESS_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=10000,
            help="Límite de puzles a importar"
        )

    def handle(self, *args, **options):
        limit = options["limit"]

        self.stdout.write(self.style.WARNING("Limpiando la tabla de puzles actual..."))
        Puzzle.objects.all().delete()

        self.stdout.write(self.style.SUCCESS(f"Conectando a Lichess (streaming)..."))

        puzzles_to_create = []
        count = 0

        try:
            # stream=True descarga chunk a chunk, nunca carga el fichero entero
            with requests.get(self.LICHESS_URL, stream=True, timeout=30) as response:
                response.raise_for_status()

                dctx = zstd.ZstdDecompressor()

                # stream_reader descomprime sobre la red directamente
                with dctx.stream_reader(response.raw) as stream_reader:
                    text_stream = io.TextIOWrapper(stream_reader, encoding="utf-8")
                    reader = csv.DictReader(text_stream)

                    for row in reader:
                        if count >= limit:
                            break

                        puzzles_to_create.append(
                            Puzzle(
                                lichess_id=row["PuzzleId"],
                                fen=row["FEN"],
                                moves=row["Moves"],
                                rating=int(row["Rating"]),
                                themes=row["Themes"],
                            )
                        )
                        count += 1

                        if count % 5000 == 0:
                            self.stdout.write(f"  → {count} puzles leídos...")

            self.stdout.write(self.style.WARNING(f"Insertando {count} puzles en BBDD..."))
            Puzzle.objects.bulk_create(puzzles_to_create, batch_size=2000)
            self.stdout.write(self.style.SUCCESS(f"✓ {count} puzles importados correctamente."))

        except KeyboardInterrupt:
            self.stdout.write(self.style.ERROR("\nInterrumpido. Insertando lo descargado hasta ahora..."))
            if puzzles_to_create:
                Puzzle.objects.bulk_create(puzzles_to_create, batch_size=2000)
                self.stdout.write(self.style.SUCCESS(f"✓ {len(puzzles_to_create)} puzles guardados."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
import openpyxl
from django.core.management.base import BaseCommand, CommandError
from surveys.models import Municipio, Ubicacion, UbicacionListFile

class Command(BaseCommand):
    help = 'Loads ubicacion data from an uploaded Excel (.xlsx) file into the Municipio and Ubicacion models.'

    def add_arguments(self, parser):
        parser.add_argument('ubicacion_list_file_id', type=int,
                            help='The ID of the UbicacionListFile instance to load.')
        parser.add_argument('--municipio_column', type=str, default='MUNICIPIO',
                            help='The name of the column for the Municipio name.')
        parser.add_argument('--code_column', type=str, default='CODIGO',
                            help='The name of the column for the Ubicacion code.')
        parser.add_argument('--name_column', type=str, default='NOMBRE',
                            help='The name of the column for the Ubicacion name.')
        parser.add_argument('--loc_column', type=str, default='LOC',
                            help='The name of the column for the Ubicacion LOC.')
        parser.add_argument('--zona_column', type=str, default='ZONA',
                            help='The name of the column for the Ubicacion ZONA.')

    def handle(self, *args, **options):
        ubicacion_list_file_id = options['ubicacion_list_file_id']
        municipio_column = options['municipio_column']
        code_column = options['code_column']
        name_column = options['name_column']
        loc_column = options['loc_column']
        zona_column = options['zona_column']

        try:
            ubicacion_list_file_instance = UbicacionListFile.objects.get(pk=ubicacion_list_file_id)
        except UbicacionListFile.DoesNotExist:
            raise CommandError(f'UbicacionListFile with ID {ubicacion_list_file_id} does not exist.')

        self.stdout.write(self.style.SUCCESS(f'Loading data from {ubicacion_list_file_instance.name}...'))

        try:
            workbook = openpyxl.load_workbook(ubicacion_list_file_instance.file.path)
            sheet = workbook.active
        except Exception as e:
            raise CommandError(f'Error reading Excel file: {e}')

        header = [cell.value for cell in sheet[1]]
        try:
            municipio_col_idx = header.index(municipio_column)
            code_col_idx = header.index(code_column)
            name_col_idx = header.index(name_column)
            loc_col_idx = header.index(loc_column)
            zona_col_idx = header.index(zona_column)
        except ValueError as e:
            raise CommandError(f'Column not found in Excel file: {e}. Available columns: {", ".join(header)}')

        created_count = 0
        updated_count = 0

        for row_idx in range(2, sheet.max_row + 1):
            row_values = [cell.value for cell in sheet[row_idx]]
            
            municipio_name = row_values[municipio_col_idx]
            ubicacion_code = row_values[code_col_idx]
            ubicacion_name = row_values[name_col_idx]
            ubicacion_loc = row_values[loc_col_idx]
            ubicacion_zona = row_values[zona_col_idx]

            if not all([municipio_name, ubicacion_code, ubicacion_name, ubicacion_loc]):
                self.stdout.write(self.style.WARNING(f'Skipping row {row_idx} due to missing data in required columns.'))
                continue

            municipio, _ = Municipio.objects.get_or_create(nombre=municipio_name)

            ubicacion, created = Ubicacion.objects.update_or_create(
                municipio=municipio,
                codigo=ubicacion_code,
                defaults={
                    'nombre': ubicacion_name,
                    'loc': ubicacion_loc,
                    'zona': ubicacion_zona or '',
                }
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Successfully loaded ubicacion data. Created {created_count} ubicaciones, updated {updated_count} ubicaciones.'
        ))

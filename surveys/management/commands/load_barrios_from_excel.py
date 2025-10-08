import openpyxl
from django.core.management.base import BaseCommand, CommandError
from surveys.models import Barrio, BarrioListFile

class Command(BaseCommand):
    help = 'Loads barrio data from an uploaded Excel (.xlsx) file into the Barrio model.'

    def add_arguments(self, parser):
        parser.add_argument('barrio_list_file_id', type=int,
                            help='The ID of the BarrioListFile instance to load.')
        parser.add_argument('--code_column', type=str, default='CODIGO',
                            help='The name of the column in the Excel file to use for the Barrio code.')
        parser.add_argument('--name_column', type=str, default='NOMBRE',
                            help='The name of the column in the Excel file to use for the Barrio name.')

    def handle(self, *args, **options):
        barrio_list_file_id = options['barrio_list_file_id']
        code_column = options['code_column']
        name_column = options['name_column']

        try:
            barrio_list_file_instance = BarrioListFile.objects.get(pk=barrio_list_file_id)
        except BarrioListFile.DoesNotExist:
            raise CommandError(f'BarrioListFile with ID {barrio_list_file_id} does not exist.')

        self.stdout.write(self.style.SUCCESS(f'Loading data from {barrio_list_file_instance.name}...'))

        try:
            # Open the Excel file
            workbook = openpyxl.load_workbook(barrio_list_file_instance.file.path)
            sheet = workbook.active # Get the active sheet
        except Exception as e:
            raise CommandError(f'Error reading Excel file: {e}')

        # Find column indices
        header = [cell.value for cell in sheet[1]] # Assuming first row is header
        try:
            code_col_idx = header.index(code_column)
            name_col_idx = header.index(name_column)
        except ValueError as e:
            raise CommandError(f'Column not found in Excel file: {e}. Available columns: {", ".join(header)}')

        created_count = 0
        updated_count = 0

        # Iterate over rows, skipping the header
        for row_idx in range(2, sheet.max_row + 1):
            row_values = [cell.value for cell in sheet[row_idx]]
            
            barrio_code = row_values[code_col_idx]
            barrio_name = row_values[name_col_idx]

            if not barrio_code or not barrio_name:
                self.stdout.write(self.style.WARNING(
                    f'Skipping row {row_idx} due to missing code or name. Code: {barrio_code}, Name: {barrio_name}'
                ))
                continue

            barrio, created = Barrio.objects.update_or_create(
                code=barrio_code,
                defaults={
                    'name': barrio_name,
                }
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created Barrio: {barrio.name} ({barrio.code})'))
            else:
                updated_count += 1
                self.stdout.write(self.style.SUCCESS(f'Updated Barrio: {barrio.name} ({barrio.code})'))

        self.stdout.write(self.style.SUCCESS(
            f'Successfully loaded barrio data. Created {created_count} barrios, updated {updated_count} barrios.'
        ))

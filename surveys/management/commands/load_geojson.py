import json
from django.core.management.base import BaseCommand, CommandError
from surveys.models import GeoJSONFile, Barrio

class Command(BaseCommand):
    help = 'Loads GeoJSON data from an uploaded GeoJSONFile into the Barrio model.'

    def add_arguments(self, parser):
        parser.add_argument('geojson_file_id', type=int,
                            help='The ID of the GeoJSONFile instance to load.')
        parser.add_argument('--name_property', type=str, default='NOMBRE',
                            help='The name of the property in GeoJSON features to use for the Barrio name.')
        parser.add_argument('--code_property', type=str, default='CODIGO',
                            help='The name of the property in GeoJSON features to use for the Barrio code.')

    def handle(self, *args, **options):
        geojson_file_id = options['geojson_file_id']
        name_property = options['name_property']
        code_property = options['code_property']

        try:
            geojson_file_instance = GeoJSONFile.objects.get(pk=geojson_file_id)
        except GeoJSONFile.DoesNotExist:
            raise CommandError(f'GeoJSONFile with ID {geojson_file_id} does not exist.')

        self.stdout.write(self.style.SUCCESS(f'Loading data from {geojson_file_instance.name}...'))

        try:
            with geojson_file_instance.file.open('r') as f:
                geojson_data = json.load(f)
        except json.JSONDecodeError:
            raise CommandError(f'Invalid GeoJSON file: {geojson_file_instance.file.name}')
        except Exception as e:
            raise CommandError(f'Error reading GeoJSON file: {e}')

        if geojson_data.get('type') != 'FeatureCollection':
            raise CommandError('GeoJSON file must be a FeatureCollection.')

        features = geojson_data.get('features', [])
        if not features:
            self.stdout.write(self.style.WARNING('No features found in the GeoJSON file.'))
            return

        created_count = 0
        updated_count = 0

        for feature in features:
            properties = feature.get('properties', {})
            geometry = feature.get('geometry', {})

            barrio_name = properties.get(name_property)
            barrio_code = properties.get(code_property)

            if not barrio_name:
                self.stdout.write(self.style.WARNING(
                    f'Skipping feature with no "{name_property}" property: {properties}'
                ))
                continue

            barrio, created = Barrio.objects.update_or_create(
                name=barrio_name,
                defaults={
                    'geometry': geometry,
                    'code': barrio_code,
                }
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created Barrio: {barrio.name}'))
            else:
                updated_count += 1
                self.stdout.write(self.style.SUCCESS(f'Updated Barrio: {barrio.name}'))

        self.stdout.write(self.style.SUCCESS(
            f'Successfully loaded GeoJSON data. Created {created_count} barrios, updated {updated_count} barrios.'
        ))

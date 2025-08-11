# Generated manually to fix migration dependency issue

from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Ontology',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type', models.PositiveSmallIntegerField(choices=[(1, 'HP'), (2, 'MONDO'), (3, 'ONCOTREE')])),
                ('label', models.CharField(max_length=100)),
                ('active', models.BooleanField(default=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Ontology',
                'verbose_name_plural': 'Ontologies',
            },
        ),
        migrations.CreateModel(
            name='Term',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identifier', models.CharField(db_index=True, max_length=25)),
                ('label', models.CharField(db_index=True, max_length=255)),
                ('description', models.TextField(blank=True)),
                ('alternate_ids', models.CharField(blank=True, max_length=2500, validators=[django.core.validators.validate_comma_separated_integer_list])),
                ('created_by', models.CharField(blank=True, max_length=50, null=True)),
                ('created', models.CharField(blank=True, max_length=25, null=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('ontology', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='ontologies.ontology')),
            ],
            options={
                'verbose_name': 'Term',
                'verbose_name_plural': 'Terms',
                'indexes': [models.Index(fields=['ontology', 'identifier'], name='ontologies_te_ontolog_8b8c8c_idx')],
            },
        ),
        migrations.CreateModel(
            name='Synonym',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('description', models.TextField(blank=True)),
                ('scope', models.PositiveSmallIntegerField(blank=True, choices=[(1, 'EXACT'), (2, 'BROAD'), (3, 'NARROW'), (4, 'RELATED'), (5, 'ABBREVATION')], null=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('term', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='synonyms', to='ontologies.term')),
            ],
            options={
                'verbose_name': 'Synonym',
                'verbose_name_plural': 'Synonyms',
            },
        ),
        migrations.CreateModel(
            name='CrossReference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.CharField(db_index=True, max_length=25)),
                ('source_value', models.CharField(max_length=255)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('term', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='xrefs', to='ontologies.term')),
            ],
            options={
                'verbose_name': 'Cross Reference',
                'verbose_name_plural': 'Cross References',
            },
        ),
        migrations.CreateModel(
            name='RelationshipType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('label', models.CharField(max_length=50, unique=True)),
                ('description', models.CharField(blank=True, max_length=255)),
                ('slug', models.SlugField(unique=True)),
                ('active', models.BooleanField(default=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Relationship Type',
                'verbose_name_plural': 'Relationship Types',
            },
        ),
        migrations.CreateModel(
            name='Relationship',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('modified', models.DateTimeField(auto_now=True)),
                ('related_term', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relationships_related', to='ontologies.term')),
                ('term', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relationships', to='ontologies.term')),
                ('type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='relationships', to='ontologies.relationshiptype')),
            ],
            options={
                'verbose_name': 'Relationship',
                'verbose_name_plural': 'Relationships',
            },
        ),
    ]

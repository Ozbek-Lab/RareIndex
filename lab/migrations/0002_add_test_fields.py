from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lab', '0001_initial'),  # Make sure this matches your last migration
    ]

    operations = [
        migrations.AddField(
            model_name='test',
            name='council_date',
            field=models.DateField(blank=True, null=True, verbose_name='Council Date'),
        ),
        migrations.AddField(
            model_name='test',
            name='service_send_date',
            field=models.DateField(blank=True, null=True, verbose_name='Service Send Date'),
        ),
        migrations.AddField(
            model_name='test',
            name='data_receipt_date',
            field=models.DateField(blank=True, null=True, verbose_name='Data Receipt Date'),
        ),
    ] 
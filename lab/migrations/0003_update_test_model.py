from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('lab', '0002_add_test_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='test',
            name='test_type',
            field=models.CharField(max_length=100),
        ),
        migrations.AlterField(
            model_name='test',
            name='performed_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='test',
            name='performed_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tests_performed', to='auth.user'),
        ),
        migrations.AlterField(
            model_name='test',
            name='sample',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tests', to='lab.sample'),
        ),
        migrations.AlterField(
            model_name='test',
            name='created_by',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tests_created', to='auth.user'),
        ),
        migrations.AddField(
            model_name='test',
            name='updated_at',
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterModelOptions(
            name='test',
            options={'ordering': ['-created_at']},
        ),
    ] 
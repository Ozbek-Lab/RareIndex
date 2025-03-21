from django.db import migrations, models
import django.db.models.deletion

def create_test_types(apps, schema_editor):
    TestType = apps.get_model('lab', 'TestType')
    User = apps.get_model('auth', 'User')
    
    # Get the first superuser
    admin_user = User.objects.filter(is_superuser=True).first()
    if not admin_user:
        admin_user = User.objects.create_superuser('admin', 'admin@example.com', 'admin')
    
    # Create test types
    test_types = {
        'WGS': 'Whole Genome Sequencing',
        'WES': 'Whole Exome Sequencing',
        'RNA-Seq': 'RNA Sequencing',
        'Panel': 'Gene Panel Sequencing'
    }
    
    for name, description in test_types.items():
        TestType.objects.get_or_create(
            name=name,
            defaults={
                'description': description,
                'created_by': admin_user
            }
        )

def update_test_types(apps, schema_editor):
    Test = apps.get_model('lab', 'Test')
    TestType = apps.get_model('lab', 'TestType')
    
    # Get all test types
    test_types = {tt.name: tt for tt in TestType.objects.all()}
    
    # Update all tests
    for test in Test.objects.all():
        old_type = test.test_type_old
        if old_type in test_types:
            test.test_type = test_types[old_type]
            test.save()

class Migration(migrations.Migration):

    dependencies = [
        ('lab', '0011_remove_sample_council_date_and_more'),
    ]

    operations = [
        # First create the new field without any constraints
        migrations.AddField(
            model_name='test',
            name='test_type_old',
            field=models.CharField(max_length=100, null=True),
        ),
        
        # Copy data to the new field
        migrations.RunSQL(
            "UPDATE lab_test SET test_type_old = test_type",
            reverse_sql="UPDATE lab_test SET test_type = test_type_old",
        ),
        
        # Create test types
        migrations.RunPython(create_test_types),
        
        # Add the new ForeignKey field
        migrations.AddField(
            model_name='test',
            name='test_type',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='lab.testtype'),
        ),
        
        # Update the data
        migrations.RunPython(update_test_types),
        
        # Make the field required
        migrations.AlterField(
            model_name='test',
            name='test_type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='lab.testtype'),
        ),
        
        # Remove the old field
        migrations.RemoveField(
            model_name='test',
            name='test_type_old',
        ),
    ] 
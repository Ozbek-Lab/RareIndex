# forms.py
from django import forms
from . import models

class IndividualForm(forms.ModelForm):
    class Meta:
        model = models.Individual
        fields = [
            'lab_id', 
            'biobank_id', 
            'full_name', 
            'tc_identity', 
            'birth_date',
            'icd11_code',
            'hpo_codes',
            'family'
        ]
        widgets = {
            'birth_date': forms.DateInput(attrs={'type': 'date'}),
            'hpo_codes': forms.Textarea(attrs={'rows': 3}),
        }

class SampleForm(forms.ModelForm):
    class Meta:
        model = models.Sample
        fields = [
            'individual', 
            'sample_type', 
            'receipt_date', 
            'processing_date',
            'service_send_date', 
            'data_receipt_date', 
            'council_date',
            'isolation_by',
            'sample_measurements', 
            'status'
        ]
        widgets = {
            'receipt_date': forms.DateInput(attrs={'type': 'date'}),
            'processing_date': forms.DateInput(attrs={'type': 'date'}),
            'service_send_date': forms.DateInput(attrs={'type': 'date'}),
            'data_receipt_date': forms.DateInput(attrs={'type': 'date'}),
            'council_date': forms.DateInput(attrs={'type': 'date'}),
        }

class NoteForm(forms.ModelForm):
    class Meta:
        model = models.Note
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3}),
        }

class TestForm(forms.ModelForm):
    class Meta:
        model = models.Test
        fields = ['name', 'description']

class SampleTypeForm(forms.ModelForm):
    class Meta:
        model = models.SampleType
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
            })
        }
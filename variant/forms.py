from django import forms
from .models import Variant, SNV, CNV, SV, Repeat
from lab.models import Individual, Test, Analysis

class VariantContextForm(forms.Form):
    individual = forms.ModelChoiceField(
        queryset=Individual.objects.all(),
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:focus:ring-blue-400 dark:focus:border-blue-400 transition-colors duration-200',
            'hx-trigger': 'change',
            'name': 'individual'
        })
    )
    test = forms.ModelChoiceField(
        queryset=Test.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:focus:ring-blue-400 dark:focus:border-blue-400 transition-colors duration-200',
            'hx-trigger': 'change',
            'name': 'test'
        })
    )
    analysis = forms.ModelChoiceField(
        queryset=Analysis.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:focus:ring-blue-400 dark:focus:border-blue-400 transition-colors duration-200',
            'name': 'analysis'
        })
    )
    variant_type = forms.ChoiceField(
        choices=[
            ('snv', 'SNV'),
            ('cnv', 'CNV'),
            ('sv', 'SV'),
            ('repeat', 'Repeat'),
        ],
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:focus:ring-blue-400 dark:focus:border-blue-400 transition-colors duration-200'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Logic to filter querysets based on data
        data = kwargs.get('data') or {}
        
        if 'individual' in data:
            try:
                individual_id = int(data.get('individual'))
                self.fields['test'].queryset = Test.objects.filter(sample__individual_id=individual_id)
            except (ValueError, TypeError):
                pass
        
        if 'test' in data:
            try:
                test_id = int(data.get('test'))
                self.fields['analysis'].queryset = Analysis.objects.filter(test_id=test_id)
            except (ValueError, TypeError):
                pass

class BaseVariantForm(forms.ModelForm):
    class Meta:
        exclude = ['created_by', 'created_at', 'analysis', 'individual']
        widgets = {
            'chromosome': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'start': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'end': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'assembly_version': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
        }

class SNVForm(BaseVariantForm):
    class Meta(BaseVariantForm.Meta):
        model = SNV
        fields = ['assembly_version', 'chromosome', 'start', 'end', 'reference', 'alternate']
        widgets = {
            **BaseVariantForm.Meta.widgets,
            'reference': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'alternate': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
        }

class CNVForm(BaseVariantForm):
    class Meta(BaseVariantForm.Meta):
        model = CNV
        fields = ['assembly_version', 'chromosome', 'start', 'end', 'cnv_type', 'copy_number']
        widgets = {
            **BaseVariantForm.Meta.widgets,
            'cnv_type': forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'copy_number': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
        }

class SVForm(BaseVariantForm):
    class Meta(BaseVariantForm.Meta):
        model = SV
        fields = ['assembly_version', 'chromosome', 'start', 'end', 'sv_type', 'breakpoints']
        widgets = {
            **BaseVariantForm.Meta.widgets,
            'sv_type': forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'breakpoints': forms.Textarea(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm', 'rows': 3}),
        }

class RepeatForm(BaseVariantForm):
    class Meta(BaseVariantForm.Meta):
        model = Repeat
        fields = ['assembly_version', 'chromosome', 'start', 'end', 'repeat_unit', 'repeat_count']
        widgets = {
            **BaseVariantForm.Meta.widgets,
            'repeat_unit': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'repeat_count': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
        }

class VariantUpdateForm(forms.ModelForm):
    class Meta:
        model = Variant
        fields = ['analysis'] # We only want to update analysis for now
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter analysis based on individual if possible, or show all
        if self.instance and self.instance.individual:
            # Show analyses for the same individual
            self.fields['analysis'].queryset = Analysis.objects.filter(
                test__sample__individual=self.instance.individual
            )
        
        self.fields['analysis'].widget.attrs.update({
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
        })

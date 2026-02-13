from django import forms
from .models import Variant, SNV, CNV, SV, Repeat
from lab.models import Individual, Test, Pipeline

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
    pipeline = forms.ModelChoiceField(
        queryset=Pipeline.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 dark:focus:ring-blue-400 dark:focus:border-blue-400 transition-colors duration-200',
            'name': 'pipeline'
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
                self.fields['pipeline'].queryset = Pipeline.objects.filter(test_id=test_id)
            except (ValueError, TypeError):
                pass

CHROMOSOME_SIZES = {
    "chr1": 248956422,
    "chr2": 242193529,
    "chr3": 198295559,
    "chr4": 190214555,
    "chr5": 181538259,
    "chr6": 170805979,
    "chr7": 159345973,
    "chrX": 156040895,
    "chr8": 145138636,
    "chr9": 138394717,
    "chr11": 135086622,
    "chr10": 133797422,
    "chr12": 133275309,
    "chr13": 114364328,
    "chr14": 107043718,
    "chr15": 101991189,
    "chr16": 90338345,
    "chr17": 83257441,
    "chr18": 80373285,
    "chr20": 64444167,
    "chr19": 58617616,
    "chrY": 57227415,
    "chr22": 50818468,
    "chr21": 46709983,
}

CHROMOSOME_CHOICES = [(chrom, chrom) for chrom in CHROMOSOME_SIZES.keys()]

ASSEMBLY_CHOICES = [
    ("hg38", "GRCh38 (hg38)"),
]

class BaseVariantForm(forms.ModelForm):
    chromosome = forms.ChoiceField(
        choices=CHROMOSOME_CHOICES,
        widget=forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'})
    )
    assembly_version = forms.ChoiceField(
        choices=ASSEMBLY_CHOICES,
        initial='hg38',
        widget=forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'})
    )

    class Meta:
        exclude = ['created_by', 'created_at', 'pipeline', 'individual']
        widgets = {
            'start': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'end': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'zygosity': forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        chromosome = cleaned_data.get("chromosome")
        start = cleaned_data.get("start")
        end = cleaned_data.get("end")

        if start and start < 1:
             self.add_error('start', "Start position must be greater than 0.")

        if end and end < 1:
             self.add_error('end', "End position must be greater than 0.")

        if start and end:
            if start > end:
                self.add_error('start', "Start position cannot be greater than end position.")

            if chromosome in CHROMOSOME_SIZES:
                max_size = CHROMOSOME_SIZES[chromosome]
                if end > max_size:
                    self.add_error('end', f"End position exceeds the size of {chromosome} ({max_size} bp).")
                if start > max_size:
                     self.add_error('start', f"Start position exceeds the size of {chromosome} ({max_size} bp).")
        
        return cleaned_data

class SNVForm(BaseVariantForm):
    class Meta(BaseVariantForm.Meta):
        model = SNV
        fields = ['assembly_version', 'chromosome', 'start', 'end', 'zygosity', 'reference', 'alternate']
        widgets = {
            **BaseVariantForm.Meta.widgets,
            'reference': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'alternate': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
        }

class CNVForm(BaseVariantForm):
    class Meta(BaseVariantForm.Meta):
        model = CNV
        fields = ['assembly_version', 'chromosome', 'start', 'end', 'zygosity', 'cnv_type', 'copy_number']
        widgets = {
            **BaseVariantForm.Meta.widgets,
            'cnv_type': forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'copy_number': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
        }

class SVForm(BaseVariantForm):
    class Meta(BaseVariantForm.Meta):
        model = SV
        fields = ['assembly_version', 'chromosome', 'start', 'end', 'zygosity', 'sv_type', 'breakpoints']
        widgets = {
            **BaseVariantForm.Meta.widgets,
            'sv_type': forms.Select(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'breakpoints': forms.Textarea(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm', 'rows': 3}),
        }

class RepeatForm(BaseVariantForm):
    class Meta(BaseVariantForm.Meta):
        model = Repeat
        fields = ['assembly_version', 'chromosome', 'start', 'end', 'zygosity', 'repeat_unit', 'repeat_count']
        widgets = {
            **BaseVariantForm.Meta.widgets,
            'repeat_unit': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
            'repeat_count': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'}),
        }

class VariantUpdateForm(forms.ModelForm):
    class Meta:
        model = Variant
        fields = ['pipeline'] # We only want to update pipeline for now
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter pipeline based on individual if possible, or show all
        if self.instance and self.instance.individual:
            # Show pipelines for the same individual
            self.fields['pipeline'].queryset = Pipeline.objects.filter(
                test__sample__individual=self.instance.individual
            )
        
        self.fields['pipeline'].widget.attrs.update({
            'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm'
        })

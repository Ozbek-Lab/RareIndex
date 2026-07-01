from django import forms
import re

from .models import Variant, SNV, CNV, SV, Repeat
from lab.models import Individual, Test, Pipeline, Analysis

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

    def __init__(self, *args, individual=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.individual = individual

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
        
        if not self.errors and self.individual:
            query = dict()
            for field in ['chromosome', 'start', 'end']:
                if field in cleaned_data and cleaned_data[field] is not None:
                    query[field] = cleaned_data[field]
            
            for field in ['reference', 'alternate', 'cnv_type', 'copy_number', 'sv_type', 'repeat_unit', 'repeat_count']:
                if field in self.fields and field in cleaned_data:
                    query[field] = cleaned_data[field]
            
            existing = self._meta.model.objects.filter(individual=self.individual, **query)
            if existing.exists():
                raise forms.ValidationError("This variant has already been added to this individual.")
        
        return cleaned_data


class VariantTypeForm(forms.Form):
    VARIANT_TYPE_CHOICES = [
        ("snv", "SNV"),
        ("cnv", "CNV"),
        ("sv", "SV"),
        ("repeat", "Repeat"),
    ]

    variant_type = forms.ChoiceField(
        choices=VARIANT_TYPE_CHOICES,
        widget=forms.Select(
            attrs={
                "class": "select select-bordered w-full",
            }
        ),
        label="Variant type",
    )


class VariantACMGEvidenceOverrideForm(forms.Form):
    override_state = forms.TypedChoiceField(
        choices=[
            ("inherit", "Use imported value"),
            ("include", "Include manually"),
            ("exclude", "Exclude manually"),
        ],
        coerce=str,
        initial="inherit",
        label="Override",
    )
    note = forms.CharField(
        required=False,
        label="Note",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            current_classes = field.widget.attrs.get("class", "")
            if isinstance(field.widget, forms.Select):
                field.widget.attrs["class"] = f"select select-bordered w-full {current_classes}".strip()
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs["class"] = f"textarea textarea-bordered w-full {current_classes}".strip()

class SNVForm(BaseVariantForm):
    # Combined human-friendly representation: chr:posREF>ALT
    snv_string = forms.CharField(
        label="Variant (chr:posREF>ALT)",
        help_text="e.g. chr3:33114394TGC>T",
    )

    class Meta(BaseVariantForm.Meta):
        model = SNV
        fields = ["assembly_version", "snv_string", "zygosity"]
        widgets = {
            **BaseVariantForm.Meta.widgets,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hide low-level fields; they are derived from snv_string.
        for name in ("chromosome", "start", "end", "reference", "alternate"):
            self.fields.pop(name, None)

        self.fields["snv_string"].widget.attrs.update(
            {
                "class": "input input-bordered w-full font-mono text-xs",
                "placeholder": "chr3:33114394TGC>T",
                "pattern": r"^(chr[0-9]{1,2}|chrX|chrY|chrM):\d+[ACGT]+>[ACGT]+$",
                "title": "Format: chrN:positionREF>ALT, e.g. chr3:33114394TGC>T",
            }
        )

    def clean_snv_string(self):
        value = self.cleaned_data["snv_string"].strip()
        # Basic strict pattern: chrN:posREF>ALT
        m = re.match(r"^(chr[0-9]{1,2}|chrX|chrY|chrM):(\d+)([ACGT]+)>([ACGT]+)$", value)
        if not m:
            raise forms.ValidationError("Use format chrN:positionREF>ALT, e.g. chr3:33114394TGC>T")
        chrom, pos, ref, alt = m.groups()
        pos_int = int(pos)

        # Populate fields used by the model and BaseVariantForm.clean
        self.cleaned_data["chromosome"] = chrom
        self.cleaned_data["start"] = pos_int
        self.cleaned_data["end"] = pos_int
        self.cleaned_data["reference"] = ref
        self.cleaned_data["alternate"] = alt
        return value

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.chromosome = self.cleaned_data["chromosome"]
        obj.start = self.cleaned_data["start"]
        obj.end = self.cleaned_data["end"]
        obj.reference = self.cleaned_data["reference"]
        obj.alternate = self.cleaned_data["alternate"]
        if commit:
            obj.save()
        return obj

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
        # Allow assigning an Analysis; Variants are no longer linked directly to Pipelines.
        fields = ["analysis"]
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Limit available analyses to those belonging to the same individual (via pipeline)
        if self.instance and self.instance.individual:
            self.fields["analysis"].queryset = Analysis.objects.filter(
                pipeline__test__sample__individual=self.instance.individual
            )
        
        self.fields["analysis"].widget.attrs.update(
            {
                "class": "mt-1 block w-full rounded-md border-gray-300 shadow-sm "
                "focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
            }
        )

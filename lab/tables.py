import django_tables2 as tables
from django.utils.html import format_html
from django.urls import reverse

from .models import Individual, Sample, Project
from variant.models import Variant

class IndividualTable(tables.Table):
    """Static column set: Primary ID, Secondary ID, Other IDs, Institution, Name, Sex, Status."""

    primary_id = tables.Column(verbose_name="Primary ID", order_by=("id"))
    secondary_id = tables.Column(verbose_name="Secondary ID", order_by=("id"))
    other_table_ids = tables.Column(verbose_name="Other IDs", orderable=False)
    institution = tables.Column(verbose_name="Institution", orderable=False)
    full_name = tables.Column(verbose_name="Name")
    sex = tables.Column(verbose_name="Sex")
    status = tables.Column(verbose_name="Status")

    def before_render(self, request):
        self.total_count = Individual.objects.count()
        self.verbose_name = Individual._meta.verbose_name
        self.verbose_name_plural = Individual._meta.verbose_name_plural

    def render_institution(self, value, record):
        names = [i.name for i in record.institution.all()]
        return ", ".join(names) if names else "—"

    class Meta:
        model = Individual
        template_name = "lab/partials/individual_expandable_table.html"
        fields = ("primary_id", "secondary_id", "other_table_ids", "institution", "full_name", "sex", "status")
        attrs = {
            "class": "table table-zebra table-sm",
            "thead": {
                "class": ""
            },
            "th": {
                "class": ""
            },
            "td": {
                "class": ""
            }
        }

    def render_status(self, value, record):
        """Wrap status in a span with ID for OOB swaps"""
        status = record.status
        icon_html = ""
        style = f"color: {status.color}; filter: brightness(0.9);"

        if status.icon:
            icon_html = format_html('<i class="fa-solid {} mr-1.5"></i>', status.icon)

        label = status.display_name

        badge_html = format_html(
            '<div class="badge badge-sm bg-transparent border-0 font-medium whitespace-nowrap" style="{}" title="{}"> {}{} </div>',
            style,
            status.name,
            icon_html,
            label,
        )
        return format_html(
            '<span id="individual-row-status-{}">{}</span>',
            record.pk,
            badge_html,
        )

    def render_full_name(self, value, record):
        # Check permissions
        user = getattr(self.request, "user", None) if hasattr(self, "request") else None
        
        if not user or not user.has_perm("lab.view_sensitive_data"):
             return "*****"
             
        url = reverse("lab:reveal_sensitive_field", kwargs={
            "model_name": "Individual",
            "pk": record.pk,
            "field_name": "full_name"
        })
        
        return format_html(
            '<span id="name-reveal-{}" class="reveal-wrapper">'
            '***** '
            '<button class="btn btn-xs btn-ghost text-primary" '
            'hx-get="{}" '
            'hx-target="closest .reveal-wrapper" '
            'hx-swap="outerHTML"><i class="fa-solid fa-eye"></i></button>'
            '</span>',
            record.pk,
            url,
            record.pk
        )

class SampleTable(tables.Table):
    id = tables.Column()
    individual = tables.Column()
    
    def before_render(self, request):
        self.total_count = Sample.objects.count()
        self.verbose_name = Sample._meta.verbose_name
        self.verbose_name_plural = Sample._meta.verbose_name_plural

    class Meta:
        model = Sample
        template_name = "lab/partials/infinite_table.html"
        fields = ("id", "individual", "sample_type", "status", "receipt_date")
        attrs = {
             "class": "table table-zebra table-sm",
            "thead": {
                "class": ""
            },
            "th": {
                 "class": ""
            },
            "td": {
                 "class": ""
            }
        }

class ProjectTable(tables.Table):
    name = tables.Column(verbose_name="Name")
    status = tables.Column(verbose_name="Status")
    priority = tables.Column(verbose_name="Priority")
    individuals_count = tables.Column(
        verbose_name="Individuals",
        orderable=False,
        empty_values=(),  # Force render_individuals_count to run (no model field)
    )
    
    def before_render(self, request):
        self.total_count = Project.objects.count()
        self.verbose_name = Project._meta.verbose_name
        self.verbose_name_plural = Project._meta.verbose_name_plural

    class Meta:
        model = Project
        template_name = "lab/partials/project_expandable_table.html" 
        fields = ("name", "status", "priority", "due_date", "individuals_count")
        attrs = {
            "class": "table table-zebra table-sm",
            "thead": {
                "class": ""
            },
            "th": {
                "class": ""
            },
            "td": {
                "class": ""
            }
        }

    def render_status(self, value, record):
        """Wrap status in a span with ID for OOB swaps"""
        status = record.status
        icon_html = ""
        style = f"color: {status.color}; filter: brightness(0.9);"

        if status.icon:
            icon_html = format_html('<i class="fa-solid {} mr-1.5"></i>', status.icon)

        label = status.display_name

        badge_html = format_html(
            '<div class="badge badge-sm bg-transparent border-0 font-medium whitespace-nowrap" style="{}" title="{}"> {}{} </div>',
            style,
            status.name,
            icon_html,
            label,
        )
        return format_html(
            '<span id="project-row-status-{}">{}</span>',
            record.pk,
            badge_html,
        )

    def render_name(self, value, record):
        return format_html(
            '<span class="font-medium">{}</span>',
            value
        )

    def render_priority(self, value, record):
        priority_colors = {
            'low': 'text-info',
            'medium': 'text-warning',
            'high': 'text-error'
        }
        color_class = priority_colors.get(value, 'text-base-content/60')
        return format_html(
            '<span class="badge badge-sm badge-ghost {}">{}</span>',
            color_class,
            value.title() if value else '-'
        )

    def render_individuals_count(self, value, record):
        individuals = record.individuals.all()
        total_count = individuals.count()
        
        # Calculate statistics
        unique_families_count = (
            individuals.exclude(family__isnull=True)
            .values_list("family", flat=True)
            .distinct()
            .count()
        )
        no_family_individuals_count = individuals.filter(family__isnull=True).count()
        families_count = unique_families_count + no_family_individuals_count
        affected_count = individuals.filter(is_affected=True).count()
        index_count = individuals.filter(is_index=True).count()
        
        # Create tooltip with Alpine.js
        return format_html(
            '<div class="relative inline-block" '
            'x-data="{{ showTooltip: false }}" '
            '@mouseenter="showTooltip = true" '
            '@mouseleave="showTooltip = false">'
            '<span class="badge badge-sm badge-ghost cursor-help">{}</span>'
            '<div x-show="showTooltip" '
            'x-transition:enter="transition ease-out duration-200" '
            'x-transition:enter-start="opacity-0 scale-95" '
            'x-transition:enter-end="opacity-100 scale-100" '
            'x-transition:leave="transition ease-in duration-150" '
            'x-transition:leave-start="opacity-100 scale-100" '
            'x-transition:leave-end="opacity-0 scale-95" '
            'x-cloak '
            'class="absolute z-50 left-full ml-2 top-1/2 -translate-y-1/2 bg-base-100 border border-base-300 rounded-lg shadow-lg p-3 min-w-[180px]">'
            '<div class="space-y-1.5 text-xs">'
            '<div class="flex justify-between"><span class="font-semibold text-base-content/80">Families:</span><span class="font-normal">{}</span></div>'
            '<div class="flex justify-between"><span class="font-semibold text-base-content/80">Affected:</span><span class="font-normal">{}</span></div>'
            '<div class="flex justify-between"><span class="font-semibold text-base-content/80">Index:</span><span class="font-normal">{}</span></div>'
            '<div class="flex justify-between border-t border-base-300 pt-1 mt-1"><span class="font-semibold text-base-content/80">Total:</span><span class="font-normal">{}</span></div>'
            '</div>'
            '</div>'
            '</div>',
            total_count,
            families_count,
            affected_count,
            index_count,
            total_count
        )


class VariantTable(tables.Table):
    variant = tables.Column(verbose_name="Variant", accessor="hgvs_name", orderable=False)
    type = tables.Column(verbose_name="Type", accessor="type", orderable=False)
    chromosome = tables.Column(verbose_name="Chr")
    start = tables.Column(verbose_name="Start")
    end = tables.Column(verbose_name="End")
    zygosity = tables.Column(verbose_name="Zygosity")
    genes = tables.Column(verbose_name="Genes", accessor="genes", orderable=False)
    individual = tables.Column(verbose_name="Individual", accessor="individual__primary_id")
    status = tables.Column(verbose_name="Status")

    def before_render(self, request):
        self.total_count = Variant.objects.count()
        self.verbose_name = Variant._meta.verbose_name
        self.verbose_name_plural = Variant._meta.verbose_name_plural

    def render_genes(self, value, record):
        symbols = [g.symbol for g in value.all()]
        if not symbols:
            return "—"
        return format_html(
            "{}",
            ", ".join(symbols),
        )

    def render_individual(self, value, record):
        if not value:
            return "—"
        url = reverse("lab:individual_detail", kwargs={"pk": record.individual_id})
        return format_html(
            '<span class="inline-flex items-center gap-1.5">'
            '  <a href="{}" target="_blank" rel="noopener noreferrer"'
            '     class="opacity-50 hover:opacity-100 transition-opacity">'
            '    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5"'
            '         fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">'
            '      <path stroke-linecap="round" stroke-linejoin="round"'
            '            d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4'
            '               M14 4h6m0 0v6m0-6L10 14"/>'
            '    </svg>'
            '  </a>'
            '  <span class="font-mono text-sm">{}</span>'
            '</span>',
            url,
            value,
        )

    class Meta:
        model = Variant
        template_name = "lab/partials/variant_table_body.html"
        fields = (
            "variant",
            "type",
            "chromosome",
            "start",
            "end",
            "zygosity",
            "genes",
            "individual",
            "status",
        )
        attrs = {
            "class": "table table-zebra table-sm",
            "thead": {"class": ""},
            "th": {"class": ""},
            "td": {"class": ""},
        }

    def render_status(self, value, record):
        status = record.status
        if not status:
            return "-"

        icon_html = ""
        style = f"color: {status.color}; filter: brightness(0.9);" if status.color else ""

        if status.icon:
            icon_html = format_html('<i class="fa-solid {} mr-1.5"></i>', status.icon)

        label = status.display_name

        badge_html = format_html(
            '<div class="badge badge-sm bg-transparent border-0 font-medium whitespace-nowrap" style="{}" title="{}"> {}{} </div>',
            style,
            status.name,
            icon_html,
            label,
        )
        return format_html(
            '<span id="variant-row-status-{}">{}</span>',
            record.pk,
            badge_html,
        )

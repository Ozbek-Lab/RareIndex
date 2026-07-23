import django_tables2 as tables
from django.utils.html import format_html, mark_safe
from django.urls import reverse

from .models import IdentifierType, Individual, Sample, Project
from .display_preferences import DEFAULT_INSTITUTION_DISPLAY, institution_display_name, normalize_institution_display
from .status_utils import collect_individual_row_statuses
from variant.models import Variant

def _render_status_badges(statuses):
    """Return HTML for a list of status badges."""
    badges = []
    for status in statuses:
        icon_html = format_html('<i class="fa-solid {} mr-1.5"></i>', status.icon) if status.icon else ""
        style = f"color: {status.color}; filter: brightness(0.9);" if status.color else ""
        badges.append(format_html(
            '<div class="badge badge-sm bg-transparent border-0 font-medium whitespace-nowrap" style="{}" title="{}"> {}{} </div>',
            style,
            status.name,
            icon_html,
            status.display_name,
        ))
    if not badges:
        return mark_safe('<span class="text-base-content/30 text-xs">—</span>')
    return mark_safe("".join(badges))


class IndividualTable(tables.Table):
    """Static column set: Primary ID, Secondary ID, Other IDs, Institution, Name, Sex, Status."""

    primary_id = tables.Column(verbose_name="Primary ID", order_by=("id",), empty_values=())
    secondary_id = tables.Column(verbose_name="Secondary ID", order_by=("id",), empty_values=())
    other_table_ids = tables.Column(verbose_name="Other IDs", orderable=False, empty_values=())
    institution = tables.Column(verbose_name="Institution", order_by=("first_institution_name",))
    full_name = tables.Column(verbose_name="Name")
    sex = tables.Column(verbose_name="Sex")
    statuses = tables.Column(verbose_name="Status", orderable=False, empty_values=())
    # Created date from the Individual record
    created_at = tables.DateTimeColumn(
        verbose_name="Created",
        accessor="created_at",
        format="m/y",
        short=False,
    )
    # Aggregated "last activity" timestamp across Individual + related
    # Sample, Test, Pipeline, Analysis, Variant, AnalysisReport.
    last_activity = tables.DateTimeColumn(
        verbose_name="Last Activity",
        accessor="last_activity",
        order_by=("last_activity",),
        format="m/y",
        short=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_identifier_types()

    def _set_identifier_types(self):
        self.primary_type = IdentifierType.objects.filter(use_priority=1).order_by("id").first()
        self.secondary_type = IdentifierType.objects.filter(use_priority=2).order_by("id").first()

    def before_render(self, request):
        self.total_count = Individual.objects.count()
        self.verbose_name = Individual._meta.verbose_name
        self.verbose_name_plural = Individual._meta.verbose_name_plural

        self._set_identifier_types()
        if self.primary_type:
            self.columns["primary_id"].column.verbose_name = f"{self.primary_type.name} ID"
        if self.secondary_type:
            self.columns["secondary_id"].column.verbose_name = f"{self.secondary_type.name} ID"

    def _table_ids(self, record):
        return list(record.cross_ids.all())

    def render_primary_id(self, value, record):
        primary_type = getattr(self, "primary_type", None)
        if not primary_type:
            return "NO PRIMARY ID SET"
        matches = [
            cross_id for cross_id in self._table_ids(record)
            if cross_id.id_type.use_priority == 1
        ]
        if matches:
            matches.sort(key=lambda cross_id: cross_id.id_type.id)
            return matches[0].id_value
        return f"No {primary_type.name} ID"

    def render_secondary_id(self, value, record):
        secondary_type = getattr(self, "secondary_type", None)
        if not secondary_type:
            return "NO SECONDARY ID SET"
        matches = [
            cross_id for cross_id in self._table_ids(record)
            if cross_id.id_type.use_priority == 2
        ]
        if matches:
            matches.sort(key=lambda cross_id: cross_id.id_type.id)
            return matches[0].id_value
        return f"No {secondary_type.name} ID"

    def render_other_table_ids(self, value, record):
        ids = [
            f"{cross_id.id_type.name}: {cross_id.id_value}"
            for cross_id in self._table_ids(record)
            if cross_id.id_type.use_priority not in (1, 2)
            and cross_id.id_type.is_shown_in_table
        ]
        return ", ".join(ids) if ids else ""

    def render_institution(self, value, record):
        user = getattr(self.request, "user", None) if hasattr(self, "request") else None
        mode = DEFAULT_INSTITUTION_DISPLAY
        if user and user.is_authenticated and hasattr(user, "profile"):
            mode = normalize_institution_display(
                (user.profile.display_preferences or {}).get("institution_display", DEFAULT_INSTITUTION_DISPLAY)
            )
        names = [institution_display_name(i, mode) for i in record.institution.all()]
        return ", ".join(names) if names else "—"

    class Meta:
        model = Individual
        template_name = "lab/partials/individual_expandable_table.html"
        fields = (
            "primary_id",
            "secondary_id",
            "other_table_ids",
            "institution",
            "full_name",
            "sex",
            "statuses",
            "created_at",
            "last_activity",
        )
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

    def render_statuses(self, value, record):
        """Render multiple status badges wrapped in a span for OOB swaps."""
        all_statuses = collect_individual_row_statuses(record)
        badges_html = _render_status_badges(all_statuses)
        return format_html(
            '<span id="individual-row-status-{}">{}</span>',
            record.pk,
            badges_html,
        )

    def render_created_at(self, value):
        if not value:
            return "—"
        return value.strftime("%m/%y")

    def render_last_activity(self, value):
        if not value:
            return "—"
        return value.strftime("%m/%y")

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
    statuses = tables.Column(verbose_name="Status", orderable=False, empty_values=())

    def before_render(self, request):
        self.total_count = Sample.objects.count()
        self.verbose_name = Sample._meta.verbose_name
        self.verbose_name_plural = Sample._meta.verbose_name_plural

    def render_statuses(self, value, record):
        return _render_status_badges(list(record.statuses.all()))

    class Meta:
        model = Sample
        template_name = "lab/partials/infinite_table.html"
        fields = ("id", "individual", "sample_type", "statuses", "receipt_date")
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
    statuses = tables.Column(verbose_name="Status", orderable=False, empty_values=())
    priority = tables.Column(verbose_name="Priority")
    individuals_count = tables.Column(
        verbose_name="Individuals",
        orderable=False,
        empty_values=(),
    )

    def before_render(self, request):
        self.total_count = Project.objects.count()
        self.verbose_name = Project._meta.verbose_name
        self.verbose_name_plural = Project._meta.verbose_name_plural

    class Meta:
        model = Project
        template_name = "lab/partials/project_expandable_table.html"
        fields = ("name", "statuses", "priority", "due_date", "individuals_count")
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

    def render_statuses(self, value, record):
        """Render multiple status badges wrapped in a span for OOB swaps."""
        all_statuses = list(record.statuses.all())
        badges_html = _render_status_badges(all_statuses)
        return format_html(
            '<span id="project-row-status-{}">{}</span>',
            record.pk,
            badges_html,
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
    statuses = tables.Column(verbose_name="Status", orderable=False, empty_values=())

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
            "statuses",
        )
        attrs = {
            "class": "table table-zebra table-sm",
            "thead": {"class": ""},
            "th": {"class": ""},
            "td": {"class": ""},
        }

    def render_statuses(self, value, record):
        all_statuses = list(record.statuses.all())
        badges_html = _render_status_badges(all_statuses)
        return format_html(
            '<span id="variant-row-status-{}">{}</span>',
            record.pk,
            badges_html,
        )

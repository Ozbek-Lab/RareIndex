import django_tables2 as tables
from .models import Individual, Sample, Project, IdentifierType
from django.utils.html import format_html

from django.urls import reverse

class IndividualTable(tables.Table):
    primary_id = tables.Column(order_by=("id"))
    secondary_id = tables.Column(order_by=("id"))
    other_table_ids = tables.Column(verbose_name="Other IDs", orderable=False)
    institution = tables.Column(verbose_name="Institution", orderable=False)
    full_name = tables.Column(verbose_name="Name")
    status = tables.Column(verbose_name="Status")
    sex = tables.Column(verbose_name="Sex")
    
    def before_render(self, request):
        self.total_count = Individual.objects.count()
        self.verbose_name = Individual._meta.verbose_name
        self.verbose_name_plural = Individual._meta.verbose_name_plural

        # Dynamic column headers based on IdentifierType priorities
        primary_type = IdentifierType.objects.filter(use_priority=1).order_by("id").first()
        secondary_type = IdentifierType.objects.filter(use_priority=2).order_by("id").first()
        if primary_type:
            self.columns["primary_id"].column.verbose_name = primary_type.name
        else:
            self.columns["primary_id"].column.verbose_name = "Primary ID"
        if secondary_type:
            self.columns["secondary_id"].column.verbose_name = secondary_type.name
        else:
            # If there is no IdentifierType with secondary priority at all,
            # hide the secondary_id column from the rendered table.
            if "secondary_id" in self.columns:
                self.columns["secondary_id"].column.visible = False

        # Individual ID is not needed as a visible column in the table rows
        if "individual_id" in self.columns:
            self.columns["individual_id"].column.visible = False

    def render_institution(self, value, record):
        names = [i.name for i in record.institution.all()]
        return ", ".join(names) if names else "—"

    class Meta:
        model = Individual
        template_name = "lab/partials/individual_expandable_table.html" 
        fields = ("primary_id", "secondary_id", "other_table_ids", "institution", "individual_id", "full_name", "sex", "status", "family")
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
        icon_html = ""
        # Apply color to the icon/text instead of border
        style = f"color: {record.status.color}; filter: brightness(0.9);"
        
        if record.status.icon:
            # We use format_html to ensure the class is escaped if needed, though it comes from DB
            icon_html = format_html('<i class="fa-solid {} mr-1.5"></i>', record.status.icon)
        
        # We can pass safe string (icon_html) to another format_html
        # Removed border-left style as requested
        # Added style to the badge for text/icon color
        # Removed badge-ghost to remove gray background, making it effectively transparent with just text color
        badge_html = format_html(
            '<div class="badge badge-sm bg-transparent border-0 font-medium" style="{}"> {}{} </div>',
            style,
            icon_html,
            value
        )
        return format_html(
            '<span id="individual-row-status-{}">{}</span>',
            record.pk,
            badge_html
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
    project_id = tables.Column(verbose_name="ID", order_by=("id"))
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
        fields = ("project_id", "name", "status", "priority", "due_date", "individuals_count")
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
        icon_html = ""
        # Apply color to the icon/text instead of border
        style = f"color: {record.status.color}; filter: brightness(0.9);"
        
        if record.status.icon:
            icon_html = format_html('<i class="fa-solid {} mr-1.5"></i>', record.status.icon)
        
        badge_html = format_html(
            '<div class="badge badge-sm bg-transparent border-0 font-medium" style="{}"> {}{} </div>',
            style,
            icon_html,
            value
        )
        return format_html(
            '<span id="project-row-status-{}">{}</span>',
            record.pk,
            badge_html
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

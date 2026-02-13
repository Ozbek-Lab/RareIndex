import django_tables2 as tables
from .models import Individual, Sample
from django.utils.html import format_html

from django.urls import reverse

class IndividualTable(tables.Table):
    individual_id = tables.Column(verbose_name="ID", order_by=("id"))
    full_name = tables.Column(verbose_name="Name")
    status = tables.Column(verbose_name="Status")
    sex = tables.Column(verbose_name="Sex")
    
    def before_render(self, request):
        self.total_count = Individual.objects.count()
        self.verbose_name = Individual._meta.verbose_name
        self.verbose_name_plural = Individual._meta.verbose_name_plural

    class Meta:
        model = Individual
        template_name = "lab/partials/individual_expandable_table.html" 
        fields = ("individual_id", "full_name", "sex", "status", "family", "created_at")
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

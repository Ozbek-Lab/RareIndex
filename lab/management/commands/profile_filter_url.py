import time
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, reset_queries
from django.http import QueryDict
from django.test import RequestFactory

from lab.filters import IndividualFilter, ProjectFilter, VariantFilter
from lab.views import IndividualListView, ProjectListView, VariantListView


PROFILES = {
    "individual": {
        "path_prefix": "/individuals/",
        "view": IndividualListView,
        "filter": IndividualFilter,
        "table_target": "individual-table-container",
    },
    "variant": {
        "path_prefix": "/variants/",
        "view": VariantListView,
        "filter": VariantFilter,
        "table_target": "variant-table-container",
    },
    "project": {
        "path_prefix": "/projects/",
        "view": ProjectListView,
        "filter": ProjectFilter,
        "table_target": "project-table-container",
    },
}


def infer_kind(path):
    for kind, profile in PROFILES.items():
        if path.startswith(profile["path_prefix"]):
            return kind
    return None


def summarize_value(value, limit=8):
    if value is None or value == "":
        return ""
    if hasattr(value, "exists"):
        items = list(value[:limit])
        suffix = "" if value.count() <= limit else " ..."
        return "[" + ", ".join(str(item) for item in items) + suffix + "]"
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        suffix = "" if len(items) <= limit else " ..."
        return "[" + ", ".join(str(item) for item in items[:limit]) + suffix + "]"
    return str(value)


def is_empty_value(filterset, value):
    if hasattr(filterset, "_is_empty_filter_value"):
        return filterset._is_empty_filter_value(value)
    if value is None or value == "":
        return True
    if hasattr(value, "exists"):
        return not value.exists()
    try:
        return len(value) == 0
    except TypeError:
        return False


def query_stats():
    queries = list(connection.queries)
    total_sql_time = 0.0
    for query in queries:
        try:
            total_sql_time += float(query.get("time") or 0)
        except ValueError:
            pass
    slowest = sorted(
        queries,
        key=lambda item: float(item.get("time") or 0),
        reverse=True,
    )
    return queries, total_sql_time, slowest


class Command(BaseCommand):
    help = "Profile RareIndex list filtering from a pasted individuals/variants/projects URL."

    def add_arguments(self, parser):
        parser.add_argument("url", help="Full URL or query string to profile.")
        parser.add_argument(
            "--kind",
            choices=sorted(PROFILES),
            help="List type. Inferred from the URL path when omitted.",
        )
        parser.add_argument(
            "--user",
            help="Username to attach to the request, useful for permission-sensitive search.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=25,
            help="Number of rows to evaluate for the first-page phase.",
        )
        parser.add_argument(
            "--show-sql",
            type=int,
            default=5,
            help="Number of slow SQL statements to print for each measured phase.",
        )

    def handle(self, *args, **options):
        parsed = urlparse(options["url"])
        path = parsed.path or "/"
        query_string = parsed.query or options["url"].lstrip("?")
        data = QueryDict(query_string, mutable=False)

        kind = options["kind"] or infer_kind(path)
        if not kind:
            raise CommandError("Could not infer kind. Pass --kind individual, variant, or project.")

        profile = PROFILES[kind]
        request = RequestFactory().get(f"{profile['path_prefix']}?{data.urlencode()}")
        request.htmx = True
        request.headers = {"HX-Target": profile["table_target"]}

        if options["user"]:
            User = get_user_model()
            request.user = User.objects.get(username=options["user"])
        else:
            request.user = AnonymousUser()

        build_result = self.profile_phase(
            "build filterset/queryset",
            lambda: self.build_filterset(profile, request, data),
            options["show_sql"],
        )
        filterset, filtered_queryset = build_result

        ignored_params = sorted(
            set(data.keys())
            - set(filterset.filters.keys())
            - {f"{name}__mode" for name in filterset.filters}
            - {"filter_group_mode", "page", "direction"}
        )
        active_filters = []
        for name in filterset.filters:
            value = filterset.form.cleaned_data.get(name)
            if not is_empty_value(filterset, value):
                active_filters.append((name, summarize_value(value)))

        self.stdout.write(self.style.MIGRATE_HEADING(f"Profile: {kind}"))
        self.stdout.write(f"Path: {path or profile['path_prefix']}")
        self.stdout.write(f"Query params: {len(data.keys())}")
        self.stdout.write(f"Active filters: {len(active_filters)}")
        for name, value in active_filters:
            self.stdout.write(f"  - {name}: {value}")
        if ignored_params:
            self.stdout.write(f"Ignored params: {', '.join(ignored_params)}")

        self.profile_phase("count", lambda: filtered_queryset.count(), options["show_sql"])
        self.profile_phase(
            f"first {options['limit']} rows",
            lambda: list(filtered_queryset[: options["limit"]]),
            options["show_sql"],
        )

    def build_filterset(self, profile, request, data):
        view = profile["view"]()
        view.request = request
        base_queryset = view.get_queryset()
        filterset = profile["filter"](data or None, queryset=base_queryset, request=request)
        filterset.form.is_valid()
        return filterset, filterset.qs

    def profile_phase(self, label, callback, show_sql):
        connection.force_debug_cursor = True
        reset_queries()
        start = time.perf_counter()
        result = callback()
        elapsed = time.perf_counter() - start
        queries, total_sql_time, slowest = query_stats()

        if isinstance(result, tuple) and len(result) == 2:
            result_label = "filterset ready"
        elif isinstance(result, list):
            result_label = f"{len(result)} rows"
        else:
            result_label = str(result)

        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO(label))
        self.stdout.write(f"  result: {result_label}")
        self.stdout.write(f"  wall time: {elapsed:.4f}s")
        self.stdout.write(f"  SQL queries: {len(queries)}")
        self.stdout.write(f"  SQL time: {total_sql_time:.4f}s")

        for index, query in enumerate(slowest[:show_sql], start=1):
            sql = " ".join((query.get("sql") or "").split())
            if len(sql) > 500:
                sql = f"{sql[:500]} ..."
            self.stdout.write(f"  slow SQL {index} ({query.get('time')}s): {sql}")

        return result

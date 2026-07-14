from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save
from django.test import RequestFactory, TestCase

from lab.htmx_views import update_status, variant_detail_partial
from lab.models import Individual, Status
from variant.models import Annotation, SNV, Variant
from variant.signals import annotate_and_link_genes


class VariantStatusControlsTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        post_save.disconnect(annotate_and_link_genes, sender=SNV)

    @classmethod
    def tearDownClass(cls):
        post_save.connect(annotate_and_link_genes, sender=SNV)
        super().tearDownClass()

    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="variant-status-editor")
        self.individual = Individual.objects.create(
            full_name="Variant Status Person",
            created_by=self.user,
        )
        self.variant = SNV.objects.create(
            assembly_version="hg38",
            chromosome="chr1",
            start=101,
            end=101,
            individual=self.individual,
            created_by=self.user,
            zygosity="het",
            reference="A",
            alternate="G",
        )
        self.variant_ct = ContentType.objects.get_for_model(Variant)
        self.status = Status.objects.create(
            name="Needs Review",
            short_name="NRev",
            color="orange",
            icon="fa-circle-question",
            content_type=self.variant_ct,
            created_by=self.user,
        )
        self.annotation_change_permission = Permission.objects.get(
            content_type=ContentType.objects.get_for_model(Annotation),
            codename="change_annotation",
        )

    def get_request(self):
        request = self.factory.get("/")
        request.user = self.user
        return request

    def post_request(self):
        request = self.factory.post("/", HTTP_HX_REQUEST="true")
        request.user = self.user
        return request

    def test_annotation_editors_can_render_and_toggle_variant_status_controls(self):
        self.user.user_permissions.add(self.annotation_change_permission)

        detail_response = variant_detail_partial(self.get_request(), self.variant.pk)
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(
            detail_response,
            f'id="variant-status-controls-{self.variant.pk}"',
        )

        update_response = update_status(
            self.post_request(),
            self.variant_ct.pk,
            self.variant.pk,
            self.status.pk,
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertContains(
            update_response,
            f'id="variant-status-controls-{self.variant.pk}"',
        )
        self.assertContains(update_response, 'id="variant-row-status-')
        self.assertTrue(
            Variant.objects.get(pk=self.variant.pk).statuses.filter(pk=self.status.pk).exists()
        )

    def test_view_only_users_do_not_see_or_toggle_variant_status_controls(self):
        detail_response = variant_detail_partial(self.get_request(), self.variant.pk)
        self.assertEqual(detail_response.status_code, 200)
        self.assertNotContains(detail_response, "variant-status-controls")

        update_response = update_status(
            self.post_request(),
            self.variant_ct.pk,
            self.variant.pk,
            self.status.pk,
        )
        self.assertEqual(update_response.status_code, 403)
        self.assertFalse(
            Variant.objects.get(pk=self.variant.pk).statuses.filter(pk=self.status.pk).exists()
        )

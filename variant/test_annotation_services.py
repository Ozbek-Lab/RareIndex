from unittest.mock import Mock, patch
from contextlib import redirect_stdout
from io import StringIO
import json

import requests

from django.test import SimpleTestCase

from variant.models import CNV, SNV, SV
from variant.services import AnnotationService


class AnnotationServiceVariantTypeTests(SimpleTestCase):
    def test_vep_failure_identifies_variant_and_exact_request(self):
        variant = SNV(
            pk=42, individual_id=17, analysis_id=23,
            chromosome="chr1", start=123, end=123,
            reference="A", alternate="T", zygosity="het",
            assembly_version="hg38",
        )
        for failure in (None, requests.Timeout("request timed out")):
            with self.subTest(failure=failure), patch("variant.services.requests.get") as get:
                get.return_value = Mock(
                    status_code=400,
                    text='{"error":"request for consequence of [T] matches reference [T]"}',
                )
                get.side_effect = failure
                output = StringIO()
                with redirect_stdout(output):
                    result = AnnotationService().fetch_vep(variant)
                self.assertIsNone(result)
                message, context = output.getvalue().split("\nVEP context: ")
                if failure:
                    self.assertIn("Timeout: request timed out", message)
                else:
                    self.assertIn("HTTP 400", message)
                    self.assertIn("matches reference [T]", message)
                context = json.loads(context)
                self.assertEqual(context["variant_id"], 42)
                self.assertEqual(context["individual_id"], 17)
                self.assertEqual(context["analysis_id"], 23)
                self.assertEqual(context["variant_type"], "SNV")
                self.assertEqual(context["assembly_version"], "hg38")
                self.assertEqual(context["reference"], "A")
                self.assertEqual(context["alternate"], "T")
                self.assertEqual(context["start"], 123)
                self.assertEqual(context["end"], 123)
                self.assertEqual(context["request_url"],
                    "https://rest.ensembl.org/vep/human/region/1:123:123/T?hgvs=1")

    def test_myvariant_uses_direct_snv_instance(self):
        service = AnnotationService()
        variant = SNV(
            chromosome="chr1",
            start=123,
            end=123,
            reference="A",
            alternate="G",
            zygosity="het",
        )

        with patch("variant.services.requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=404, text="not found")
            service.fetch_myvariant_info(variant)

        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], "https://myvariant.info/v1/variant/chr1:g.123A>G")
        self.assertEqual(kwargs["params"], {"assembly": "hg38"})

    def test_vep_uses_direct_cnv_instance(self):
        service = AnnotationService()
        variant = CNV(
            chromosome="chr7",
            start=100318423,
            end=100321323,
            cnv_type="gain",
            zygosity="het",
        )

        with patch("variant.services.requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=404, text="not found")
            service.fetch_vep(variant)

        args, kwargs = mock_get.call_args
        self.assertEqual(
            args[0],
            "https://rest.ensembl.org/vep/human/region/7:100318423-100321323:1/DUP",
        )
        self.assertEqual(kwargs["params"], {"hgvs": 1})

    def test_vep_uses_direct_sv_instance(self):
        service = AnnotationService()
        variant = SV(
            chromosome="chr2",
            start=200000,
            end=250000,
            sv_type="inversion",
            zygosity="het",
        )

        with patch("variant.services.requests.get") as mock_get:
            mock_get.return_value = Mock(status_code=404, text="not found")
            service.fetch_vep(variant)

        args, kwargs = mock_get.call_args
        self.assertEqual(
            args[0],
            "https://rest.ensembl.org/vep/human/region/2:200000-250000:1/INV",
        )
        self.assertEqual(kwargs["params"], {"hgvs": 1})

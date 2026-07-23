from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from variant.models import CNV, SNV, SV
from variant.services import AnnotationService


class AnnotationServiceVariantTypeTests(SimpleTestCase):
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

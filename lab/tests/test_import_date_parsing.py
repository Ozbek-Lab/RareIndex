from datetime import date, datetime

from django.test import SimpleTestCase

from lab.management.commands._import_helpers import parse_date
from lab.management.commands.import_ozbek_all import Command as ImportOzbekAllCommand
from lab.management.commands.update_ozbek_yayin_ici import Command as UpdateYayinIciCommand


class ImportDateParsingTests(SimpleTestCase):
    def test_parse_date_supports_common_import_formats(self):
        samples = {
            "20.03.1995": date(1995, 3, 20),
            "15.08.1992": date(1992, 8, 15),
            "31.07.2010": date(2010, 7, 31),
            "20.12.1980": date(1980, 12, 20),
            "15.09.1976": date(1976, 9, 15),
            "03.06.2024": date(2024, 6, 3),
            "20.06.2001": date(2001, 6, 20),
            "06.08.1997": date(1997, 8, 6),
            "27.12.2013": date(2013, 12, 27),
            "1989-12-30": date(1989, 12, 30),
            "1990-05-01": date(1990, 5, 1),
            "2024-10-28": date(2024, 10, 28),
            "1977-02-22": date(1977, 2, 22),
            "1990-03-04": date(1990, 3, 4),
            "2019-01-06": date(2019, 1, 6),
            "1985-11-04": date(1985, 11, 4),
        }

        for raw, expected in samples.items():
            with self.subTest(raw=raw):
                self.assertEqual(parse_date(raw), expected)

    def test_parse_date_accepts_datetime_objects(self):
        self.assertEqual(parse_date(datetime(2024, 10, 28, 14, 30)), date(2024, 10, 28))

    def test_private_import_parsers_delegate_to_shared_parser(self):
        import_ozbek = ImportOzbekAllCommand()
        yayin_ici = UpdateYayinIciCommand()

        self.assertEqual(import_ozbek._parse_date("20.03.1995"), date(1995, 3, 20))
        self.assertEqual(import_ozbek._parse_date("1989-12-30"), date(1989, 12, 30))
        self.assertEqual(yayin_ici._parse_ddmmyyyy("15.08.1992"), date(1992, 8, 15))
        self.assertEqual(yayin_ici._parse_ddmmyyyy("1990-05-01"), date(1990, 5, 1))

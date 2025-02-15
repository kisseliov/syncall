from pathlib import Path

import yaml

from syncall import convert_gcal_to_tw, convert_tw_to_gcal

from .generic_test_case import GenericTestCase


class TestConversions(GenericTestCase):
    """Test item conversions - TW <-> Google Calendar."""

    @classmethod
    def setUpClass(cls):
        pass

    def setUp(self):
        super(TestConversions, self).setUp()

    def load_sample_items(self):
        with open(Path(GenericTestCase.DATA_FILES_PATH, "sample_items.yaml"), "r") as fname:
            conts = yaml.load(fname, Loader=yaml.Loader)

        self.gcal_item = conts["gcal_item"]
        self.tw_item_expected = conts["tw_item_expected"]

        self.tw_item = conts["tw_item"]
        self.gcal_item_expected = conts["gcal_item_expected"]

        self.gcal_item_w_date = conts["gcal_item_w_date"]
        self.tw_item_w_date_expected = conts["tw_item_w_date_expected"]

    def test_tw_gcal_basic_convert(self):
        """Basic TW -> GCal conversion."""
        self.load_sample_items()
        gcal_item_out = convert_tw_to_gcal(self.tw_item)
        self.assertDictEqual(gcal_item_out, self.gcal_item_expected)

    def test_gcal_tw_basic_convert(self):
        """Basic GCal -> TW conversion."""
        self.load_sample_items()
        tw_item_out = convert_gcal_to_tw(self.gcal_item)
        self.assertDictEqual(tw_item_out, self.tw_item_expected)

    def test_gcal_tw_date_convert(self):
        """GCal (with 'date' subfield) -> TW conversion."""
        self.load_sample_items()
        tw_item_out = convert_gcal_to_tw(self.gcal_item_w_date)
        self.assertDictEqual(tw_item_out, self.tw_item_w_date_expected)

    def test_tw_gcal_n_back(self):
        """TW -> GCal -> TW conversion"""
        self.load_sample_items()
        tw_item_out = convert_gcal_to_tw(convert_tw_to_gcal(self.tw_item))

        self.assertSetEqual(
            set(self.tw_item) ^ set(tw_item_out),
            set({"entry", "due", "id", "tags", "urgency"}),
        )

        intersection = set(self.tw_item) & set(tw_item_out)
        self.assertDictEqual(
            {i: self.tw_item[i] for i in intersection},
            {i: tw_item_out[i] for i in intersection},
        )

    def test_gcal_tw_n_back(self):
        """GCal -> TW -> GCal conversion."""
        self.load_sample_items()
        gcal_item_out = convert_tw_to_gcal(convert_gcal_to_tw(self.gcal_item))

        self.assertSetEqual(
            set(self.gcal_item) ^ set(gcal_item_out),
            set(
                {
                    "htmlLink",
                    "kind",
                    "etag",
                    "extendedProperties",
                    "creator",
                    "created",
                    "organizer",
                    "sequence",
                    "status",
                    "reminders",
                    "iCalUID",
                    "id",
                }
            ),
        )
        # can't really check the description field..

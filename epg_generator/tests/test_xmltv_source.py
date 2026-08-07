import unittest

from epg_sources.xmltv_net.main import XMLTV


class XMLTVSourceTests(unittest.TestCase):
    def test_programme_times_are_normalised_to_utc_for_procentric(self):
        xml_data = """\
<tv>
  <channel id="abc-qld">
    <display-name>ABC TV QLD</display-name>
  </channel>
  <programme
      channel="abc-qld"
      start="20260806230000 +0000"
      stop="20260807000000 +0000">
    <title>ABC News Mornings</title>
  </programme>
</tv>
"""

        guide = XMLTV("unused", "Test guide", timezone=10).parse_xml_to_model(xml_data)
        event = guide.channels[0].events[0]

        # The appliance applies Brisbane's +10 offset. Emitting 09:00 here would
        # make this morning programme appear at 19:00, as seen in the OOL guide.
        self.assertEqual("2026-08-06", event.date)
        self.assertEqual("2300", event.startTime)
        self.assertEqual("60", event.length)

    def test_non_utc_xmltv_offsets_are_also_normalised_to_utc(self):
        xml_data = """\
<tv>
  <channel id="test">
    <display-name>Test channel</display-name>
  </channel>
  <programme
      channel="test"
      start="20260807090000 +1000"
      stop="20260807100000 +1000">
    <title>Morning programme</title>
  </programme>
</tv>
"""

        guide = XMLTV("unused", "Test guide", timezone=10).parse_xml_to_model(xml_data)
        event = guide.channels[0].events[0]

        self.assertEqual("2026-08-06", event.date)
        self.assertEqual("2300", event.startTime)
        self.assertEqual("60", event.length)


if __name__ == "__main__":
    unittest.main()

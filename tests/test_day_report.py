import unittest

from tempo_log.day_report import DayEntry, analyse


def e(i, start, minutes, issue="PROJ-1"):
    return DayEntry(i, start, minutes, issue)


class DayReportTests(unittest.TestCase):
    def test_clean_day(self):
        report = analyse([e(1, 600, 60), e(2, 660, 30)], 15, 720)
        self.assertEqual(report["total_minutes"], 90)
        self.assertEqual(report["overlaps"], [])
        self.assertEqual(report["gaps"], [])
        self.assertFalse(report["over_cap"])

    def test_overlap_gap_and_rounding(self):
        report = analyse([e(1, 600, 60), e(2, 630, 20), e(3, 720, 15)], 15, 720)
        self.assertEqual(len(report["overlaps"]), 1)
        self.assertEqual(report["gaps"], [(650, 720)])
        self.assertEqual([x.worklog_id for x in report["off_step"]], [2])

    def test_over_cap(self):
        report = analyse([e(1, 0, 13 * 60)], 15, 12 * 60)
        self.assertTrue(report["over_cap"])


if __name__ == "__main__":
    unittest.main()

import unittest

from tempo_log.worklog_import import merge_by_issue, parse_blocks

SAMPLE = """\
## 2026-01-05 (Fix login redirect)
Time: 09:00-09:20 (20m) | Ticket: PROJ-10 [id:1010]
- Found the redirect loop
- Added a guard

## 2026-01-05 (Follow-up on login redirect)
Time: 10:00-10:10 (10m) | Ticket: PROJ-10 [id:1010]
- Added a test

## 2026-01-05 (Planning call)
Time: 11:00-11:30 (30m, meeting) | Ticket: PROJ-20
- Reviewed the plan

## 2026-01-05 (Tidy scripts)
Time: 12:00-12:10 (10m) | Ticket: none
- Removed dead code

## 2026-01-05 (Batch summary)
Time: 13:00-14:00 (1h, summary) | Ticket: see sub-blocks below
- Not for the timesheet

## 2026-01-06 (Another day)
Time: 09:00-10:00 (1h) | Ticket: PROJ-30
- Other work
"""


class ParseTests(unittest.TestCase):
    def test_only_requested_date(self):
        blocks = parse_blocks(SAMPLE, "2026-01-05")
        self.assertEqual(len(blocks), 5)
        self.assertEqual(parse_blocks(SAMPLE, "2026-01-06")[0].issue, "PROJ-30")

    def test_duration_and_issue(self):
        first = parse_blocks(SAMPLE, "2026-01-05")[0]
        self.assertEqual(first.minutes, 20)
        self.assertEqual(first.issue, 1010)
        self.assertEqual(first.title, "Fix login redirect")

    def test_hour_duration_and_range_fallback(self):
        text = "## 2026-01-05 (X)\nTime: 09:00-10:30 | Ticket: PROJ-1\n- a\n"
        self.assertEqual(parse_blocks(text, "2026-01-05")[0].minutes, 90)

    def test_unassigned_and_container_blocks_are_flagged(self):
        blocks = parse_blocks(SAMPLE, "2026-01-05")
        self.assertEqual(blocks[3].skip_reason, "no ticket")
        self.assertIsNotNone(blocks[4].skip_reason)


class MergeTests(unittest.TestCase):
    def test_same_ticket_merged(self):
        merged = merge_by_issue(parse_blocks(SAMPLE, "2026-01-05"))
        self.assertEqual([m.issue for m in merged], [1010, "PROJ-20"])
        self.assertEqual(merged[1].minutes, 30)
        self.assertEqual(merged[0].minutes, 30)
        self.assertEqual(len(merged[0].bullets), 3)
        self.assertTrue(merged[0].description().startswith("Fix login redirect (+1 related):\n- "))

    def test_meetings_on_same_ticket_stay_separate(self):
        text = (
            "## 2026-01-05 (Call A)\nTime: 09:00-09:30 (30m, meeting) | Ticket: PROJ-1\n- a\n"
            "## 2026-01-05 (Call B)\nTime: 10:00-10:30 (30m, meeting) | Ticket: PROJ-1\n- b\n"
        )
        merged = merge_by_issue(parse_blocks(text, "2026-01-05"))
        self.assertEqual(len(merged), 2)

    def test_ticket_subheading_uses_parent_title(self):
        text = (
            "## 2026-01-05 (Landing page docs)\n\n### PROJ-5 [id:55]\n"
            "Time: 09:00-10:00 (1h) | Ticket: PROJ-5 [id:55]\n- Wrote docs\n"
        )
        block = parse_blocks(text, "2026-01-05")[0]
        self.assertEqual(block.title, "Landing page docs")

    def test_not_for_timesheet_bullet_skips_block(self):
        text = (
            "## 2026-01-05 (Tidy)\nTime: 09:00-09:30 (30m) | Ticket: PROJ-5\n"
            "- Did a thing\n- Not for timesheet: internal\n"
        )
        block = parse_blocks(text, "2026-01-05")[0]
        self.assertIsNotNone(block.skip_reason)
        self.assertEqual(merge_by_issue([block]), [])

    def test_duplicate_meeting_records_collapse(self):
        text = (
            "## 2026-01-05 (Call, first note)\nTime: 11:20-11:29 (9m, meeting) | Ticket: PROJ-1\n- a\n"
            "## 2026-01-05 (Call, second note)\nTime: 11:20-11:30 (10m, meeting) | Ticket: PROJ-1\n- b\n"
        )
        merged = merge_by_issue(parse_blocks(text, "2026-01-05"))
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].minutes, 10)
        self.assertEqual(len(merged[0].bullets), 2)


if __name__ == "__main__":
    unittest.main()

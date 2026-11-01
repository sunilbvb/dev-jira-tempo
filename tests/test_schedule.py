import unittest

from tempo_log.schedule import Item, ScheduleConfig, ScheduleError, build_day, build_schedule, round_up


def cfg(**kw):
    base = dict(start_candidates=("10:00",), break_issue="PROJ-1")
    base.update(kw)
    return ScheduleConfig(**base)


class RoundUpTests(unittest.TestCase):
    def test_rounds_up_with_minimum(self):
        self.assertEqual(round_up(1, 15), 15)
        self.assertEqual(round_up(20, 15), 30)
        self.assertEqual(round_up(45, 15), 45)
        self.assertEqual(round_up(46, 15), 60)

    def test_rejects_non_positive(self):
        with self.assertRaises(ScheduleError):
            round_up(0, 15)


class ScheduleTests(unittest.TestCase):
    def test_no_overlap_and_break_pinned(self):
        items = [Item("PROJ-2", 120), Item("PROJ-3", 120), Item("PROJ-4", 60)]
        placed = build_schedule(items, cfg())
        self.assertEqual(sum(1 for i in placed if i.issue == "PROJ-1"), 1)
        spans = sorted((i.start, i.start + i.minutes) for i in placed)
        for (_, end), (start, _) in zip(spans, spans[1:]):
            self.assertLessEqual(end, start)
        lunch = next(i for i in placed if i.issue == "PROJ-1")
        self.assertEqual(lunch.start, 14 * 60)

    def test_picks_start_with_smallest_gap(self):
        items = [Item("PROJ-2", 270)]
        placed = build_schedule(items, cfg(start_candidates=("10:00", "09:30")))
        work = next(i for i in placed if i.issue == "PROJ-2")
        self.assertEqual(work.start, 9 * 60 + 30)

    def test_item_that_does_not_fit_goes_after_break(self):
        items = [Item("PROJ-2", 60), Item("PROJ-3", 300)]
        placed = build_schedule(items, cfg())
        long_item = next(i for i in placed if i.issue == "PROJ-3")
        self.assertEqual(long_item.start, 15 * 60)

    def test_daily_cap(self):
        with self.assertRaises(ScheduleError):
            build_schedule([Item("PROJ-2", 13 * 60)], cfg())

    def test_without_break(self):
        placed = build_schedule([Item("PROJ-2", 30), Item("PROJ-3", 30)], cfg(break_issue=None))
        self.assertEqual([i.start for i in placed], [600, 630])


class BuildDayTests(unittest.TestCase):
    def test_calls_keep_their_real_start(self):
        items = [
            Item("W-1", 120),
            Item("CALL-1", 45, fixed_start=12 * 60),
            Item("W-2", 120),
        ]
        placed = build_day(items, cfg())
        call = next(i for i in placed if i.issue == "CALL-1")
        self.assertEqual(call.start, 12 * 60)
        spans = sorted((i.start, i.start + i.minutes) for i in placed)
        for (_, end), (start, _) in zip(spans, spans[1:]):
            self.assertLessEqual(end, start)

    def test_break_moves_around_a_call(self):
        items = [Item("CALL-1", 15, fixed_start=14 * 60 + 1), Item("W-1", 60)]
        placed = build_day(items, cfg())
        lunch = next(i for i in placed if i.issue == "PROJ-1")
        call = next(i for i in placed if i.issue == "CALL-1")
        self.assertTrue(lunch.start >= call.start + 15 or lunch.start + 60 <= call.start)

    def test_work_is_split_across_gaps_and_total_kept(self):
        items = [Item("CALL-1", 30, fixed_start=11 * 60), Item("W-1", 240)]
        placed = build_day(items, cfg(break_issue=None))
        work = [i for i in placed if i.issue == "W-1"]
        self.assertEqual(sum(i.minutes for i in work), 240)
        self.assertGreater(len(work), 1)


if __name__ == "__main__":
    unittest.main()

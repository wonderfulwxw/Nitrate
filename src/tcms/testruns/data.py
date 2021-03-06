# -*- coding: utf-8 -*-

from itertools import groupby
from operator import itemgetter
from typing import Dict, List

from django.conf import settings
from django.db.models import Count, F

from tcms.core.db import CaseRunStatusGroupByResult
from tcms.testruns.models import TestCaseRun
from tcms.testruns.models import TestCaseRunStatus


def stats_case_runs_status(run_ids: List[int]) -> Dict[int, CaseRunStatusGroupByResult]:
    """Get statistics based on case runs' status

    :param list[int] run_ids: id of test run from where to get statistics
    :return: the statistics including the number of each status mapping,
        total number of case runs, complete percent, and failure percent.
    :rtype: dict[int, CaseRunStatusGroupByResult]
    """
    result = (TestCaseRun.objects
              .filter(run__in=run_ids)
              .values('run_id', status_name=F('case_run_status__name'))
              .annotate(count=Count('pk'))
              .order_by('run_id', 'status_name'))

    # Example of final result: {
    #     # run_id: {status_1: count, ...}
    #     1: {'PASSED': 1, 'FAILED': 2, 'IDLE': 3, ...},
    #     2: {'PASSED': 1, 'ERROR': 2, 'IDLE': 3, ...},
    #     3: {'PASSED': 1, 'FAILED': 2, 'IDLE': 3, 'WAIVED': 4, ...},
    # }

    if result:
        subtotal = {}
        for item in result:
            run_id = item['run_id']
            status_subtotal = subtotal.setdefault(run_id, CaseRunStatusGroupByResult())
            status_subtotal[item['status_name']] = item['count']
    else:
        subtotal = {run_id: CaseRunStatusGroupByResult() for run_id in run_ids}

    stock_status_names = TestCaseRunStatus.objects.values_list('name', flat=True)

    # Not all case runs of a test run are not in all the status, hence some
    # status could be missed in the subtotal result.
    for item in subtotal.values():
        for name in stock_status_names:
            if name not in item:
                item[name] = 0

    return subtotal


class TestCaseRunDataMixin:
    """Data for test case runs"""

    def stats_mode_caseruns(self, case_runs):
        """Statistics from case runs mode

        @param case_runs: iteratable object to access each case run
        @type case_runs: iterable, list, tuple
        @return: mapping between mode and the count. Example return value is
            { 'manual': I, 'automated': J, 'manual_automated': N }
        @rtype: dict
        """
        manual_count = 0
        automated_count = 0
        manual_automated_count = 0

        for case_run in case_runs:
            is_automated = case_run.case.is_automated
            if is_automated == 1:
                automated_count += 1
            elif is_automated == 0:
                manual_count += 1
            else:
                manual_automated_count += 1

        return {
            'manual': manual_count,
            'automated': automated_count,
            'manual_automated': manual_automated_count,
        }

    def get_caseruns_comments(self, run_pk):
        """Get case runs' comments

        :param int run_pk: run's pk whose comments will be retrieved.
        :return: the mapping between case run id and comments
        :rtype: dict
        """
        qs = TestCaseRun.objects.filter(
            run=run_pk,
            comments__site=settings.SITE_ID,
            comments__is_public=True,
            comments__is_removed=False,
        ).annotate(
            submit_date=F('comments__submit_date'),
            comment=F('comments__comment'),
            user_name=F('comments__user_name'),
        ).values(
            'case_run_id',
            'submit_date',
            'comment',
            'user_name',
        ).order_by('pk')

        return {
            case_run_id: list(comments) for case_run_id, comments in
            groupby(qs, itemgetter('case_run_id'))
        }

    def get_summary_stats(self, case_runs):
        """Get summary statistics from case runs

        Statistics targets:
        - the number of pending test case runs, whose status is IDLE
        - the number of completed test case runs, whose status are PASSED,
          ERROR, FAILED, WAIVED

        @param case_runs: iterable object containing case runs
        @type case_runs: iterable
        @return: a mapping between statistics target and its value
        @rtype: dict
        """
        idle_count = 0
        complete_count = 0
        complete_status_names = TestCaseRunStatus.complete_status_names
        idle_status_names = TestCaseRunStatus.idle_status_names

        for case_run in case_runs:
            status_name = case_run.case_run_status.name
            if status_name in idle_status_names:
                idle_count += 1
            elif status_name in complete_status_names:
                complete_count += 1

        return {'idle': idle_count, 'complete': complete_count}

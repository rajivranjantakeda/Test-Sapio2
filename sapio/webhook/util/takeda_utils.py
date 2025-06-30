from typing import List

from sapiopylib.rest.pojo.eln.ElnEntryPosition import ElnEntryPosition
from sapiopylib.rest.pojo.eln.eln_headings import ElnExperimentTab
from sapiopylib.rest.utils.Protocols import ElnEntryStep

TabIdentifier = ElnExperimentTab | int | str
"""Accepts either an ElnExperimentTab, an integer for the tab id, or a string for the tab name."""


class ElnPositionUtil:
    """
    For dealing with Sapio ElnExperimentTabs.
    """

    @staticmethod
    def get_order(tabs: List[ElnExperimentTab], this_tab: TabIdentifier) -> int | None:
        """
        Iterates through the tabs and returns the order of the tab with the given identifier. Returns None if the tab
        is not found.
        """
        for tab in tabs:
            if isinstance(this_tab, ElnExperimentTab):
                if tab.tab_id == this_tab.tab_id:
                    return tab.tab_order
            elif isinstance(this_tab, int):
                if tab.tab_id == this_tab:
                    return tab.tab_order
            elif isinstance(this_tab, str):
                if tab.tab_name == this_tab:
                    return tab.tab_order
        return None

    @classmethod
    def is_after(cls, tabs: List[ElnExperimentTab], position1: ElnEntryPosition, position2: ElnEntryPosition):
        """
        Returns True if position1 is after position2, accounting for tab order. If either tab is not found, returns
        False.
        """
        tab_order_1 = cls.get_order(tabs, position1.tab_id)
        tab_order_2 = cls.get_order(tabs, position2.tab_id)
        if tab_order_1 is None or tab_order_2 is None:
            return False
        if tab_order_1 > tab_order_2:
            return True
        if tab_order_1 < tab_order_2:
            return False
        return position1.order > position2.order

    @staticmethod
    def to_position(entry_step: ElnEntryStep) -> ElnEntryPosition:
        """
        Converts an ElnEntryStep to an ElnEntryPosition with the position of that step.
        """
        return ElnEntryPosition(entry_step.eln_entry.notebook_experiment_tab_id, entry_step.eln_entry.order)
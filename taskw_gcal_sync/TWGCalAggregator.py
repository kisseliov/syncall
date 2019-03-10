from taskw_gcal_sync import GCalSide
from taskw_gcal_sync import TaskWarriorSide
from taskw_gcal_sync.PrefsManager import PrefsManager
from taskw_gcal_sync.clogger import setup_logging

from bidict import bidict
from typing import Any, Tuple, List, Dict, Union, Set
import atexit
import logging
import os
import sys

from uuid import UUID
from datetime import datetime, timedelta
from dateutil.tz import tzutc

logger = logging.getLogger(__name__)
setup_logging(__name__)

class TWGCalAggregator():
    """Aggregator class: TaskWarrior <-> Google Calendar sides.

    Having an aggregator is handy for managing push/pull/sync directives in a
    consistent manner.

    """
    def __init__(self, tw_config: dict, gcal_config: dict, **kargs):
        super(TWGCalAggregator, self, **kargs).__init__()

        assert isinstance(tw_config, dict)
        assert isinstance(gcal_config, dict)

        # Preferences manager
        self.prefs_manager = PrefsManager("taskw_gcal_sync")

        # Own config
        self.config = {}
        self.config['tw_id_key'] = 'uuid'
        self.config['gcal_id_key'] = 'htmlLink'
        self.config.update(**kargs)  # Update

        # Sides config + Initialisation
        tw_config_new = {}
        tw_config_new.update(tw_config)
        self.tw_side = TaskWarriorSide(**tw_config_new)

        gcal_config_new = {
            "credentials_dir": self.prefs_manager.prefs_dir_full,
        }
        gcal_config_new.update(tw_config)
        self.gcal_side = GCalSide(**gcal_config_new)

        # Correspondences between the TW reminders and the GCal events
        # The following fields are used for finding matches:
        # TaskWarrior: uuid
        # GCal: id
        if "tw_gcal_ids" not in self.prefs_manager:
            self.prefs_manager["tw_gcal_ids"] = bidict()
        self.tw_gcal_ids = self.prefs_manager["tw_gcal_ids"]

        atexit.register(self.cleanup)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cleanup()

    def start(self):
        self.tw_side.start()
        self.gcal_side.start()

    def cleanup(self):
        """Method to be called automatically on instance destruction.
        """
        pass

    def register_items(self, items: Tuple[Dict[str, Any]], item_type: str):
        """Register a list of items.

        - Register in the broker
        - Add the corresponding item in the other form (TW if registering GCal
          event or the other way around)

        :param item_type: "tw" / "gcal"
        """
        assert(item_type in ["tw", "gcal"])

        registered_ids = self.tw_gcal_ids if item_type == 'tw' else \
            self.tw_gcal_ids.inverse
        side = self.gcal_side if item_type == "tw" else self.gcal_side  # Use opposite side!
        convert_fun = TWGCalAggregator.convert_tw_to_gcal \
            if item_type == "tw" \
            else TWGCalAggregator.convert_gcal_to_tw

        type_key = self.config["{}_id_key".format(item_type)]
        opposite_type = "gcal" if item_type == "tw" else "tw"
        opposite_type_key = self.config["{}_id_key".format(opposite_type)]

        for item in items:
            _id = str(item[type_key])

            # Check if I have this item in the register
            if _id not in registered_ids.keys():
                # Create the item in TW
                logger.info("Inserting item, [{}] id: {}...".format(item_type,
                                                                    _id))

                # Cache it with pickle - f=_id

                # Add it to TW/GCal
                item_converted = convert_fun(item)
                item_registered = side.add_item(item_converted)

                #  Add registry entry
                registered_ids[_id] = item_registered[opposite_type_key]

    @staticmethod
    def compare_tw_gcal_items(tw_item: dict, gcal_item: dict) -> Tuple[Set[str],
                                                                       Dict[str, Tuple[Any, Any]]]:
        """Compare a TW and a GCal item and find any differences.

        :returns: list of different keys and Dictionary with the differences for
                  same keys
        """
        # Compare in TW form
        tw_item_out = TWGCalAggregator.convert_gcal_to_tw(gcal_item)
        diff_keys = {k for k in set(tw_item) ^ set(tw_item_out)}
        changes = {k: (tw_item[k], tw_item_out[k])
                   for k in set(tw_item) & set(tw_item_out)
                   if tw_item[k] != tw_item_out[k]}

        return diff_keys, changes

    @staticmethod
    def convert_tw_to_gcal(tw_item: dict) -> dict:
        """Convert a TW item to a Gcal event.

        .. note:: Do not convert the ID as that may change either manually or
                  after marking the task as "DONE"
        """

        assert all([i in tw_item.keys()
                    for i in ['description', 'status', 'uuid']]) and \
            "Missing keys in tw_item"

        gcal_item = {}

        # Summary
        gcal_item['summary'] = tw_item['description']

        # description
        gcal_item['description'] = "{meta_title}\n"\
            .format(desc=tw_item['description'],
                    meta_title='IMPORTED FROM TASKWARRIOR',)
        if 'annotations' in tw_item.keys():
            for i, a in enumerate(tw_item['annotations']):
                gcal_item['description'] += '\n* Annotation {}: {}' \
                    .format(i+1, a)

        gcal_item['description'] += '\n'
        for k in ['status', 'uuid']:
            gcal_item['description'] += '\n* {}: {}'.format(k, tw_item[k])

        # Handle dates:
        # - If given due date -> (start=entry, end=due)
        # - Else -> (start=entry, end=entry+1)
        entry_dt = GCalSide.format_datetime(tw_item['entry'])
        gcal_item['start'] = \
            {'dateTime': entry_dt}
        if 'due' in tw_item.keys():
            due_dt = GCalSide.format_datetime(tw_item['due'])
            gcal_item['end'] = {'dateTime': due_dt}
        else:
            gcal_item['end'] = {'dateTime': GCalSide.format_datetime(
                tw_item['entry'] + timedelta(days=1))}

        return gcal_item

    @staticmethod
    def convert_gcal_to_tw(gcal_item: dict) -> dict:
        """Convert a GCal event to a TW item."""

        # Parse the description
        annotations, status, uuid = \
            TWGCalAggregator._parse_gcal_item_desc(gcal_item)
        assert isinstance(annotations, list)
        assert isinstance(status, str)
        assert isinstance(uuid, UUID) or uuid is None

        tw_item: Dict[str, Any] = {}
        # annotations
        tw_item['annotations'] = annotations
        # Status
        if status not in ['pending', 'completed', 'deleted', 'waiting',
                          'recurring']:
            logger.warn(
                "Invalid status %s in GCal->TW conversion of item. Skipping status:"
                % status)
        else:
            tw_item['status'] = status

        # uuid - may just be created -, thus not there
        if uuid is not None:
            tw_item['uuid'] = uuid

        # Description
        tw_item['description'] = gcal_item['summary']

        # entry
        tw_item['entry'] = GCalSide.parse_datetime(gcal_item['start']['dateTime'])
        tw_item['due'] = GCalSide.parse_datetime(gcal_item['end']['dateTime'])

        # Note:
        # Don't add extra fields of GCal as TW annotations 'cause then, if
        # converted backwards, these annotations are going in the description of
        # the Gcal event and then these are going into the event description and
        # this happens on every conversion. Add them as new TW UDAs if needed

        # add annotation
        return tw_item

    @staticmethod
    def _parse_gcal_item_desc(gcal_item: dict) -> Tuple[List[str], str,
                                                        Union[UUID, None]]:
        """Parse the necessary TW fields off a Google Calendar Item.

        """
        annotations: List[str] = []
        status = 'pending'
        uuid = None

        if 'description' not in gcal_item.keys():
            return annotations, status, uuid

        gcal_desc = gcal_item['description']
        # strip whitespaces, empty lines
        lines = [l.strip() for l in gcal_desc.split('\n') if l][1:]

        # annotations
        i = 0
        for i, l in enumerate(lines):
            parts = l.split(':', maxsplit=1)
            if len(parts) == 2 and parts[0].lower().startswith("* annotation"):
                annotations.append(parts[1].strip())
            else:
                break

        if i == len(lines) - 1:
            return annotations, status, uuid

        # Iterate through rest of lines, find only the status and uuid ones
        for l in lines[i:]:
            parts = l.split(':', maxsplit=1)
            if len(parts) == 2:
                start = parts[0].lower()
                if start.startswith("* status"):
                    status = parts[1].strip().lower()
                elif start.startswith("* uuid"):
                    try:
                        uuid = UUID(parts[1].strip())
                    except ValueError as err:
                        logger.error(
                            "Invalid UUID %s provided during GCal -> TW conversion, Using None..."
                            % err)

        return annotations, status, uuid

    def find_in_tw(self, gcal_item) -> Union[Tuple[UUID, Dict], None]:
        """Given a GCal event find the corresponding reminder in TW, if the
        latter exists.

        :return: (ID, dict) for corresponding TW reminder, or None if a
        valid one is not found
        :rtype: tuple
        """

        pass

    def find_in_gcal(self, tw_item):
        """Given a TW reminder find the corresponding GCal event, if the
        latter exists.

        :return: ID of corresponding GCal reminder, None if a valid one is not
        found
        """

        pass


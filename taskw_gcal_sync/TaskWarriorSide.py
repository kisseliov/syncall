from taskw_gcal_sync import GenericSide
from taskw import TaskWarrior


class TaskWarriorSide(GenericSide):
    """Handles interaction with the TaskWarrior client."""
    def __init__(self, **kargs):
        super(TaskWarriorSide, self).__init__()

        self.config = {
            'tags': ""
        }
        self.config.update(**kargs)

        # TODO Only single tag versions are currently supported - recheck taskw
        # docs
        if not isinstance(self.config['tags'], str):
            self.logger.fatal(
                "\nPlease provide only a single tag in string form."
                " No other form is currently supported\n")
            raise RuntimeError

        # TaskWarrior instance as a class memeber - initialize only once
        self.tw = TaskWarrior(marshal=True)

    def get_items(self):
        """Fetch the tasks off the local taskw db.

        :return: list of tasks that exist locally

        """
        d = {}
        d['tags'] = self.config['tags']

        ret = self.tw.filter_tasks(filter_dict=d)
        return ret

    def update_item(self, item):
        """Update an already added item.
        """
        # Make sure it's there

        # Update
        raise NotImplementedError("TODO")

    def add_item(self, item) -> dict:
        """Add a new Item as a TW task.

        :param item:  This should contain only keys that exist in standard TW
                      tasks (e.g., proj, tag, due). It is mandatory that it
                      contains the 'description' key for the task title
        """
        assert('description' in item)
        len_print = min(10, len(item['desscription']))
        self.logger.info("Adding item - \"{}\"..."
                         .format(item['description'][0:len_print]))
        description = item.pop('description')
        new_item = self.tw.task_add(description=description, **item)

        return new_item

from collections import deque

class RollingBuffer:
    """
    A short-term memory buffer holding a maximum of 20 items.
    Old items are pruned when max length is reached.
    """
    def __init__(self, maxlen=20):
        self.maxlen = maxlen
        self._buffer = deque(maxlen=maxlen)

    def push(self, item: dict):
        """
        Push an item to the buffer.
        Item format: {'role': str, 'content': str, 'turn': int, 'timestamp': str, 'tags': list[str]}
        """
        self._buffer.append(item)

    def items(self):
        """Return the items in the buffer."""
        return list(self._buffer)

    def clear(self):
        """Clear the buffer."""
        self._buffer.clear()

    def __len__(self):
        """Return current length of the buffer."""
        return len(self._buffer)


class Scratchpad:
    """
    A persistent dict-backed scratchpad. 
    This scratchpad is NEVER touched or pruned by the RollingBuffer pruning mechanism.
    It holds persistent working state for the current session.
    """
    def __init__(self):
        self.plan = ""
        self.sub_goal = ""
        self.working_state = {}
        self.active_dispute_id = None
        self.active_analyst_id = None
        self.notes = []

    def update(self, **kwargs):
        """Update fields in the scratchpad."""
        if 'plan' in kwargs:
            self.plan = kwargs['plan']
        if 'sub_goal' in kwargs:
            self.sub_goal = kwargs['sub_goal']
        if 'working_state' in kwargs:
            self.working_state.update(kwargs['working_state'])
        if 'active_dispute_id' in kwargs:
            self.active_dispute_id = kwargs['active_dispute_id']
        if 'active_analyst_id' in kwargs:
            self.active_analyst_id = kwargs['active_analyst_id']
        if 'notes' in kwargs:
            self.notes.extend(kwargs['notes'])

    def get(self, key, default=None):
        """Get a value from the scratchpad using attribute access or default."""
        return getattr(self, key, default)

    def reset(self):
        """Reset the scratchpad to default empty state."""
        self.plan = ""
        self.sub_goal = ""
        self.working_state = {}
        self.active_dispute_id = None
        self.active_analyst_id = None
        self.notes = []

    def to_dict(self):
        """Return a dictionary representation of the scratchpad."""
        return {
            'plan': self.plan,
            'sub_goal': self.sub_goal,
            'working_state': self.working_state,
            'active_dispute_id': self.active_dispute_id,
            'active_analyst_id': self.active_analyst_id,
            'notes': self.notes
        }

    def from_dict(self, d: dict):
        """Load state from a dictionary."""
        self.reset()
        self.update(**d)

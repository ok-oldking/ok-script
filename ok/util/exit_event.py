import threading


class ExitEvent(threading.Event):
    queues = set()

    def bind_queue(self, queue):
        self.queues.add(queue)

    def set(self):
        super(ExitEvent, self).set()
        for queue in self.queues:
            queue.put(None)

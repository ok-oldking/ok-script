# Frame-independent one-time tasks (draft)

Ordinary tasks and trigger tasks retain their initial capture and input-backend
preparation. An explicitly queued one-time control task can opt out by setting:

    requires_initial_frame = False

Such a task is responsible for preparing/validating its own device before doing
any capture-dependent work. The flag skips only the executor's initial capture
and input preparation, not all future capture calls.

A pending enabled opt-in task wakes idle/trigger polling even if capture is
unavailable. It cannot preempt an active one-time task. Trigger execution always
keeps its capture guard, even if a trigger sets this flag.

Errors from an opt-in task use the cached screenshot rather than requesting a
new frame after cleanup closed the device.

This change does not alter Task.enable()/the normal StartController startup
workflow. A control UI can explicitly enqueue its registered task, as shown in
the paired OK-WW draft, without calling an implicit game-start workflow.

Run the dependency-free tests with:

    python -m unittest discover -s tests -p test_frame_independent.py -v

These are deterministic method-level tests with doubles, not live device tests.

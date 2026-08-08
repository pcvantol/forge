# Autonomous Mission Runtime Scheduler Architecture Authoring Report 001

The canonical Scheduler is a durable Forge Runtime capability. It connects
Forge planning to Engineering Platform through the versioned Producer
Submission Envelope without transferring governance, host admission, retry,
execution liveness or receipt ownership. The scheduler is sequential,
fail-closed, receipt-driven and restart-safe; parallel Actions and a second
scheduler remain out of scope.

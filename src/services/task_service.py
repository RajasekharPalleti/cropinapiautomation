"""Task API service (task fill).

GET  /services/farm/api/tasks/{id}  — task details (inherited get_by_id)
PUT  /services/farm/api/tasks       — fills (completes, or saves as a draft)
                                      an existing task; plain JSON body, not
                                      multipart. (POST on this URL creates a NEW
                                      task and rejects a body that carries an id:
                                      400 "A new task cannot already have an ID".)

The list of tasks that belong to a croppable area lives on ProjectService
(list_tasks_for_croppable_area, GET .../tasks/croppablearea/{id}) since it
hangs off the croppable area, not the task resource itself.
"""
from typing import Any

from src.core.response_wrapper import ApiResponse
from src.services.base_service import BaseService


class TaskService(BaseService):
    resource_path = "/services/farm/api/tasks"

    def fill(
        self,
        payload: dict | None = None,
        *,
        raw_body: str | None = None,
        headers: dict | None = None,
    ) -> ApiResponse:
        """PUTs a task-fill body. Pass `payload` for a normal JSON call, or
        `raw_body` (a pre-serialized string) to send something deliberately
        malformed. `headers` overrides per call — a value of None drops that
        header entirely (e.g. {"Authorization": None} for the no-auth case).
        The call's own duration_ms (from ApiClient's call log) is attached as
        `response.duration_ms` so tests can assert on response time.
        """
        if raw_body is not None:
            response = self._client.put(self.resource_path, data=raw_body, headers=headers)
        else:
            response = self._client.put(self.resource_path, json=payload, headers=headers)
        response.duration_ms = self._client.call_log[-1]["duration_ms"]
        return response

    def get_task(self, task_id: Any) -> ApiResponse:
        return self.get_by_id(task_id)
